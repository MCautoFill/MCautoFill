"""Build games/lotr/catalog.json for The Lord of the Rings: The Card Game.

Card and pack ids come from Proxy Nexus (games/lotr/proxynexus_lotr.json, extracted from the database its web app
loads), because those ids are what Proxy Nexus names its exported images after. Hall of Beorn's exports add what
the ids lack: card type, sphere, encounter set, quest stages and copy counts. RingsDB's pack list gives the cycle
each pack belongs to.

cycles[] : deluxe expansion + its adventure packs, the sagas, standalone scenarios, ALeP, nightmare decks...
packs[]  : every product, split into sections: the player cards (heroes first), quests, encounter sets.

Run:  python lotr_catalog.py          (LOTR_CACHE=<dir> reuses downloaded json files)
"""
import json, os, re, unicodedata
from collections import defaultdict
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
GDIR = os.path.join(HERE, "games", "lotr")
OUT = os.path.join(GDIR, "catalog.json")
UA = {"User-Agent": "Mozilla/5.0 (MC Autofill)"}
HOB = "http://hallofbeorn.com/Export/"

# RingsDB cycle_position -> (cycle code, name). Deluxe boxes and their adventure packs share a cycle.
CYCLES = {
    1: ("core", "Core Set"), 2: ("core", "Core Set"),
    10: ("mirkwood", "Shadows of Mirkwood"),
    11: ("khazad", "Khazad-dûm / Dwarrowdelf"), 12: ("khazad", "Khazad-dûm / Dwarrowdelf"),
    13: ("numenor", "Heirs of Númenor / Against the Shadow"), 14: ("numenor", "Heirs of Númenor / Against the Shadow"),
    15: ("isengard", "The Voice of Isengard / The Ring-maker"), 16: ("isengard", "The Voice of Isengard / The Ring-maker"),
    17: ("angmar", "The Lost Realm / Angmar Awakened"), 18: ("angmar", "The Lost Realm / Angmar Awakened"), 19: ("angmar", "The Lost Realm / Angmar Awakened"),
    20: ("dreamchaser", "The Grey Havens / Dream-chaser"), 21: ("dreamchaser", "The Grey Havens / Dream-chaser"), 22: ("dreamchaser", "The Grey Havens / Dream-chaser"),
    23: ("harad", "The Sands of Harad / Haradrim"), 24: ("harad", "The Sands of Harad / Haradrim"),
    25: ("eredmithrin", "The Wilds of Rhovanion / Ered Mithrin"), 26: ("eredmithrin", "The Wilds of Rhovanion / Ered Mithrin"), 27: ("eredmithrin", "The Wilds of Rhovanion / Ered Mithrin"),
    28: ("mordor", "A Shadow in the East / Vengeance of Mordor"), 29: ("mordor", "A Shadow in the East / Vengeance of Mordor"),
    30: ("alep", "ALeP – A Long-extended Party"), 31: ("alep", "ALeP – A Long-extended Party"), 32: ("alep", "ALeP – A Long-extended Party"), 33: ("alep", "ALeP – A Long-extended Party"),
    40: ("hobbit", "The Hobbit saga"), 41: ("lotrsaga", "The Lord of the Rings saga"),
    50: ("standalone", "Standalone scenarios"), 60: ("starters", "Starter decks"), 61: ("starters", "Starter decks"),
    70: ("motk", "Messenger of the King"),
}
CYCLE_ORDER = ["core", "mirkwood", "khazad", "numenor", "isengard", "angmar", "dreamchaser", "harad", "eredmithrin", "mordor",
               "hobbit", "lotrsaga", "standalone", "starters", "motk", "alep", "nightmare", "other"]
SPHERES = ["Leadership", "Tactics", "Spirit", "Lore", "Neutral", "Baggins", "Fellowship"]
# the 2022+ repackaged line: player cards printed here are reprints of older packs (matched by title, type and sphere)
REVISED = ["Revised Core Set", "Angmar Awakened Hero Expansion", "Angmar Awakened Campaign Expansion", "Dream-chaser Hero Expansion",
           "Dream-chaser Campaign Expansion", "Ered Mithrin Hero Expansion", "Ered Mithrin Campaign Expansion", "The Fellowship of the Ring",
           "The Two Towers", "The Return of the King", "Dwarves of Durin", "Elves of Lórien", "Defenders of Gondor", "Riders of Rohan"]
PLAYER_TYPES = {"Hero", "Ally", "Attachment", "Event", "Player_Side_Quest", "Contract", "Treasure"}
QUEST_TYPES = {"Quest", "Campaign", "Nightmare_Setup", "GenCon_Setup"}


def norm(s):
    """Proxy Nexus's normalize_title: ascii-fold, lower-case, every other character becomes one underscore."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "_", s)


# packs whose Proxy Nexus / Hall of Beorn name does not match a RingsDB pack name
CYCLE_OVERRIDES = {
    "the hobbit: over hill and under hill": "hobbit", "the hobbit: on the doorstep": "hobbit",
    "the fellowship of the ring": "lotrsaga", "the two towers": "lotrsaga", "the return of the king": "lotrsaga",
    "angmar awakened hero expansion": "angmar", "dream-chaser hero expansion": "dreamchaser", "ered mithrin hero expansion": "eredmithrin",
    "two-player limited edition starter": "starters", "the dark of mirkwood": "standalone",
}


def canon(name):
    """Proxy Nexus's canonical pack name: no 'ALeP - ' prefix, no '.English' suffix, no 'Nightmare Deck' suffix."""
    n = re.sub(r"^ALeP - ", "", name).replace(".English", "").strip()
    return n


def fetch(name, url):
    cache = os.environ.get("LOTR_CACHE")
    p = os.path.join(cache, name) if cache else None
    if p and os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    if p:
        open(p, "w", encoding="utf-8").write(r.text)
    return r.json()


def main():
    pn = json.load(open(os.path.join(GDIR, "proxynexus_lotr.json"), encoding="utf-8"))
    hob = fetch("hob_PlayerCards.json", HOB + "PlayerCards") + fetch("hob_EncounterCards.json", HOB + "EncounterCards") \
        + fetch("hob_QuestCards.json", HOB + "QuestCards")
    alep = fetch("hob_ALeP.json", HOB + "ALeP")
    rpacks = fetch("rings_packs.json", "https://ringsdb.com/api/public/packs/")

    hob_by_slug = {norm(c["Slug"]): c for c in hob}
    revised_key = lambda c: (norm(c["Title"]), c["CardType"], c.get("Sphere") or "")
    reprinted = defaultdict(set)                        # (title, type, sphere) -> revised products that print it
    for c in hob:
        if c["CardSet"] in REVISED and c["CardType"] in PLAYER_TYPES:
            reprinted[revised_key(c)].add(c["CardSet"])
    alep_by_id = {}
    for c in alep:                                     # RingsDB-style export; ALeP ids are norm("<name>-<pack id>")
        pid = norm(canon(c["pack_name"]))
        alep_by_id.setdefault(norm(f"{c['name']}-{pid}"), c)
    cycle_by_pack = {}
    for rp in rpacks:
        cycle_by_pack[norm(canon(rp["name"]))] = CYCLES.get(rp["cycle_position"], ("other", "Other"))

    strip = lambda s: s[len("lotrlcg_"):] if s.startswith("lotrlcg_") else s
    pn_cards = {c["id"]: c for c in pn["cards"]}
    versions_by_pack = defaultdict(list)
    for v in pn["versions"]:
        versions_by_pack[v["pack_id"]].append(v)

    cycles = {}
    out_packs = []
    packs_sorted = sorted(pn["packs"], key=lambda p: (p.get("date_release") is None, p.get("date_release") or "", p["name"]))
    for p in packs_sorted:
        pcode = strip(p["id"])
        is_nm = p["name"].endswith(" Nightmare")
        is_alep = p["name"].startswith("ALeP - ")
        if is_nm:
            ccode, cname = "nightmare", "Nightmare decks"
        elif is_alep:
            ccode, cname = "alep", "ALeP – A Long-extended Party"
        else:
            base = re.sub(r" Preorder Promotion$", "", p["name"])
            ccode, cname = cycle_by_pack.get(norm(canon(base)), (None, None))
            if p["name"].lower() in CYCLE_OVERRIDES:
                ccode = CYCLE_OVERRIDES[p["name"].lower()]
                cname = next(n for c, n in CYCLES.values() if c == ccode)
            if not ccode:
                ccode, cname = "other", "Other"
        cy = cycles.setdefault(ccode, {"code": ccode, "name": cname, "packs": []})
        sections = {}

        def section(code, name, skind, order):
            return sections.setdefault(code, {"code": f"{pcode}/{code}", "name": name, "kind": skind, "order": order, "cards": []})

        vs = sorted(versions_by_pack.get(p["id"], []), key=lambda v: (v.get("position") is None, v.get("position") or 0))
        hero_first = lambda v: 0 if (hob_by_slug.get(v["api_id"]) or {}).get("CardType") == "Hero" else 1
        vs.sort(key=hero_first)
        for v in vs:
            card = pn_cards.get(v["card_id"])
            if not card:
                continue
            code = strip(card["id"])
            h = hob_by_slug.get(v["api_id"]) if v.get("api_id") else None
            a = alep_by_id.get(code) if not h else None
            ctype = (h["CardType"] if h else (a["type_code"].replace("-", "_").title() if a else None))
            if a and ctype:
                ctype = {"Encounter_Side_Quest": "Encounter_Side_Quest", "Player_Side_Quest": "Player_Side_Quest"}.get(ctype, ctype)
            sphere = (h.get("Sphere") if h else (a.get("sphere_name") if a else None))
            enc = (h.get("EncounterInfo") or {}).get("EncounterSet") if h else None
            qty = (h.get("Quantity") if h else (a.get("quantity") if a else None)) or v.get("quantity") or 1
            back = bool(h and h.get("Back")) or ctype in ("Quest", "Campaign") or (a is not None and a["type_code"] == "quest")
            # Proxy Nexus spells reprints apart with the pack's abbreviation: "Gandalf (Core)", "Bilbo Baggins (THOHaUH)"
            title = re.sub(r"\s*\((?:Core|RevCore|[A-Za-z0-9]{2,10})\)$", "", card["title"]) if h else card["title"]
            entry = {"code": code, "name": title, "type": (ctype or "").lower() or "unknown", "faction": (sphere or "").lower() or None,
                     "qty": qty, "back": back, "pos": v.get("position")}
            if h and h.get("Front", {}).get("Subtitle"):
                entry["sub"] = h["Front"]["Subtitle"]
            if h and ctype in PLAYER_TYPES and h["CardSet"] not in REVISED and revised_key(h) in reprinted:
                entry["revised"] = sorted(reprinted[revised_key(h)])
            if h and (h.get("EncounterInfo") or {}).get("StageNumber"):
                entry["stage"] = f"{h['EncounterInfo']['StageNumber']}{h['EncounterInfo'].get('StageLetter') or ''}"
            bg = card.get("back_group") or "encounter"
            if ctype in PLAYER_TYPES or (not ctype and bg == "player"):
                s = section("player", "Player cards", "player", (0, 0))     # heroes first, then by pack position
            elif ctype in QUEST_TYPES or (not ctype and bg == "quest"):
                label = enc or ("Campaign" if ctype == "Campaign" else "Quests")
                s = section("quest_" + norm(label), f"Quest: {label}" if ctype == "Quest" else label, "quest", (2, 0))
            else:
                label = enc or "Encounter cards"
                s = section("enc_" + norm(label), label, "encounter", (3, 0))
            s["cards"].append(entry)
        if not sections:
            continue
        secs = sorted(sections.values(), key=lambda s: (s["order"], s["name"]))
        for s in secs:
            s.pop("order")
        kind = "nightmare" if is_nm else ("alep" if is_alep else ("saga" if ccode in ("hobbit", "lotrsaga") else "pack"))
        out_packs.append({"code": pcode, "name": p["name"], "kind": kind, "date": p.get("date_release"), "cycle": ccode,
                          "sections": secs, "cards": sum(len(s["cards"]) for s in secs)})
        cy["packs"].append(pcode)
    cycles = sorted((c for c in cycles.values() if c["packs"]), key=lambda c: CYCLE_ORDER.index(c["code"]) if c["code"] in CYCLE_ORDER else 99)
    catalog = {"game": "lotr", "name": "The Lord of the Rings LCG", "cycles": cycles, "packs": out_packs,
               "back_groups": {"player": "player", "encounter": "encounter", "quest": "quest"},
               "options": [{"key": "exclude_revised", "label": "exclude player cards reprinted in the revised editions",
                            "title": "Player cards from older packs that were printed again in the Revised Core Set, the Angmar Awakened / "
                                     "Dream-chaser / Ered Mithrin Hero and Campaign Expansions, the repackaged sagas or the four starter "
                                     "decks are set to 0 copies. Encounter and quest cards are never affected."}]}
    json.dump(catalog, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n_unknown = sum(1 for p in out_packs for s in p["sections"] for c in s["cards"] if c["type"] == "unknown")
    print(f"{len(cycles)} cycles, {len(out_packs)} packs, {sum(p['cards'] for p in out_packs)} cards ({n_unknown} with no type info) -> {OUT}")
    for cy in cycles:
        print(f"  {cy['name']:<44} {len(cy['packs'])} packs")


if __name__ == "__main__":
    main()
