"""Selection -> physical cards -> order folder for the "sets" games (Arkham Horror, The Lord of the Rings).

A selection is {"game": "arkham", "sections": ["dwl/investigators", ...], "qty": {code: n}, "name": "...", "back": "original"}.
Sections are the catalog's per-pack groups (investigators, a class or sphere, an encounter set, a quest); every card in a
chosen section is picked at its printed copy count. Cards with no image in the game's library default to 0 copies, and
a two-sided card needs both sides. Per-card counts from the order list override that.
"""
import json, os
import games
import mc_order


def load_catalog(game):
    return json.load(open(games.paths(game)["catalog"], encoding="utf-8"))


def load_library(game):
    p = os.path.join(games.paths(game)["library"], "library.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def find_image(code, lib, game):
    """Library file (relative to the game's library folder) for a code, or None. Back sides are keyed "<code>~back"."""
    f = lib.get(code)
    return f if f and os.path.exists(os.path.join(games.paths(game)["library"], f)) else None


def section_index(catalog):
    out = {}
    for p in catalog["packs"]:
        for s in p["sections"]:
            out[s["code"]] = (p, s)
    return out


def resolve_selection(game, sel, catalog=None):
    catalog = catalog or load_catalog(game)
    lib = load_library(game)
    wanted = sel.get("sections") or []
    idx = section_index(catalog)
    picked, seen = [], set()
    for code in wanted:                                   # in the order the catalog lists them, not the click order
        pass
    for p in catalog["packs"]:
        for s in p["sections"]:
            if s["code"] not in set(wanted):
                continue
            for c in s["cards"]:
                if c["code"] in seen:
                    continue
                seen.add(c["code"])
                back = c["code"] + "~back" if c.get("back") else None
                pc = {"front": c["code"], "back": back, "name": c["name"], "type": c.get("type"), "faction": c.get("faction"),
                      "qty": c.get("qty", 1) or 1, "default_qty": c.get("qty", 1) or 1, "group": f"{p['name']} · {s['name']}",
                      "kind": s["kind"], "pack": p["code"], "section": s["code"], "sub": c.get("sub"), "xp": c.get("xp"),
                      "stage": c.get("stage"), "core_reprint": False, "dup_reprint": False, "also_in": [],
                      "revised": c.get("revised") or []}
                pc["have_front"] = bool(find_image(c["code"], lib, game))
                pc["have_back"] = bool(find_image(back, lib, game)) if back else True
                pc["have"] = pc["have_front"] and pc["have_back"]
                if not pc["have"]:
                    pc["qty"] = 0
                if pc["revised"] and (sel.get("opts") or {}).get("exclude_revised"):
                    pc["qty"] = 0                        # reprinted in a revised-edition product: left out unless asked for
                picked.append(pc)
    overrides = sel.get("qty") or {}
    for pc in picked:
        if pc["front"] in overrides:
            try:
                pc["qty"] = max(0, int(overrides[pc["front"]]))
            except (TypeError, ValueError):
                pass
    return picked


def back_kind(pc, game):
    kinds = games.get(game)["back_kinds"]
    k = pc.get("kind") or "encounter"
    return k if k in kinds else "encounter"


def build_order(game, sel, launch=False):
    g = games.get(game)
    paths = games.paths(game)
    picked = resolve_selection(game, sel)
    lib = load_library(game)
    style = sel.get("back", "original")
    items = []
    for pc in picked:
        if pc["qty"] <= 0:
            continue
        f = find_image(pc["front"], lib, game)
        b = find_image(pc["back"], lib, game) if pc["back"] else None
        items.append({"front": os.path.join(paths["library"], f) if f else None,
                      "back": os.path.join(paths["library"], b) if b else None, "needs_back": bool(pc["back"]),
                      "kind": back_kind(pc, game), "qty": pc["qty"], "name": pc["name"], "group": pc["group"]})
    name = sel.get("name") or g["order_name"]
    return mc_order.write_order(name, items, paths["backs"], style, g["back_kinds"], sel, launch=launch)
