"""Collect the Ancient Evils player-card ratings for Arkham Horror into games/arkham/ratings.json.

derbk.com/ancientevils reviews every investigator expansion (and the Core Sets and starter decks) card by card, with
the scale Bad < Okay < Good < Excellent < Staple, written as "<strong>Card(xp)</strong>: Good to Excellent." Each
review is fetched, the ratings are read off, and every card is matched to its ArkhamDB code(s) in the catalog by name,
level and, where the review says so, class. A code gets the rating of the review that covers its cycle.

Run:  python ae_ratings.py            (AE_CACHE=<dir> reuses downloaded html)   then  python ah_catalog.py
"""
import difflib, html, json, os, re, unicodedata
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(HERE, "games", "arkham", "catalog.json")
OUT = os.path.join(HERE, "games", "arkham", "ratings.json")
BASE = "https://derbk.com/ancientevils/investigator-expansion-review-"
UA = {"User-Agent": "Mozilla/5.0"}
# review page -> the catalog cycles / packs it covers (used to pick the right printing of a name)
PAGES = {
    "the-core": ["core"], "the-2026-core-set": ["core"], "dunwich": ["c2"], "carcosa": ["c3"], "forgotten-age": ["c4"],
    "circle-undone": ["c5"], "dream-eaters": ["c6"], "innsmouth": ["c7"], "edge-of-the-earth": ["c8"], "scarlet-keys": ["c9"],
    "the-feast-of-hemlock-vale": ["c10"], "the-drowned-city": ["c11"], "investigator-starter-decks": ["starters"],
    "the-evergreen-investigators": ["starters"],
}
LEVELS = {"Bad": 1, "Okay": 2, "Good": 3, "Excellent": 4, "Staple": 5}
WORD = r"(?:Bad|Okay|Good|Excellent|Staple)"
ENTRY = re.compile(r"<strong>((?:(?!</strong>).)*?)</strong>\s*:\s*(" + WORD + r"(?:\s*(?:to|/)\s*" + WORD + r")?)\b", re.S)


def norm(s):
    s = html.unescape(s).replace("\u2019", "'").replace("\u2018", "'").replace("'", "")     # Rabbit's / Rabbit’s -> rabbits
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# review spellings that differ from ArkhamDB's card names
ALIASES = {"medical text": "medical texts", "sharp rethoric": "sharp rhetoric", "brand of cthuga": "brand of cthugha",
           "mk1 grenades": "mk 1 grenades", "joey the rat": "joey the rat vigil", "the rat": "joey the rat vigil",
           "whitton green": "whitton greene", "45 auto": "45 automatic", "thompson submachine gun": "45 thompson",
           "miss doyle and the cat army": "miss doyle", "remington 1859": "remington model 1858", "ive had worse": "ive had worse",
           "the desperate skills": None}


def resolve(name, by_name, pool):
    """Catalog cards for a review's card name: exact, then alias, then the one card whose name contains all its words,
    then the closest spelling in the review's cycle."""
    key = norm(name)
    if key in ALIASES:
        if ALIASES[key] is None:
            return []
        key = ALIASES[key]
    if by_name.get(key):
        return by_name[key]
    if "/" in name and by_name.get(norm(name.split("/")[0])):                 # "Empty Vessel/Wish Eater": the front face
        return by_name[norm(name.split("/")[0])]
    if " and " in name and all(by_name.get(norm(x)) for x in name.split(" and ")):
        return [c for x in name.split(" and ") for c in by_name[norm(x)]]     # "Painkillers and Smoking Pipe"
    words = set(key.split())
    names = {norm(c["name"]) for c in pool}
    sub = [n for n in names if words <= set(n.split())]
    if len(sub) == 1:
        return by_name[sub[0]]
    close = difflib.get_close_matches(key, list(names), n=1, cutoff=0.86)
    return by_name[close[0]] if close else []


def fetch(slug):
    cache = os.environ.get("AE_CACHE")
    p = os.path.join(cache, slug + ".html") if cache else None
    if p and os.path.exists(p):
        return open(p, encoding="utf-8", errors="ignore").read()
    r = requests.get(BASE + slug + "/", headers=UA, timeout=120)
    r.raise_for_status()
    if p:
        open(p, "w", encoding="utf-8").write(r.text)
    return r.text


def parse(page):
    """[(name, xp or None, class or None, rating text, numeric)] and the ArkhamDB codes pictured on the page."""
    body = page.split("<article", 1)[1].split("</article>", 1)[0] if "<article" in page else page
    body = body.split("<h2", 1)[1] if "<h2" in body else body           # skip the intro
    out = []
    for raw, rating in ENTRY.findall(body):
        name = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip().rstrip(":").strip()
        xp, cls = None, None
        m = re.search(r"\(([^)]*)\)\s*$", name)
        if m:
            inside = m.group(1)
            parts = [x.strip() for x in inside.split(",")]
            if parts and re.fullmatch(r"\d+\s*(?:Ex|XP)?", parts[0], re.I):      # "(3)", "(3Ex)" = level 3, exceptional
                xp = int(re.match(r"\d+", parts[0]).group()); parts = parts[1:]
            elif parts and parts[0].upper() == "C":          # customizable card
                parts = parts[1:]
            if parts and parts[0].lower() in ("guardian", "seeker", "rogue", "mystic", "survivor", "neutral"):
                cls = parts[0].lower(); parts = parts[1:]
            if xp is not None or cls is not None or inside.upper() == "C":
                name = name[:m.start()].strip()
        words = [w.strip() for w in re.split(r"\s*(?:to|/)\s*", rating)]
        n = sum(LEVELS[w] for w in words) / len(words)
        out.append((name, xp, cls, rating, n))
    codes = set(re.findall(r"arkhamdb\.com/bundles/cards/(\d{5})", body))
    return out, codes


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    cycle_of = {p["code"]: p["cycle"] for p in cat["packs"]}
    cards = [dict(c, pack=p["code"], cycle=p["cycle"]) for p in cat["packs"] for s in p["sections"] if s["kind"] == "player" for c in s["cards"]]
    by_name = {}
    for c in cards:
        by_name.setdefault(norm(c["name"]), []).append(c)
    ratings, unmatched, n_entries = {}, [], 0
    for slug, cycles in PAGES.items():
        entries, pictured = parse(fetch(slug))
        n_entries += len(entries)
        for name, xp, cls, rating, n in entries:
            pool = [c for c in cards if c["cycle"] in cycles and c["type"] != "investigator"]
            cands = [c for c in resolve(name, by_name, pool) if c["type"] != "investigator"]
            if xp is not None:
                cands = [c for c in cands if (c.get("xp") or 0) == xp]
            if cls:
                cands = [c for c in cands if c.get("faction") == cls]
            in_cycle = [c for c in cands if c["cycle"] in cycles]
            on_page = [c for c in cands if c["code"] in pictured]
            pick = in_cycle or on_page or cands
            if not pick:
                unmatched.append((slug, name, xp, cls, rating))
                continue
            if len({(c["name"], c.get("xp"), c.get("faction")) for c in pick}) > 1 and xp is None:
                pick = [c for c in pick if not c.get("xp")] or pick        # unnumbered = the level-0 version
            for c in pick:
                ratings[c["code"]] = {"rating": rating, "n": round(n, 1), "page": slug}
    json.dump(dict(sorted(ratings.items())), open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"{n_entries} rated entries on {len(PAGES)} pages -> {len(ratings)} card codes rated, {len(unmatched)} entries unmatched -> {OUT}")
    for u in unmatched:
        print("   unmatched:", u)


if __name__ == "__main__":
    main()
