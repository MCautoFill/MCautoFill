"""Import a Proxy Nexus MPC export (zip or unpacked folder) into a game's image library.

Proxy Nexus names every image {card id}-{variant}-{collection}-{copy}[-back].{ext} inside card-images/ or
{player|encounter|quest}-images/, and puts the generic card backs at the top level as {group}_{label}.bleed.{ext}.
The card id is the one from Proxy Nexus's own catalog: the ArkhamDB code for Arkham Horror, and Proxy Nexus's
title-and-pack id for The Lord of the Rings, which is exactly what games/<game>/catalog.json uses. So the import is a
rename: copy one image per card side into games/<game>/library/ as <id>.<ext> / <id>~back.<ext>, and the backs into
games/<game>/backs/ as <label>_<group>.<ext> (the naming the order builder expects).
"""
import json, os, re, shutil, time, zipfile
import games

NAME = re.compile(r"^(?P<id>[^-]+)-(?P<variant>[^-]+)-(?P<coll>.+?)-(?P<n>\d+)(?P<back>-back\d*)?$")
BACK = re.compile(r"^(?P<group>[a-z]+)_(?P<label>[a-z0-9]+)(?:\.bleed)?$", re.I)
IMG = (".jpg", ".jpeg", ".png", ".webp")
GAME_OF_COLLECTION = {"ahlcg": "arkham", "lotrlcg": "lotr"}


def game_of(collection):
    return GAME_OF_COLLECTION.get(collection.split("-")[0])


def _entries(src):
    """(relative path, opener) for every file in a zip or a folder."""
    if os.path.isdir(src):
        for root, _, files in os.walk(src):
            for f in files:
                p = os.path.join(root, f)
                yield os.path.relpath(p, src).replace(os.sep, "/"), (lambda p=p: open(p, "rb"))
    else:
        zf = zipfile.ZipFile(src)
        for info in zf.infolist():
            if not info.is_dir():
                yield info.filename, (lambda n=info.filename: zf.open(n))


def inspect(src):
    """What an export contains without importing it: {game, cards, backs, unknown}."""
    cards, backs, unknown, game = set(), [], [], None
    for rel, _ in _entries(src):
        base = os.path.basename(rel)
        stem, ext = os.path.splitext(base)
        if ext.lower() not in IMG:
            continue
        m = NAME.match(stem)
        if m and "/" in rel:
            cards.add((m["id"], bool(m["back"])))
            game = game or game_of(m["coll"])
        elif "/" not in rel and BACK.match(stem):
            backs.append(base)
        else:
            unknown.append(rel)
    fronts = {i for i, b in cards if not b}
    return {"game": game, "cards": len(fronts), "ids": sorted(fronts), "backs": backs, "unknown": unknown[:10]}


def packs_of(ids, catalog):
    """Which catalog packs an export's card ids belong to: [(pack name, cards from it)], most first."""
    where = {}
    for p in catalog.get("packs", []):
        for s in p["sections"]:
            for c in s["cards"]:
                where.setdefault(c["code"], p["name"])
    counts = {}
    for i in ids:
        name = where.get(i)
        if name:
            counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def import_export(game, src, log=print):
    paths = games.paths(game)
    libdir, backsdir = paths["library"], paths["backs"]
    os.makedirs(libdir, exist_ok=True)
    os.makedirs(backsdir, exist_ok=True)
    libp, srcp, donep = (os.path.join(libdir, n) for n in ("library.json", "sources.json", "pn_done.json"))
    lib = json.load(open(libp, encoding="utf-8")) if os.path.exists(libp) else {}
    sources = json.load(open(srcp, encoding="utf-8")) if os.path.exists(srcp) else {}
    done = json.load(open(donep, encoding="utf-8")) if os.path.exists(donep) else {}
    label = os.path.basename(src.rstrip("/\\"))
    added, replaced, skipped, backs, unknown = 0, 0, 0, [], []
    seen = set()
    for rel, opener in _entries(src):
        base = os.path.basename(rel)
        stem, ext = os.path.splitext(base)
        ext = ext.lower()
        if ext not in IMG:
            continue
        m = NAME.match(stem)
        if m and "/" in rel:
            coll_game = game_of(m["coll"])
            if coll_game and coll_game != game:
                raise RuntimeError(f"this export is for {games.get(coll_game)['name']}, not {games.get(game)['name']} ({base})")
            key = m["id"] + ("~back" if m["back"] else "")
            if key in seen:
                skipped += 1                              # copy 2, 3... of the same image
                continue
            seen.add(key)
            dest = re.sub(r"[^\w.\-~]", "~", key) + ext
            existed = key in lib and os.path.exists(os.path.join(libdir, lib[key]))
            with opener() as fh, open(os.path.join(libdir, dest + ".part"), "wb") as out:
                shutil.copyfileobj(fh, out)
            os.replace(os.path.join(libdir, dest + ".part"), os.path.join(libdir, dest))
            if existed and lib[key] != dest:
                try:
                    os.remove(os.path.join(libdir, lib[key]))
                except OSError:
                    pass
            lib[key] = dest
            sources[key] = f"{label}/{rel}"
            replaced += existed
            added += not existed
        elif "/" not in rel and BACK.match(stem):
            b = BACK.match(stem)
            dest = f"{b['label'].lower()}_{b['group'].lower()}{ext}"
            with opener() as fh, open(os.path.join(backsdir, dest), "wb") as out:
                shutil.copyfileobj(fh, out)
            backs.append(dest)
        else:
            unknown.append(rel)
    json.dump(lib, open(libp, "w", encoding="utf-8"), indent=1)
    json.dump(sources, open(srcp, "w", encoding="utf-8"), indent=1)
    done[label] = {"when": time.strftime("%Y-%m-%d %H:%M"), "added": added, "replaced": replaced, "backs": backs}
    json.dump(done, open(donep, "w", encoding="utf-8"), indent=1)
    log(f"{label}: {added} new images, {replaced} replaced, {skipped} duplicate copies skipped, {len(backs)} backs"
        + (f", {len(unknown)} files not understood" if unknown else "") + f" -> library has {sum(1 for k in lib if '~' not in k)} cards")
    return {"added": added, "replaced": replaced, "skipped": skipped, "backs": backs, "unknown": unknown[:20]}


def list_exports(folder):
    """Proxy Nexus exports (zips, or folders holding order.xml) in a folder, newest first."""
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    for n in os.listdir(folder):
        p = os.path.join(folder, n)
        if n.lower().endswith(".zip") or (os.path.isdir(p) and os.path.exists(os.path.join(p, "order.xml"))):
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append({"name": n, "path": p, "size": st.st_size if os.path.isfile(p) else None, "mtime": st.st_mtime})
    return sorted(out, key=lambda e: -e["mtime"])


if __name__ == "__main__":
    import sys
    print(json.dumps(import_export(sys.argv[1], sys.argv[2]), indent=1))
