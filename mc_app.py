"""Local web UI for building Marvel Champions MPC orders. Run: python mc_app.py  (opens http://127.0.0.1:8765)"""
import io, os, threading, webbrowser
from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, ImageDraw
import mc_order
import mc_autofill

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
    lib = mc_order.load_library()
    cards = mc_order.resolve_selection(sel)
    for c in cards:
        c["have"] = bool(mc_order.find_image(c["front"], lib))
    return jsonify({"cards": cards, "total": sum(c["qty"] for c in cards), "missing": sum(1 for c in cards if not c["have"])})


@app.post("/api/build")
def build():
    body = request.get_json(force=True)
    return jsonify(mc_order.build_order(body.get("selection", {}), launch=bool(body.get("launch"))))


@app.get("/api/autofill/options")
def autofill_options():
    return jsonify(mc_autofill.options())


@app.post("/api/autofill/start")
def autofill_start():
    body = request.get_json(force=True)
    if mc_autofill.JOB.running:
        return jsonify({"error": "an autofill run is already in progress"}), 409
    built = mc_order.build_order(body.get("selection", {}), launch=False)
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
