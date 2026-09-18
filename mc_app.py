"""Local web UI for building Marvel Champions MPC orders. Run: python mc_app.py  (opens http://127.0.0.1:8765)"""
import io, json, os, re, threading, traceback, webbrowser
from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, ImageDraw
import mc_order
import mc_autofill
import mc_drive

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)
_thumb_cache = {}


@app.get("/")
def index():
    return send_from_directory(os.path.join(HERE, "ui"), "index.html")


@app.get("/api/catalog")
def catalog():
    return jsonify(mc_order.load_catalog())


@app.get("/api/library")
def library():
    lib = mc_order.load_library()
    backs = {s: {k: bool(mc_order.back_file(s, k)) for k in mc_order.BACK_KINDS} for s in ("original", "promo")}
    pr = mc_order.printings()
    return jsonify({"codes": sorted(lib), "count": len(lib), "backs": backs, "aliases": mc_order.alias_map(lib),
                    "printings": {k: v["packs"] for k, v in pr.items()}, "core_reprints": [k for k, v in pr.items() if v["core"]],
                    "dup_reprints": {k: v["original_pack"] for k, v in pr.items() if not v["core"] and v["original"] != k},
                    "exe": any(os.path.exists(e) for e in mc_order.EXE_CANDIDATES)})


def _wrap(s, n):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur] if cur else lines


@app.get("/img/<code>")
def img(code):
    """Thumbnail (or full image with ?full=1) for a card code; a labelled placeholder when not in the library yet."""
    lib = mc_order.load_library()
    f = mc_order.find_image(code, lib)
    if f:
        path = os.path.join(mc_order.LIB, f)
        if request.args.get("full"):
            return send_file(path)
        if code not in _thumb_cache:
            im = Image.open(path)
            im.thumbnail((300, 420))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=85)
            _thumb_cache[code] = buf.getvalue()
        return send_file(io.BytesIO(_thumb_cache[code]), mimetype="image/jpeg")
    label = request.args.get("name", code)
    im = Image.new("RGB", (300, 420), (40, 44, 52))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, 293, 413), radius=18, outline=(90, 96, 110), width=3)
    y = 170
    for line in _wrap(label, 22):
        d.text((150 - 3.2 * len(line), y), line, fill=(200, 205, 215))
        y += 16
    d.text((150 - 3.2 * len("no image yet"), y + 12), "no image yet", fill=(120, 126, 140))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.post("/api/preview")
def preview():
    sel = request.get_json(force=True)
    cards = mc_order.resolve_selection(sel)      # sets "have" and zeroes cards without an image
    return jsonify({"cards": cards, "total": sum(c["qty"] for c in cards), "missing": sum(1 for c in cards if not c["have"])})


@app.post("/api/build")
def build():
    body = request.get_json(force=True)
    try:
        return jsonify(mc_order.build_order(body.get("selection", {}), launch=bool(body.get("launch"))))
    except RuntimeError as ex:
        return jsonify({"error": str(ex)}), 400


@app.get("/api/autofill/options")
def autofill_options():
    return jsonify(mc_autofill.options())


@app.post("/api/autofill/start")
def autofill_start():
    body = request.get_json(force=True)
    if mc_autofill.JOB.running:
        return jsonify({"error": "an autofill run is already in progress"}), 409
    try:
        built = mc_order.build_order(body.get("selection", {}), launch=False)
    except RuntimeError as ex:
        return jsonify({"error": str(ex)}), 400
    if not built["cards"]:
        return jsonify({"error": "the order has no cards with images", "build": built}), 400
    settings = dict(body.get("settings") or {})
    settings["landing_url"] = request.host_url.rstrip("/") + "/autofill-landing"
    snap = mc_autofill.start(built["folder"], settings)
    return jsonify({"build": built, "job": snap})


@app.get("/api/autofill/status")
def autofill_status():
    return jsonify(mc_autofill.JOB.snapshot())


@app.post("/api/autofill/answer")
def autofill_answer():
    body = request.get_json(force=True)
    ok = mc_autofill.JOB.reply(int(body.get("id", 0)), body.get("value", ""))
    return jsonify({"ok": ok})


@app.post("/api/autofill/abort")
def autofill_abort():
    mc_autofill.abort()
    return jsonify({"ok": True})


@app.get("/api/drive/default")
def drive_default():
    return jsonify({"url": mc_drive.DEFAULT_FOLDER})


@app.get("/api/drive/tree")
def drive_tree():
    """Importable folders of a shared Google Drive link, with how many are already in the library."""
    link = request.args.get("url") or mc_drive.DEFAULT_FOLDER
    try:
        info = mc_drive.tree(link, key=request.args.get("key") or None, refresh=bool(request.args.get("refresh")))
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({"error": f"{type(ex).__name__}: {ex}"}), 400
    done = mc_drive.load_done()
    # folders imported by hand (mc_import.py on a local copy) are recognised from the paths recorded in sources.json
    srcp = os.path.join(mc_order.LIB, "sources.json")
    # Drive zip downloads turn ' and ’ into _ in folder names, so compare with all of them folded to _
    tidy = lambda p: "\\" + re.sub(r"['‘’]", "_", p.replace("/", "\\")).lower()   # noqa: E731
    sources = [tidy(v) for v in (json.load(open(srcp, encoding="utf-8")).values() if os.path.exists(srcp) else [])]
    for u in info["units"]:
        u["done"] = done.get(u["id"])
        if not u["done"]:
            key = tidy(u["name"]) + "\\"
            if u["category"] == "Other":            # top-level folders must be the root of the recorded path
                n = sum(1 for v in sources if v.startswith(key))
            else:
                n = sum(1 for v in sources if key in v and not v.startswith("\\core set\\"))
            if n:
                u["done"] = {"manual": True, "converted": n, "had": 0, "files": u.get("files"), "unmatched": 0, "failed": [], "when": "earlier import"}
    return jsonify({**info, "default_url": mc_drive.DEFAULT_FOLDER})


@app.post("/api/drive/import")
def drive_import():
    body = request.get_json(force=True)
    try:
        snap = mc_drive.start(body.get("url") or mc_drive.DEFAULT_FOLDER, body.get("units") or [], key=body.get("key"),
                              keep_scans=bool(body.get("keep_scans")), redo=bool(body.get("redo")))
    except Exception as ex:  # noqa: BLE001
        return jsonify({"error": str(ex)}), 409
    return jsonify(snap)


@app.get("/api/drive/status")
def drive_status():
    return jsonify(mc_drive.JOB.snapshot())


@app.post("/api/drive/abort")
def drive_abort():
    mc_drive.abort()
    return jsonify({"ok": True})


@app.get("/autofill-landing")
def autofill_landing():
    return ("<!doctype html><meta charset='utf-8'><title>MC Autofill</title>"
            "<body style='font-family:system-ui;background:#14161b;color:#e6e8ee;display:flex;align-items:center;"
            "justify-content:center;height:100vh;margin:0'><div style='text-align:center;max-width:520px'>"
            "<h1 style='color:#e23636'>MC Autofill</h1><p>This browser window is being driven by MC Autofill. Leave it open.</p>"
            "<p>Progress, questions and the sign-in step are shown at the top of the MC Autofill app.</p></div></body>")


if __name__ == "__main__":
    port = 8765
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
