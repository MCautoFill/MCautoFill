"""Turn a UI selection into an MPC-autofill order folder (images + order.xml) and optionally launch autofill."""
import json, os, re, shutil, subprocess, sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "library")
BACKS = os.path.join(HERE, "backs")
ORDERS = os.path.join(HERE, "orders")
# Optional: the stand-alone mpc-autofill desktop tool, copied into each order folder for the manual flow.
# Not needed for "Build & autofill" (the tool is embedded); set MC_AUTOFILL_EXE to point at it elsewhere.
EXE_CANDIDATES = [os.path.join(HERE, "autofill-windows.exe")] + ([os.environ["MC_AUTOFILL_EXE"]] if os.environ.get("MC_AUTOFILL_EXE") else [])
ENCOUNTER_TYPES = {"villain", "minion", "treachery", "attachment", "environment", "side_scheme", "main_scheme",
                   "obligation", "leader", "evidence_means", "evidence_motive", "evidence_opportunity"}


def load_catalog():
    cat = json.load(open(os.path.join(HERE, "catalog.json"), encoding="utf-8"))
    merge_extras(cat)
    return cat


def merge_extras(cat):
    """Add scans MarvelCDB does not index (library/extra.json, written by mc_import) as extra encounter sets.
    Side A/B scans of one card are paired into a double-sided physical card."""
    p = os.path.join(LIB, "extra.json")
    if not os.path.exists(p):
        return
    extras = json.load(open(p, encoding="utf-8"))
    by_pack = {_norm(p["name"]): p for p in cat["packs"]}
    for alias, real in (("Red Skull", "The Rise of Red Skull"), ("Agends of SHIELD", "Agents of S.H.I.E.L.D."),
                        ("Galaxy's Most Wanted", "The Galaxy's Most Wanted"), ("Mad Titan's Shadow", "The Mad Titan's Shadow")):
        if _norm(real) in by_pack:
            by_pack[_norm(alias)] = by_pack[_norm(real)]
    by_hero = {h["set"]: h for h in cat["heroes"]}
    groups = {}
    # hero-attached extras (deck lists, rules references): they join the hero's own cards and get the player back
    hero_extra = {}
    for code, e in extras.items():
        if e.get("hero_set") and e["hero_set"] in by_hero:
            hero_extra.setdefault(e["hero_set"], []).append(
                {"code": code, "name": e["name"], "type": "decklist", "faction": "hero", "qty": 1, "double": False,
                 "linked": None, "side": e.get("side")})
    for hs, cards in hero_extra.items():
        codes = {c["code"] for c in cards}
        for c in cards:
            if c["side"] == "a" and c["code"][:-1] + "b" in codes:
                c["linked"] = c["code"][:-1] + "b"
        # the pack's divider card: "STOP!" rules text on one side, the deck list on the other
        rules = next((c for c in cards if c["code"].endswith(":rules")), None)
        dl = next((c for c in cards if c["code"].endswith(":decklist")), None)
        if rules and dl:
            rules["name"], rules["linked"] = "Deck divider (STOP! / deck list)", dl["code"]
            dl["code"] = dl["code"] + "~side"      # marks it as the back side so physical_cards() folds it in
            rules["linked"] = dl["code"]
        by_hero[hs]["hero_cards"].extend(cards)
    for code, e in extras.items():
        if e.get("hero_set"):
            continue
        pack = by_pack.get(_norm(e["pack"]))
        if pack is None:
            pack = {"code": "scan:" + e["pack"], "name": e["pack"] + " (from scans)", "kind": "campaign",
                    "heroes": [], "player_cards": [], "encounter_sets": []}
            cat["packs"].append(pack)
            by_pack[_norm(e["pack"])] = pack
        key = (pack["code"], e["set"])
        if key not in groups:
            groups[key] = {"code": "scan:" + e["set"], "name": e["set"] + " (from scans)", "kind": "scan", "cards": []}
            pack["encounter_sets"].append(groups[key])
        groups[key]["cards"].append({"code": code, "name": e["name"], "type": e.get("type_code") or "unknown", "faction": "encounter",
                                     "qty": e.get("qty", 1), "double": False, "linked": None, "side": e.get("side")})
    # pair "...a" / "...b" sides: the b side becomes the back of the a side
    for g in groups.values():
        codes = {c["code"] for c in g["cards"]}
        for c in g["cards"]:
            if c["side"] == "a" and c["code"][:-1] + "b" in codes:
                c["linked"] = c["code"][:-1] + "b"


_EQUIV = None


def _norm(s):
    import re, unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def equivalents():
    """code -> other codes that are the same printed card (reprints across packs): identical name, subtitle,
    type, aspect and rules text.  MarvelCDB gives every pack's copy its own code; the scans exist only once."""
    global _EQUIV
    if _EQUIV is None:
        cards = json.load(open(os.path.join(HERE, "marvelcdb_cards.json"), encoding="utf-8"))
        groups = {}
        for c in cards:
            key = (_norm(c["name"]), _norm(c.get("subname")), c["type_code"], c.get("faction_code"),
                   _norm(c.get("real_text") or c.get("text")), str(c.get("stage") or ""))
            groups.setdefault(key, []).append(c["code"])
        _EQUIV = {code: [k for k in codes if k != code] for codes in groups.values() if len(codes) > 1 for code in codes}
    return _EQUIV


_PRINT = None


def printings():
    """code -> {"packs": [pack names of every identical printing, own first], "core": True if one of them is the Core Set}"""
    global _PRINT
    if _PRINT is None:
        cards = {c["code"]: c for c in json.load(open(os.path.join(HERE, "marvelcdb_cards.json"), encoding="utf-8"))}
        _PRINT = {}
        for code, others in equivalents().items():
            names = [cards[code]["pack_name"]] + [cards[o]["pack_name"] for o in others if o in cards]
            seen, packs = set(), []
            for n in names:
                if n not in seen:
                    seen.add(n)
                    packs.append(n)
            # the original printing is the one with the lowest pack number (MarvelCDB codes start with the pack number)
            allc = [code] + [o for o in others if o in cards]
            original = min(allc, key=lambda k: (int(k[:2]) if k[:2].isdigit() else 99, k))
            _PRINT[code] = {"packs": packs, "core": any(cards[o]["pack_code"] == "core" for o in others if o in cards),
                            "original": original, "original_pack": cards[original]["pack_name"]}
    return _PRINT


def find_image(code, lib, sides=True):
    """Library file for a code: its own scan, else a sibling art variant (…a/b/c), else an identical printing.
    sides=False skips the a/b/c siblings: for the back of a two-sided card they are the *other* side, not a variant."""
    if not code:
        return None
    f = lib.get(code)
    if f and os.path.exists(os.path.join(LIB, f)):
        return f
    if sides and code[-1] in "abcd":
        for letter in "abcd":
            g = lib.get(code[:-1] + letter)
            if g and os.path.exists(os.path.join(LIB, g)):
                return g
    for other in equivalents().get(code, []):
        g = lib.get(other)
        if g and os.path.exists(os.path.join(LIB, g)):
            return g
    return None


def alias_map(lib):
    """code -> code whose image stands in for it, for every catalog code without its own scan."""
    out = {}
    for code, others in equivalents().items():
        if code in lib:
            continue
        for other in others:
            if other in lib:
                out[code] = other
                break
    return out


def load_library():
    """code -> relative image path, built by mc_import.py. Missing file = no images yet."""
    p = os.path.join(LIB, "library.json")
    lib = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    for code in [c for c in lib if c.startswith("x:decklist:") and c.endswith(":decklist")]:
        lib[code + "~side"] = lib[code]          # alias used when the deck list is the back of the divider card
    return lib


def physical_cards(cards):
    """Collapse MarvelCDB a/b pairs into one physical card: {front, back, name, type, qty, faction}."""
    codes = {c["code"] for c in cards}
    out = []
    for c in cards:
        code = c["code"]
        if code.endswith("b") and code[:-1] + "a" in codes:
            continue  # back side of a double-sided card
        if code.endswith("~side"):
            continue  # explicit back side (deck divider)
        if code + "a" in codes:
            continue  # MarvelCDB lists double-sided main schemes both as "X" and as the "Xa"/"Xb" pair; keep the pair
        back = c.get("linked") if (c.get("linked") and c["linked"] in codes) else None
        out.append({"front": code, "back": back, "name": c["name"], "type": c["type"], "qty": c.get("qty", 1),
                    "faction": c.get("faction")})
    return out


def is_encounter(card):
    return card["type"] in ENCOUNTER_TYPES or card.get("faction") == "encounter"


VILLAIN_TYPES = {"villain", "leader"}


def back_kind(card):
    """Which printed back a single-sided card gets: blue player, orange encounter, or purple villain."""
    if card["type"] in VILLAIN_TYPES:
        return "villain"
    return "encounter" if is_encounter(card) else "player"


def resolve_selection(sel, catalog=None):
    """Expand a selection into the list of physical cards (qty = copies) grouped by where they came from."""
    catalog = catalog or load_catalog()
    heroes = {h["set"]: h for h in catalog["heroes"]}
    packs = {p["code"]: p for p in catalog["packs"]}
    single = sel.get("copies") == "single"
    picked, seen = [], set()

    def add(cards, group):
        for pc in physical_cards(cards):
            if pc["front"] in seen:
                continue
            seen.add(pc["front"])
            pc["group"] = group
            if single and not is_encounter(pc):
                pc["qty"] = 1
            pc["default_qty"] = pc["qty"]
            picked.append(pc)

    for hs in sel.get("heroes", []):
        h = heroes.get(hs["set"])
        if not h:
            continue
        add(h["hero_cards"], f"Hero: {h['name']}")
        if hs.get("nemesis", True):
            add(h["nemesis_cards"], f"Nemesis: {h['name']}")
        if hs.get("mode") == "hero+pack":
            p = packs.get(h["pack"])
            if p:
                add(p["player_cards"], f"Player cards: {p['name']}")
        if hs.get("modular", True):                      # the modular encounter set(s) that ship in the hero's pack
            p = packs.get(h["pack"])
            if p and p["kind"] == "hero":
                for es in p["encounter_sets"]:
                    add(es["cards"], f"Modular set: {es['name']}")
    for ps in sel.get("packs", []):
        p = packs.get(ps["code"])
        if not p:
            continue
        if ps.get("player_cards"):
            add(p["player_cards"], f"Player cards: {p['name']}")
        wanted = set(ps.get("encounter_sets") or [])
        for es in p["encounter_sets"]:
            if es["code"] in wanted:
                add(es["cards"], f"{p['name']}: {es['name']}")
    # reprints: note where else each card was printed; Core Set reprints default to 0 copies unless asked for
    pr = printings()
    for pc in picked:
        info = pr.get(pc["front"])
        pc["also_in"] = info["packs"][1:] if info else []
        pc["core_reprint"] = bool(info and info["core"]) and not is_encounter(pc)
        pc["dup_reprint"] = bool(info and not info["core"] and info["original"] != pc["front"]) and not is_encounter(pc)
        pc["original_pack"] = info["original_pack"] if (info and info["original"] != pc["front"]) else None
        if pc["core_reprint"] and not sel.get("core_reprints"):
            pc["qty"] = 0
        if pc["dup_reprint"] and not sel.get("dup_reprints"):
            pc["qty"] = 0
    # cards with no image in the library yet default to 0 copies: nothing could be printed for them anyway
    lib = load_library()
    for pc in picked:
        pc["have_front"] = bool(find_image(pc["front"], lib))
        pc["have_back"] = bool(find_image(pc["back"], lib, sides=False)) if pc["back"] else True
        pc["have"] = pc["have_front"] and pc["have_back"]
        if not pc["have"]:
            pc["qty"] = 0
    # per-card quantity overrides from the order list (0 = leave out of the build)
    overrides = sel.get("qty") or {}
    for pc in picked:
        if pc["front"] in overrides:
            try:
                pc["qty"] = max(0, int(overrides[pc["front"]]))
            except (TypeError, ValueError):
                pass
    return picked


BACK_KINDS = ("player", "encounter", "villain")
# MPC cardstocks as the embedded autofill tool names them (its Cardstocks enum); the order picks one for the whole project
STOCKS = {"S30": "(S30) Standard Smooth", "S33": "(S33) Superior Smooth", "S27": "(S27) Smooth", "M31": "(M31) Linen", "P10": "(P10) Plastic"}


def back_file(style, kind, backs_dir=None):
    """<backs>/<style>_<kind>.<ext>; falls back to any other style there, and villain/quest -> encounter."""
    backs_dir = backs_dir or BACKS
    styles = [style] + sorted({f.split("_", 1)[0] for f in os.listdir(backs_dir) if "_" in f} - {style}) if os.path.isdir(backs_dir) else [style]
    for st in styles:
        for k in ((kind, "encounter") if kind in ("villain", "quest") else (kind,)):
            for ext in ("jpg", "jpeg", "png"):
                p = os.path.join(backs_dir, f"{st}_{k}.{ext}")
                if os.path.exists(p):
                    return p
    return None


def back_styles(backs_dir=None):
    """Back styles available in a backs folder: the <style> part of <style>_<kind>.<ext>."""
    backs_dir = backs_dir or BACKS
    if not os.path.isdir(backs_dir):
        return []
    return sorted({f.split("_", 1)[0] for f in os.listdir(backs_dir) if "_" in f and f.lower().endswith((".jpg", ".jpeg", ".png"))})


def build_order(sel, launch=False):
    catalog, lib = load_catalog(), load_library()
    picked = resolve_selection(sel, catalog)
    style = sel.get("back", "original")
    items = []
    for pc in picked:
        if pc["qty"] <= 0:
            continue
        f = image_for(pc["front"], lib)
        b = find_image(pc["back"], lib, sides=False) if pc["back"] else None
        items.append({"front": os.path.join(LIB, f) if f else None, "back": os.path.join(LIB, b) if b else None,
                      "needs_back": bool(pc["back"]), "kind": back_kind(pc), "qty": pc["qty"], "name": pc["name"], "group": pc["group"]})
    return write_order(sel.get("name") or "order", items, BACKS, style, BACK_KINDS, sel, launch=launch)


def image_for(code, lib):
    return find_image(code, lib)


def write_order(name, items, backs_dir, style, back_kinds, sel, launch=False):
    """Write orders/<name>/ (images + order.xml) for a list of physical cards.

    items: [{"front": abs image path or None, "back": abs path or None, "needs_back": bool, "kind": back kind for a
            single-sided card, "qty": copies, "name", "group"}]. A card with no front image, or a two-sided card with no
            back image, is reported as missing and left out. Single-sided cards get backs_dir/<style>_<kind>.<ext>.
    """
    name = re.sub(r"[^\w\- ]+", "", name).strip() or "order"
    out = os.path.join(ORDERS, name)
    img_dir = os.path.join(out, "images")
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir)
    os.makedirs(img_dir, exist_ok=True)
    backs = {k: back_file(style, k, backs_dir) for k in back_kinds}
    for k, p in backs.items():
        if p:
            shutil.copy2(p, os.path.join(out, f"back_{k}{os.path.splitext(p)[1]}"))
    # absolute paths: the embedded autofill tool resolves "Local File" ids without changing directory
    img_abs = lambda n: os.path.join(img_dir, n)

    fronts, back_entries, missing, slot = [], {}, [], 0
    for it in items:
        f, b = it["front"], it["back"]
        if not f or (it["needs_back"] and not b):
            missing.append(it)
            continue
        shutil.copy2(f, img_abs(os.path.basename(f)))
        if b:
            shutil.copy2(b, img_abs(os.path.basename(b)))
            back_id = img_abs(os.path.basename(b))
        else:
            kind = it["kind"]
            bp = backs.get(kind)
            if not bp:
                raise RuntimeError(f"No {kind} card back found: put {os.path.basename(backs_dir)}/{style}_{kind}.jpg (or .png) "
                                   f"in {os.path.dirname(backs_dir)} before building an order")
            back_id = os.path.join(out, f"back_{kind}{os.path.splitext(bp)[1]}")
        for _ in range(it["qty"]):
            fronts.append((slot, img_abs(os.path.basename(f))))
            back_entries.setdefault(back_id, []).append(slot)
            slot += 1

    # the most common back becomes the order default; the rest are listed explicitly
    default_back = max(back_entries, key=lambda k: len(back_entries[k])) if back_entries else os.path.join(out, "back_player.jpg")

    def card(cid, slots):
        return ("    <card>\n"
                f"      <id>{escape(cid)}</id>\n"
                "      <sourceType>Local File</sourceType>\n"
                f"      <slots>{','.join(map(str, slots))}</slots>\n"
                f"      <name>{escape(os.path.basename(cid))}</name>\n"
                "    </card>\n")

    xml = ("<order>\n  <details>\n"
           f"    <quantity>{slot}</quantity>\n"
           f"    <stock>{STOCKS.get(sel.get('stock') or 'S30', STOCKS['S30'])}</stock>\n"
           "    <foil>false</foil>\n  </details>\n  <fronts>\n"
           + "".join(card(c, [s]) for s, c in fronts) + "  </fronts>\n  <backs>\n"
           + "".join(card(c, sl) for c, sl in back_entries.items() if c != default_back) + "  </backs>\n"
           f"  <cardback>{escape(default_back)}</cardback>\n</order>\n")
    open(os.path.join(out, "order.xml"), "w", encoding="utf-8").write(xml)
    exe = next((e for e in EXE_CANDIDATES if os.path.exists(e)), None)
    if exe and not os.path.exists(os.path.join(out, "autofill-windows.exe")):
        shutil.copy2(exe, os.path.join(out, "autofill-windows.exe"))
    json.dump({"selection": sel, "missing": [m["name"] for m in missing]},
              open(os.path.join(out, "selection.json"), "w"), indent=1)
    result = {"folder": out, "cards": slot, "unique": sum(1 for it in items if it["qty"] > 0) - len(missing),
              "missing": [f"{m['name']} ({m['group']})" for m in missing], "exe": bool(exe), "launched": False}
    if launch and exe and slot:
        subprocess.Popen(["cmd", "/c", "start", "", os.path.join(out, "autofill-windows.exe")], cwd=out)
        result["launched"] = True
    return result


if __name__ == "__main__":
    sel = json.load(open(sys.argv[1]))
    print(json.dumps(build_order(sel, launch="--launch" in sys.argv), indent=1))
