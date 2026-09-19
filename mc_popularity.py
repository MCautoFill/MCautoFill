"""Score Marvel Champions aspect and basic cards by how often MarvelCDB decklists play them -> mc_popularity.json.

There is no site that rates Marvel Champions player cards one by one, so this builds the same kind of measure RingsDB
publishes for The Lord of the Rings: for every aspect / basic card, the share of decklists that could have used it
(same aspect, published after the card's pack came out) and actually did. The share becomes a 0-10 score on fixed
breakpoints chosen from what the numbers mean in practice: the staples every deck of an aspect runs (Helicarrier,
Team Training, Skilled Investigator) sit at 30% and above = 10, the well-known good cards (Hawkeye, Indomitable,
Quincarrier) around 15-25% = 8-9, ordinary cards at 4-8% = 4-5, and cards under 2% of decks = 1-2. Basic cards
compete for slots in every deck and run about a third lower, so they are judged on a proportionally lower scale.
Hero cards are not scored: they come with the hero.

Decklists are read day by day from https://marvelcdb.com/api/public/decklists/by_date/<date>, which is slow, so each
day is cached under MC_CACHE (default: .cache/marvelcdb/ next to this file) and only new days are fetched.

Run:  python mc_popularity.py [--years 2]     then  python mc_catalog.py
"""
import argparse, datetime as dt, json, os, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "mc_popularity.json")
API = "https://marvelcdb.com/api/public"
UA = {"User-Agent": "Mozilla/5.0 (MC Autofill)"}
ASPECTS = {"aggression", "justice", "leadership", "protection", "pool"}
PLAYER_FACTIONS = ASPECTS | {"basic"}
# score -> minimum share of eligible decks (aspect cards); basic cards use the same table scaled by BASIC_FACTOR
BREAKPOINTS = [(10, 0.30), (9, 0.22), (8, 0.16), (7, 0.12), (6, 0.09), (5, 0.065), (4, 0.045), (3, 0.03), (2, 0.015), (1, 0.0001)]
BASIC_FACTOR = 0.7


def score(rate, faction):
    if rate is None:
        return None
    f = BASIC_FACTOR if faction == "basic" else 1.0
    for n, cut in BREAKPOINTS:
        if rate >= cut * f:
            return n
    return 0


def cache_dir():
    d = os.environ.get("MC_CACHE") or os.path.join(HERE, ".cache", "marvelcdb")
    os.makedirs(d, exist_ok=True)
    return d


def get_json(url, tries=4):
    for attempt in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return []
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}")


def fetch_days(days, log=print):
    """Decklists for each date, from the cache or MarvelCDB. Today's file is refetched (it is still growing)."""
    d = cache_dir()
    today = dt.date.today().isoformat()
    todo = [day for day in days if day == today or not os.path.exists(os.path.join(d, day + ".json"))]
    done = [0]

    def fetch_one(day):
        data = get_json(f"{API}/decklists/by_date/{day}")
        json.dump(data, open(os.path.join(d, day + ".json"), "w", encoding="utf-8"))
        done[0] += 1
        if done[0] % 50 == 0:
            log(f"  fetched {done[0]}/{len(todo)} days")
    if todo:
        log(f"  {len(todo)} days to fetch ({len(days) - len(todo)} cached)")
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(fetch_one, todo))
    out = []
    for day in days:
        out.extend(json.load(open(os.path.join(d, day + ".json"), encoding="utf-8")))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=2.0, help="how far back to read decklists (default 2 years)")
    args = ap.parse_args(argv)
    cards = json.load(open(os.path.join(HERE, "marvelcdb_cards.json"), encoding="utf-8"))
    packs = {p["code"]: p for p in get_json(f"{API}/packs/")}
    released = {code: (packs.get(c["pack_code"]) or {}).get("available") or "" for code, c in ((c["code"], c) for c in cards)}
    player = [c for c in cards if c.get("faction_code") in PLAYER_FACTIONS and c.get("type_code") not in ("hero", "alter_ego")]
    # reprints share a score: every code of the same (name, faction, type) is one card
    family = {c["code"]: (c["name"], c["faction_code"], c["type_code"]) for c in player}
    first_release = defaultdict(lambda: "9999")
    for c in player:
        first_release[family[c["code"]]] = min(first_release[family[c["code"]]], released[c["code"]] or "9999")

    end = dt.date.today()
    start = end - dt.timedelta(days=int(365 * args.years))
    days = [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    print(f"reading decklists from {days[0]} to {days[-1]} ({len(days)} days)…")
    decks = fetch_days(days)
    print(f"{len(decks)} decklists")

    by_aspect = defaultdict(list)          # aspect -> [(date, set of card families)]
    for dk in decks:
        try:
            meta = json.loads(dk.get("meta") or "{}")
        except ValueError:
            meta = {}
        aspects = meta.get("aspect") or meta.get("aspects") or ""
        aspects = {a.strip() for a in str(aspects).split(",") if a.strip()} & ASPECTS
        date = (dk.get("date_creation") or "")[:10]
        fams = {family[code] for code in dk.get("slots", {}) if code in family}
        for a in aspects or {"?"}:
            by_aspect[a].append((date, fams))

    scores = {}
    for fam in set(family.values()):
        name, faction, _ = fam
        pool = [d for a in (ASPECTS if faction == "basic" else {faction}) for d in by_aspect.get(a, [])]
        eligible = [d for d in pool if d[0] >= first_release[fam]]
        used = sum(1 for d in eligible if fam in d[1])
        scores[fam] = {"decks": used, "eligible": len(eligible), "rate": round(used / len(eligible), 4) if eligible else None}
    out = {}
    for c in player:
        s = scores[family[c["code"]]]
        out[c["code"]] = {"popularity": score(s["rate"], c["faction_code"]), **s}
    json.dump({"generated": end.isoformat(), "decklists": len(decks), "since": days[0],
               "breakpoints": {str(n): cut for n, cut in BREAKPOINTS}, "basic_factor": BASIC_FACTOR, "cards": out},
              open(OUT, "w", encoding="utf-8"), indent=1)
    dist = defaultdict(int)
    for v in out.values():
        dist[v["popularity"]] += 1
    print(f"{len(out)} aspect/basic card codes scored (10 = played in 30%+ of eligible decks) -> {OUT}")
    print("  distribution:", dict(sorted(dist.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))))
    top = sorted(((v["rate"] or 0, c["name"], c["faction_code"]) for c in player for v in [out[c["code"]]]), reverse=True)
    seen, shown = set(), []
    for r, n, f in top:
        if (n, f) not in seen:
            seen.add((n, f)); shown.append(f"{n} ({f}, {r:.0%})")
        if len(shown) == 10:
            break
    print("  most played:", "; ".join(shown))


if __name__ == "__main__":
    main()
