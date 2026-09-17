"""Build catalog.json from MarvelCDB data: what the app lets you pick.

heroes[]      : one per hero (hero + alter-ego + hero-specific cards + nemesis set), with the pack it came in
packs[]       : every product; for hero packs the aspect/basic cards it adds; for campaign boxes the campaign,
                villain sets, modular sets and their cards
"""
import json, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
cards = json.load(open(os.path.join(HERE, "marvelcdb_cards.json"), encoding="utf-8"))
cards = [c for c in cards]  # keep "hidden" entries: they are the back sides of double-sided cards
# MarvelCDB occasionally lists one printing twice under a foreign code (e.g. Shang-Chi 10098 and 04098 both in the
# Rise of Red Skull Taskmaster set); keep the entry whose code numbering matches its pack.
from collections import Counter as _Counter
_prefix = {}
for c in cards:
    _prefix.setdefault(c["pack_code"], _Counter())[c["code"][:2]] += 1
_seen = {}
_keep = []
for c in cards:
    key = (c["pack_code"], c.get("card_set_code"), c["name"], c["type_code"], str(c.get("stage")), c["code"].rstrip("abcd"))
    native = c["code"][:2] == _prefix[c["pack_code"]].most_common(1)[0][0]
    key2 = (c["pack_code"], c.get("card_set_code"), c["name"], c["type_code"], str(c.get("stage")))
    if key2 in _seen and not native and c["code"][-1] not in "abcd":
        continue
    if key2 in _seen and native and c["code"][-1] not in "abcd" and not _seen[key2]:
        _keep = [k for k in _keep if not (k["pack_code"], k.get("card_set_code"), k["name"], k["type_code"], str(k.get("stage"))) == key2]
    _seen[key2] = _seen.get(key2, False) or native
    _keep.append(c)
cards = _keep
by_set = defaultdict(list)
for c in cards:
    by_set[c.get("card_set_code")].append(c)

def slim(c):
    return {"code": c["code"], "name": c["name"], "type": c["type_code"], "faction": c.get("faction_code"),
            "qty": c.get("quantity", 1), "double": bool(c.get("double_sided")), "linked": c.get("linked_to_code")}

heroes = []
_seen_sets = set()
for h in sorted((c for c in cards if c["type_code"] == "hero"), key=lambda c: (c["name"], c["code"])):
    if h["card_set_code"] in _seen_sets:
        continue                      # multi-form heroes (Ant-Man, Wasp, Angel/Archangel, Ironheart) are one hero, one tile
    _seen_sets.add(h["card_set_code"])
    hs = by_set[h["card_set_code"]]
    nem = by_set.get(h["card_set_code"] + "_nemesis", [])
    alter = next((c["name"] for c in hs if c["type_code"] == "alter_ego"), "")
    heroes.append({"name": h["name"], "alter_ego": alter, "set": h["card_set_code"], "pack": h["pack_code"], "pack_name": h["pack_name"],
                   "hero_cards": [slim(c) for c in hs], "nemesis_cards": [slim(c) for c in nem]})

packs = {}
for c in cards:
    p = packs.setdefault(c["pack_code"], {"code": c["pack_code"], "name": c["pack_name"], "heroes": [], "player_cards": [],
                                          "encounter_sets": {}})
    st = c.get("card_set_type_name_code")
    if st == "hero":
        if c["card_set_code"] not in p["heroes"]: p["heroes"].append(c["card_set_code"])
    elif st == "nemesis":
        pass  # travels with its hero
    elif st is None and c.get("faction_code") in ("aggression", "justice", "leadership", "protection", "basic", "pool", "campaign"):
        p["player_cards"].append(slim(c))
    else:
        key = c.get("card_set_code") or f"{c['pack_code']}_loose"
        es = p["encounter_sets"].setdefault(key, {"code": key, "name": c.get("card_set_name") or "Other", "kind": st or "other", "cards": []})
        es["cards"].append(slim(c))
for p in packs.values():
    p["encounter_sets"] = list(p["encounter_sets"].values())

# product kind: hero pack / campaign box / scenario pack / core
def kind(p):
    if p["code"] == "core": return "core"
    if p["heroes"] and any(es["kind"] in ("villain", "main_scheme", "leader") for es in p["encounter_sets"]) and len(p["heroes"]) >= 2: return "campaign"
    if len(p["heroes"]) >= 2: return "campaign"
    if p["heroes"]: return "hero"
    return "scenario"
for p in packs.values():
    p["kind"] = kind(p)

catalog = {"heroes": heroes, "packs": sorted(packs.values(), key=lambda p: (["core", "campaign", "scenario", "hero"].index(p["kind"]), p["name"]))}
json.dump(catalog, open(os.path.join(HERE, "catalog.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

from collections import Counter
print(len(heroes), "heroes;", len(packs), "packs:", dict(Counter(p["kind"] for p in packs.values())))
for p in catalog["packs"]:
    if p["kind"] in ("core", "campaign", "scenario"):
        n_enc = sum(len(es["cards"]) for es in p["encounter_sets"])
        print(f"  [{p['kind']:8}] {p['name']:<28} heroes={len(p['heroes'])} player={len(p['player_cards'])} enc_sets={len(p['encounter_sets'])} enc_cards={n_enc}")
