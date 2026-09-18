"""Build games/arkham/catalog.json from ArkhamDB: what the app lets you pick for Arkham Horror: The Card Game.

cycles[]  : how the packs are grouped in the UI (a campaign cycle, the Return-to boxes, standalone scenarios, ...)
packs[]   : every product, in Proxy Nexus's order (release date), each split into sections: the player cards
            (investigators first) and one section per encounter set. Cards use ArkhamDB codes, which is also
            what Proxy Nexus names its exported images after.

The repackaged Investigator / Campaign Expansions (2021 onwards for the old cycles) contain exactly the cards of the
original deluxe box and its six Mythos packs, so they are not listed as packs of their own: the cycle notes them.

Run:  python ah_catalog.py            (fetches from arkhamdb.com; AH_CACHE=<dir> reuses downloaded json files)
"""
import json, os, sys, re
from collections import defaultdict
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "games", "arkham", "catalog.json")
RATINGS = os.path.join(HERE, "games", "arkham", "ratings.json")      # from ae_ratings.py (Ancient Evils reviews)
API = "https://arkhamdb.com/api/public"
UA = {"User-Agent": "Mozilla/5.0 (MC Autofill)"}

CLASSES = {"guardian": "Guardian", "seeker": "Seeker", "rogue": "Rogue", "mystic": "Mystic", "survivor": "Survivor",
           "neutral": "Neutral", "mythos": "Mythos"}


def fetch(name, url):
    cache = os.environ.get("AH_CACHE")
    p = os.path.join(cache, name) if cache else None
    if p and os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    r = requests.get(url, headers=UA, timeout=180)
    r.raise_for_status()
    if p:
        open(p, "w", encoding="utf-8").write(r.text)
    return r.json()


def cycle_of(pack):
    """(cycle code, cycle name, pack kind) from ArkhamDB's cycle_position / position."""
    cp, pos, name = pack["cycle_position"], pack["position"], pack["name"]
    if cp in (1, 12):
        return "core", "Core Set", "core"
    if 2 <= cp <= 11:
        if pack.get("reprint_type"):
            return f"c{cp}", None, "repackaged"
        kind = "deluxe" if pos == 1 else "mythos"
        if "Investigator Expansion" in name:
            kind = "investigators"
        elif "Campaign Expansion" in name:
            kind = "campaign"
        return f"c{cp}", None, kind
    if cp == 50:
        return "return", "Return to…", "return"
    if cp in (60, 61):
        return "starters", "Investigator starter decks", "starter"
    if cp == 70:
        return "standalone", "Standalone scenarios", "standalone"
    if cp == 80:
        return "promo", "Promos and novellas", "promo"
    if cp == 90:
        return "parallel", "Parallel investigators", "parallel"
    return "other", "Other", "other"


def main():
    packs = fetch("arkham_packs.json", f"{API}/packs/")
    cards = fetch("arkham_enc.json", f"{API}/cards/?encounter=1")
    cards = [c for c in cards if not c.get("hidden")]          # hidden = the back face of a double-sided card, indexed twice
    by_pack = defaultdict(list)
    for c in cards:
        by_pack[c["pack_code"]].append(c)

    ratings = json.load(open(RATINGS, encoding="utf-8")) if os.path.exists(RATINGS) else {}
    cycles, out_packs = {}, []
    for p in sorted(packs, key=lambda p: (p["cycle_position"], p["position"])):
        ccode, cname, kind = cycle_of(p)
        cy = cycles.setdefault(ccode, {"code": ccode, "name": cname, "packs": [], "notes": []})
        if kind == "deluxe" and not cy["name"]:
            cy["name"] = p["name"]
        if kind in ("investigators", "campaign") and not cy["name"]:
            cy["name"] = re.sub(r" (Investigator|Campaign) Expansion$", "", p["name"])
        if kind == "repackaged":
            cy["notes"].append(p["name"])
            continue
        pcards = sorted(by_pack.get(p["code"], []), key=lambda c: c["position"])
        if not pcards:
            continue
        sections = {}

        def section(code, name, skind, order):
            return sections.setdefault(code, {"code": f"{p['code']}/{code}", "name": name, "kind": skind, "order": order, "cards": []})

        for c in pcards:
            entry = {"code": c["code"], "name": c["name"], "type": c["type_code"], "faction": c.get("faction_code"),
                     "qty": c.get("quantity", 1) or 1, "back": bool(c.get("double_sided")), "pos": c["position"]}
            if c.get("subname"):
                entry["sub"] = c["subname"]
            if c.get("xp"):
                entry["xp"] = c["xp"]
            if c["code"] in ratings:
                entry["rating"] = ratings[c["code"]]["rating"]
                entry["rating_n"] = ratings[c["code"]]["n"]
            if c.get("encounter_code"):
                s = section("enc_" + c["encounter_code"], c.get("encounter_name") or c["encounter_code"], "encounter",
                            (3, c.get("encounter_position") or 0))
                entry["enc_pos"] = c.get("encounter_position")
            else:
                s = section("player", "Player cards", "player", (0, 0))      # investigators first (pack order), then the rest
            s["cards"].append(entry)
        secs = sorted(sections.values(), key=lambda s: (s["order"], s["name"]))
        for s in secs:
            s.pop("order")
        out_packs.append({"code": p["code"], "name": p["name"], "kind": kind, "date": p.get("available"), "cycle": ccode,
                          "sections": secs, "cards": sum(len(s["cards"]) for s in secs)})
        cy["packs"].append(p["code"])
    for cy in cycles.values():
        if cy["notes"]:
            cy["note"] = "Also sold as " + " + ".join(cy["notes"]) + " (same cards)"
        cy.pop("notes")
    cycles = [c for c in cycles.values() if c["packs"]]
    catalog = {"game": "arkham", "name": "Arkham Horror LCG", "cycles": cycles, "packs": out_packs,
               "back_groups": {"player": "player", "encounter": "encounter"},
               "options": [{"key": "min_rating", "type": "select", "label": "keep player cards rated",
                            "title": "Ancient Evils (derbk.com) rates every player card of the Core Sets, investigator expansions and "
                                     "starter decks: Bad < Okay < Good < Excellent < Staple. Choose a minimum: cards rated below it are set "
                                     "to 0 copies, cards at or above it keep their copies. Investigators, signature cards, weaknesses and "
                                     "cards the reviews do not cover are never affected.",
                            "choices": [["", "any (no filter)"], ["2", "Okay or better"], ["2.5", "Okay-to-Good or better"], ["3", "Good or better"],
                                        ["3.5", "Good-to-Excellent or better"], ["4", "Excellent or better"], ["5", "Staple only"]]}]}
    print(f"{sum(1 for p in out_packs for s in p['sections'] for c in s['cards'] if 'rating' in c)} cards carry an Ancient Evils rating")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(catalog, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{len(cycles)} cycles, {len(out_packs)} packs, {sum(p['cards'] for p in out_packs)} cards -> {OUT}")
    for cy in cycles:
        print(f"  {cy['name']:<34} {len(cy['packs'])} packs" + (f"  ({cy['note']})" if cy.get("note") else ""))


if __name__ == "__main__":
    main()
