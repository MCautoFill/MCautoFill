"""Local web UI for building MPC orders (Marvel Champions, Arkham Horror, The Lord of the Rings).
Run: python mc_app.py  (opens http://127.0.0.1:8765)"""
import io, json, os, re, threading, traceback, webbrowser
from flask import Flask, jsonify, request, send_file, send_from_directory
from PIL import Image, ImageDraw
import games
import mc_order
import mc_autofill
import mc_drive
import pn_import
import set_order

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)
_thumb_cache = {}


@app.get("/")
def index():
    return send_from_directory(os.path.join(HERE, "ui"), "index.html")


def game_arg(body=None):
    """Which game a request is about: ?game= or the "game" key of a JSON body; Marvel Champions when unsaid."""
    g = (body or {}).get("game") or request.args.get("game") or games.DEFAULT
    games.get(g)
    return g


def is_sets(game):
    return games.get(game)["kind"] == "sets"


@app.get("/api/games")
def games_list():
    return jsonify({"games": games.listing(), "default": games.DEFAULT})


@app.get("/api/catalog")
def catalog():
    game = game_arg()
    return jsonify(set_order.load_catalog(game) if is_sets(game) else mc_order.load_catalog())


@app.get("/api/library")
def library():
    game = game_arg()
    if is_sets(game):
        lib = set_order.load_library(game)
        bdir = games.paths(game)["backs"]
        styles = mc_order.back_styles(bdir)
        backs = {st: {k: bool(mc_order.back_file(st, k, bdir)) for k in games.get(game)["back_kinds"]} for st in styles}
        return jsonify({"codes": sorted(k for k in lib if "~" not in k), "count": sum(1 for k in lib if "~" not in k),
                        "backs": backs, "styles": styles, "aliases": {}, "printings": {}, "core_reprints": [], "dup_reprints": {}})
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
    game = game_arg()
    if is_sets(game):
        lib = set_order.load_library(game)
        f = set_order.find_image(code, lib, game)
        path = os.path.join(games.paths(game)["library"], f) if f else None
    else:
        lib = mc_order.load_library()
        f = mc_order.find_image(code, lib)
        path = os.path.join(mc_order.LIB, f) if f else None
    if path:
        if request.args.get("full"):
            return send_file(path)
        key = (game, code)
        if key not in _thumb_cache:
            im = Image.open(path)
            im.thumbnail((300, 420))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=85)
            _thumb_cache[key] = buf.getvalue()
        return send_file(io.BytesIO(_thumb_cache[key]), mimetype="image/jpeg")
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
    game = game_arg(sel)
    cards = set_order.resolve_selection(game, sel) if is_sets(game) else mc_order.resolve_selection(sel)
    return jsonify({"cards": cards, "total": sum(c["qty"] for c in cards), "missing": sum(1 for c in cards if not c["have"])})


@app.post("/api/build")
def build():
    body = request.get_json(force=True)
    try:
        return jsonify(build_for(body.get("selection", {}), launch=bool(body.get("launch"))))
    except RuntimeError as ex:
        return jsonify({"error": str(ex)}), 400


def build_for(sel, launch=False):
    game = game_arg(sel)
    return set_order.build_order(game, sel, launch=launch) if is_sets(game) else mc_order.build_order(sel, launch=launch)


@app.get("/api/autofill/options")
def autofill_options():
    return jsonify(mc_autofill.options())


@app.post("/api/autofill/start")
def autofill_start():
    body = request.get_json(force=True)
    if mc_autofill.JOB.running:
        return jsonify({"error": "an autofill run is already in progress"}), 409
    try:
        built = build_for(body.get("selection", {}), launch=False)
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


@app.get("/api/pn/exports")
def pn_exports():
    """Proxy Nexus exports in a folder (default: the Downloads folder), with what each one holds."""
    game = game_arg()
    folder = request.args.get("dir") or os.path.join(os.path.expanduser("~"), "Downloads")
    donep = os.path.join(games.paths(game)["library"], "pn_done.json")
    done = json.load(open(donep, encoding="utf-8")) if os.path.exists(donep) else {}
    out = []
    for e in pn_import.list_exports(folder):
        try:
            info = pn_import.inspect(e["path"])
        except Exception as ex:  # noqa: BLE001
            info = {"game": None, "cards": 0, "backs": [], "error": str(ex)}
        if info.get("game") is None and not info.get("cards"):
            continue                                   # not a Proxy Nexus export
        e.update(info)
        e["done"] = done.get(e["name"])
        out.append(e)
    return jsonify({"dir": folder, "exports": out})


@app.post("/api/pn/import")
def pn_do_import():
    body = request.get_json(force=True)
    game = game_arg(body)
    results = []
    for path in body.get("paths") or []:
        try:
            results.append({"path": path, **pn_import.import_export(game, path, log=lambda *a: None)})
        except Exception as ex:  # noqa: BLE001
            results.append({"path": path, "error": str(ex)})
    _thumb_cache.clear()
    return jsonify({"results": results})


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
