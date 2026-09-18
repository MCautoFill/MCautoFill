r"""Import the Drive scans into the library.

    python mc_import.py <folder-or-zip> [more...] [--dry]     # e.g. python mc_import.py "..\Heros-*.zip"

For every image found (TIFF/PNG/JPG; zips are read in place, nothing is extracted to disk):
  1. work out which MarvelCDB card it is from the file name and the folders it sits in,
  2. convert it to an MPC-ready JPG with bleed (mc_format.py) into library/<code>.jpg,
  3. record code -> file in library/library.json; scans MarvelCDB does not index go to library/extra.json
     (and show up in the app as "(from scans)" sets); guesses go to library/notes.txt, failures to unmatched.txt.
Already-converted codes are skipped, so it can be re-run on new zips as they arrive.

Drive naming seen so far:
  Heros/<Alter Ego>_<Hero>/<Aspect>_<Card Name>_<Type>_<n>.tiff             aspect/basic cards in a hero pack
  Heros/<Alter Ego>_<Hero>/<Hero>_<Card Name>_<Type>_<n>_<x.15>.tiff        hero-specific cards
  Heros/<Alter Ego>_<Hero>/<Alter Ego>_<Hero>_Hero_1a.tiff / _Alter-Ego_1b.tiff
  Heros/<Alter Ego>_<Hero>/<Hero> Nemesis/<Hero>_<Name>_<Type>_<n>.tiff     nemesis set
  Expansion Campaings/<Box>/<Encounter Set>/<n>_<Name>_<Type>.tiff          encounter cards (folder = set)
  .../<n>_<I|II|III>_<Villain>_Villain.tiff                                 villain stages
  .../<n>_<Name>_Main Scheme_1A.tiff / _Side A.tiff / _Side B.tiff          double-sided cards
  .../<Set>_<Name>_<Type>_<n>_<x.16>.tiff                                   set-prefixed encounter cards
  .../<Aspect>_<Ally> (<Subname>)_Ally_<n>.tiff                              allies with a subname
  .../<Hero>_Hero Giant_1c.tiff, V2_<Alter Ego>_<Hero>_Alter_ego_2b.tiff     multi-form / multi-version identities
"""
import glob, json, os, re, sys, unicodedata, zipfile
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import mc_format

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "library")
os.makedirs(LIB, exist_ok=True)
IMG_EXT = (".tif", ".tiff", ".png", ".jpg", ".jpeg")
TYPE_WORDS = {"hero": "hero", "alter-ego": "alter_ego", "alterego": "alter_ego", "alter ego": "alter_ego", "ally": "ally",
              "event": "event", "upgrade": "upgrade", "support": "support", "resource": "resource", "obligation": "obligation",
              "minion": "minion", "treachery": "treachery", "attachment": "attachment", "villain": "villain",
              "side scheme": "side_scheme", "sidescheme": "side_scheme", "main scheme": "main_scheme", "mainscheme": "main_scheme",
              "environment": "environment", "player side scheme": "player_side_scheme", "players side scheme": "player_side_scheme",
              "leader": "leader", "means": "evidence_means", "motive": "evidence_motive", "opportunity": "evidence_opportunity",
              "oppurtunity": "evidence_opportunity", "main showdown": "main_scheme"}
ASPECTS = {"aggression", "justice", "leadership", "protection", "basic", "pool", "campaign"}
ROMAN = {"i": "I", "ii": "II", "iii": "III", "iv": "IV", "v": "V"}
SKIP_FOLDERS = {"expansion campaings", "expansion campaigns", "marvel champions", "heros", "heroes", "core set", "modular sets", "scenario packs",
                "aspects", "villains", "villain", "modular", "campaign", "encounter", "player", "player cards", "encounter cards",
                "additional cards", "nemesis"}
NOT_A_CARD = re.compile(r"back for cards|test$|(?<![A-Za-z])back$", re.I)
DECK_LIST = re.compile(r"deck ?list|decklist|little rules|rules card", re.I)
KNOWN_NAMES = set()   # filled by Matcher: normalised card names, so a card called "Aero" is never read as the type "hero"


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


def load_cards():
    return json.load(open(os.path.join(HERE, "marvelcdb_cards.json"), encoding="utf-8"))


def clean_stem(fname):
    """Undo the file-name mangling seen in the scans."""
    s = re.sub(r"_s ", "'s ", fname)                 # Taskmaster_s Shield
    s = re.sub(r"_ (?=[A-Z])", "' ", s)              # Crossbones_ Machine Gun
    s = re.sub(r"[Aa]lter_[Ee]go", "Alter-Ego", s)   # Alter_Ego_1b
    s = re.sub(r"(?<![A-Za-z])Hero (Giant|Tiny|Normal)(?![A-Za-z])", "Hero", s)
    s = re.sub(r"-denoise(-sharpen)?$|-sharpen$", "", s, flags=re.I)                    # "...-denoise-sharpen"
    s = re.sub(r"(\d+\.\d+)-\d$", r"\1", s)                                            # "..._5.15-2"
    s = re.sub(r"(?:^|(?<=_))([A-Z])_([A-Z][a-z])", r"\1'\2", s)                        # "T_Challa" -> "T'Challa"
    s = re.sub(r"_s(?=[A-Z])", "'s ", s)                                                 # "Captain Marvel_sHelmet"
    s = s.replace("B_ack ", "Black ")
    s = re.sub(r"\s*-\s*Copy(\s*\(\d+\))?$", "", s, flags=re.I)                       # "... - Copy"
    s = re.sub(r"_\d+ copies$", "", s, flags=re.I)                                        # "..._4 copies"
    s = re.sub(r"\s*\(\s*backs? for [^)]*\)", "", s, flags=re.I)                      # "( Backs for 7b-11b)"
    s = re.sub(r"-(Attachment|Treachery|Minion|Ally|Event|Upgrade|Support|Resource|Environment|Villain|Obligation)$", r"_\1", s, flags=re.I)
    s = re.sub(r"(?<=[a-z!?.])(Attachment|Treachery|Minion|Ally|Event|Upgrade|Support|Resource|Environment|Villain|Obligation)$", r"_\1", s)
    return s


def type_of(token):
    low = token.lower().strip()
    if low in TYPE_WORDS:
        return TYPE_WORDS[low]
    if norm(low) in KNOWN_NAMES or len(low) < 5:
        return None
    best = max(TYPE_WORDS, key=lambda w: sim(low, w))
    return TYPE_WORDS[best] if sim(low, best) >= 0.8 else None


def parse_name(fname):
    """Split a cleaned file stem into (name tokens, type, stage, side, subname, card number)."""
    tokens = [t.strip() for t in fname.split("_") if t.strip()]
    typ, stage, side, names, sub, num = None, None, None, [], None, None
    for t in tokens:
        low = t.lower()
        if re.fullmatch(r"\d+", low):
            if names:                      # a number after the name is the card's number in its pack
                num = int(low)
            continue                       # a leading number is just the file's index within its folder
        m = re.fullmatch(r"(?:side )?(\d*)([a-c])", low) or re.fullmatch(r"side (\d+)([a-c])", low)
        if m:
            side = m.group(2)
            if m.group(1) and len(m.group(1)) >= 3:
                num = int(m.group(1))
            elif m.group(1):
                stage = m.group(1)
            continue
        if re.fullmatch(r"[ab]\d", low):              # Collector A1 / B2
            stage = low.upper()
            continue
        if low in ROMAN or re.fullmatch(r"stage (i{1,3}|iv|v|\d+)", low):
            stage = ROMAN.get(low.split()[-1], low.split()[-1].upper())
            continue
        if re.fullmatch(r"\d+[a-c]?|\d+\.\d+|v\d+|[a-c] and [a-c] side|nemesis", low):
            continue
        tt = type_of(t)
        if tt:
            typ = tt
            continue
        pm = re.match(r"^(.*?)\s*[\(\[]\s*(.+?)\s*[\)\]\}]\s*$", t)
        if pm and len(pm.group(1)) > 1:
            t, sub = pm.group(1).strip(), pm.group(2).strip()
        names.append(t)
    return names, typ, stage, side, sub, num


class Matcher:
    def __init__(self, cards):
        self.cards = cards
        self.by_name = defaultdict(list)
        self.by_base = defaultdict(list)          # name without a parenthetical: "Suggestion ([energy])" -> "suggestion"
        for c in cards:
            self.by_name[norm(c["name"])].append(c)
            self.by_base[norm(re.sub(r"\s*[\(\[].*?[\)\]]", "", c["name"]))].append(c)
            KNOWN_NAMES.add(norm(c["name"]))
        self.hero_sets = {}
        self.ambiguous_heroes = set()          # "Spider-Man" / "Black Panther" name two different heroes
        for c in cards:
            if c["type_code"] in ("hero", "alter_ego") and c.get("card_set_code"):
                k = norm(c["name"])
                if k in self.hero_sets and self.hero_sets[k] != c["card_set_code"]:
                    self.ambiguous_heroes.add(k)
                self.hero_sets[k] = c["card_set_code"]
        self.set_codes = defaultdict(set)
        for c in cards:
            if c.get("card_set_name"):
                self.set_codes[norm(c["card_set_name"])].add(c["card_set_code"])
        self.pack_codes = defaultdict(set)
        for c in cards:
            self.pack_codes[norm(c["pack_name"])].add(c["pack_code"])
        for alias, real in (("Red Skull", "The Rise of Red Skull"), ("Agends of SHIELD", "Agents of S.H.I.E.L.D."),
                            ("Galaxy's Most Wanted", "The Galaxy's Most Wanted"), ("Next Evolution", "NeXt Evolution"),
                            ("Synthzoid Smackdown", "Synthezoid Smackdown"), ("Kang", "The Once and Future Kang"),
                            ("Wrecking Crew", "The Wrecking Crew"), ("Green Goblin", "The Green Goblin"), ("Hood", "The Hood")):
            self.pack_codes[norm(alias)] |= self.pack_codes[norm(real)]
        for alias, real in (("Expert Kang", "Kang (Expert)"), ("Expert Kang", "Kang Expert")):
            if norm(real) in self.set_codes:
                self.set_codes[norm(alias)] |= self.set_codes[norm(real)]
        self.set_pack = {}
        for c in cards:
            if c.get("card_set_code"):
                self.set_pack.setdefault(c["card_set_code"], c["pack_code"])
        self.pack_prefix = {}
        for pk, cnt in ((pk, Counter(c["code"][:2] for c in cards if c["pack_code"] == pk)) for pk in {c["pack_code"] for c in cards}):
            self.pack_prefix[pk] = cnt.most_common(1)[0][0]
        self.last_alternates = []

    def context(self, parts):
        ctx = {"hero_set": None, "aspect": None, "sets": set(), "packs": set(), "nemesis": False, "inner": set()}
        folders = [f for f in parts[:-1]]
        first = True
        hero_at, pack_at = None, None
        for i, folder in enumerate(folders):
            f = re.sub(r"\(.*?\)", "", clean_stem(folder)).strip()
            f = re.sub(r"^MC \d+_", "", f)                      # "MC 08_Stephen Strange_Doctor Strange"
            if "nemesis" in f.lower():
                ctx["nemesis"] = True
            if f.lower() in SKIP_FOLDERS:
                continue
            for token in re.split(r"[_/]", f) + [f]:
                t = norm(token)
                if not t:
                    continue
                if t in self.hero_sets and (ctx["hero_set"] is None or t not in self.ambiguous_heroes):
                    ctx["hero_set"] = self.hero_sets[t]
                    hero_at = i
                if t in self.set_codes:
                    ctx["sets"] |= self.set_codes[t]
                    ctx["inner"] = set(self.set_codes[t]) if i == len(folders) - 1 else ctx["inner"]
                if first and t in self.pack_codes:
                    ctx["packs"] |= self.pack_codes[t]
                    pack_at = i
            first = False
        # inside a campaign/scenario box (pack folder above it) a hero-named folder is an encounter set, not a hero
        if hero_at is not None and pack_at is not None and pack_at < hero_at:
            ctx["hero_set"] = None
        return ctx

    def match(self, path):
        self.last_alternates = []
        parts = [p for p in re.split(r"[\\/]", path) if p]
        fname = clean_stem(os.path.splitext(parts[-1])[0])
        if NOT_A_CARD.search(fname):
            return None, "not a card (back image / test file)"
        if DECK_LIST.search(fname):
            return None, "deck list"
        ctx = self.context(parts)
        names, typ, stage, side, sub, num = parse_name(fname)
        if not names:
            if typ == "obligation" and ctx["hero_set"]:
                obl = [c for c in self.cards if c.get("card_set_code") == ctx["hero_set"] and c["type_code"] == "obligation"]
                if len(obl) == 1:
                    return obl[0], "ok"
            return None, f"no name in '{fname}'"
        if typ in ("hero", "alter_ego"):                           # "<Alter Ego>_<Hero>_Hero_1a", "1A_Falcon_Sam Wilson_Hero"
            order = list(reversed(names)) if typ == "hero" else list(names)
            for name in order:
                if any(c["type_code"] == typ for c in self.by_name.get(norm(name), [])):
                    return self._pick(name, typ, stage, side, sub, ctx, fname, num)
            # the scan is named after the other side ("0_Phoenix_Alter-Ego_1A": the alter-ego card is "Jean Grey"), so take
            # the identity card of the wanted type from the same hero set instead of colliding with the hero side
            other = "alter_ego" if typ == "hero" else "hero"
            for name in order:
                sets = {c["card_set_code"] for c in self.by_name.get(norm(name), []) if c["type_code"] == other and c.get("card_set_code")}
                if not sets:
                    continue
                if ctx["hero_set"] in sets:
                    sets = {ctx["hero_set"]}
                for flip in sorted({c["name"] for c in self.cards if c["type_code"] == typ and c.get("card_set_code") in sets}):
                    card, why = self._pick(flip, typ, stage, side, sub, ctx, fname, num)
                    if card:
                        return card, why
            return self._pick(order[0], typ, stage, side, sub, ctx, fname, num)
        if len(names) >= 2:                                        # "<Prefix>_<Name>": aspect / hero / set prefix
            np_ = norm(names[0])
            if names[0].lower() in ASPECTS:
                ctx["aspect"] = names[0].lower()
                names = names[1:]
            elif np_ in self.hero_sets:
                if ctx["hero_set"] is None or np_ not in self.ambiguous_heroes:
                    ctx["hero_set"] = self.hero_sets[np_]
                names = names[1:]
            elif np_ in self.set_codes:
                ctx["sets"] |= self.set_codes[np_]
                names = names[1:]
        why = "no name"
        for cand in ([names[-1], " ".join(names)] if len(names) > 1 else [names[0]]):
            card, why = self._pick(cand, typ, stage, side, sub, ctx, fname, num)
            if card:
                return card, why
        return None, why

    def _pool(self, ctx):
        hs = ctx["hero_set"]
        hp = self.set_pack.get(hs) if hs else None
        out = []
        for c in self.cards:
            if ctx["aspect"] and c.get("faction_code") != ctx["aspect"]:
                continue
            if hs and not ctx["aspect"] and c.get("card_set_code") not in (hs, hs + "_nemesis") and c["pack_code"] != hp:
                continue
            if not hs and (ctx["sets"] or ctx["packs"]) and c.get("card_set_code") not in ctx["sets"] and c["pack_code"] not in ctx["packs"]:
                continue
            out.append(c)
        return out

    def _pick(self, name, typ, stage, side, sub, ctx, fname, num=None):
        key = norm(name)
        cands = list(self.by_name.get(key, [])) or list(self.by_base.get(key, []))
        if not cands:
            pool = self._pool(ctx)
            thresh = 0.8 if (ctx["hero_set"] or ctx["sets"] or ctx["aspect"]) else 0.86
            if ctx.get("inner") and typ:      # the folder names one encounter set and the type is known: be more forgiving
                pool = [c for c in pool if c.get("card_set_code") in ctx["inner"] and c["type_code"] == typ] or pool
                thresh = min(thresh, 0.72)
            scored = sorted(((max(sim(key, norm(c["name"])), sim(key, norm(re.sub(r"\s*[\(\[].*?[\)\]]", "", c["name"])))), c)
                             for c in pool), key=lambda x: -x[0])
            if sub:
                def _sub_of(c):
                    mm = re.search(r"\(([^)]*)\)", c["name"])
                    return norm(c.get("subname") or (mm.group(1) if mm else ""))
                by_sub = [c for c in pool if _sub_of(c) == norm(sub) and sim(key, norm(re.sub(r"\s*\(.*?\)", "", c["name"]))) >= 0.6]
                if by_sub:
                    scored = [(1.0, c) for c in by_sub]
            if scored and scored[0][0] >= thresh:
                cands = [c for r, c in scored if r >= scored[0][0] - 0.02]
            else:
                return None, f"no name match for '{name}' ({fname})"
        if ctx["packs"] and not any(c["pack_code"] in ctx["packs"] or c.get("card_set_code") in ctx["sets"] for c in cands):
            return None, f"'{name}' only exists outside this product ({', '.join(sorted({c['pack_code'] for c in cands}))}) ({fname})"
        # identity cards: the Hero / Alter-Ego word in the file name decides the side. The printed side letter does not
        # (FFG prints the alter-ego as side A and the hero as side B, MarvelCDB codes them the other way round), and
        # for Groot, Rocket or Nick Fury both sides even share the name.
        if typ in ("hero", "alter_ego") and any(c["type_code"] == typ for c in cands):
            cands = [c for c in cands if c["type_code"] == typ]
        # an identity scan inside a hero's own folder is that hero's identity ("Miles Morales_Spider-Man/..._Spider-Man_Hero"
        # is Miles, not the Core Set Spider-Man)
        if typ in ("hero", "alter_ego") and ctx["hero_set"] and any(c.get("card_set_code") == ctx["hero_set"] for c in cands):
            cands = [c for c in cands if c.get("card_set_code") == ctx["hero_set"]]
        codes = {c["code"] for c in cands}
        want = (stage + side).upper() if (stage and side) else (stage.upper() if stage else None)
        wants = {want, (side + stage).upper() if (stage and side) else None} - {None}      # "1A" is stored as "A1" for some villains
        exact_stage = [c for c in cands if wants and str(c.get("stage") or "").upper() in wants]
        if exact_stage:                       # e.g. Collector "A2" is the back side of the A1 card
            cands = exact_stage
        elif side:
            cands = [c for c in cands if c["code"] + "a" not in codes]
            sided = [c for c in cands if c["code"][-1] == side]
            if sided:
                cands = sided
        else:
            cands = [c for c in cands if not (c["code"][-1] in "bc" and c["code"][:-1] + "a" in codes) and c["code"] + "a" not in codes]
        if not cands:
            return None, f"only sided entries for '{name}' ({fname})"

        def score(c):
            s = 0
            if typ and c["type_code"] == typ:
                s += 4
            if typ and typ != c["type_code"] and typ in ("hero", "alter_ego", "villain", "main_scheme", "ally", "minion"):
                s -= 4
            st = str(c.get("stage") or "")
            if stage and (st.upper() == stage.upper() or st.upper().rstrip("AB") == stage.upper()):
                s += 3
            if side and st and st[-1].lower() == side:
                s += 3
            if side and c["code"][-1] == side:
                s += 3
            if side and st and st[-1].lower() in "ab" and st[-1].lower() != side:
                s -= 5
            if sub:
                mm = re.search(r"\(([^)]*)\)", c["name"])
                if norm(sub) in (norm(c.get("subname") or ""), norm(mm.group(1) if mm else "")):
                    s += 4
                elif c.get("subname") or mm:
                    s -= 2
            if ctx["hero_set"] and c.get("card_set_code") == ctx["hero_set"]:
                s += 3
            if ctx["nemesis"] and (c.get("card_set_code") or "").endswith("_nemesis"):
                s += 3
            if ctx["aspect"] and c.get("faction_code") == ctx["aspect"]:
                s += 2
            if ctx["sets"] and c.get("card_set_code") in ctx["sets"]:
                s += 3
            if ctx.get("inner") and c.get("card_set_code") in ctx["inner"]:
                s += 2
            if ctx["packs"] and c["pack_code"] in ctx["packs"]:
                s += 2
            if ctx["hero_set"] and c["pack_code"] == self.set_pack.get(ctx["hero_set"]):
                s += 2
            if c["code"][:2] == self.pack_prefix.get(c["pack_code"]):
                s += 1
            if num is not None and re.sub(r"\D", "", c["code"])[2:].lstrip("0") == str(num):
                s += 5                        # the trailing number in the file name is the card's number in its pack
            return s

        cands.sort(key=lambda c: (-score(c), c["code"]))
        if os.environ.get("MC_DEBUG"):
            print("   scores:", [(c["code"], c["pack_code"], score(c)) for c in cands])
        best = cands[0]
        top = [c for c in cands if score(c) == score(best)]
        # numbered identity versions ("V2_..._Alter-Ego_2b"): pick the Nth of otherwise-identical candidates
        if stage and stage.isdigit() and len(top) > 1 and not any(c.get("stage") for c in top):
            i = int(stage) - 1
            if 0 <= i < len(top):
                best, top = top[i], [top[i]]
        self.last_alternates = [c for c in top if c is not best]
        if len(top) > 1:
            return best, f"ambiguous ({', '.join(c['code'] for c in top[:4])}) -> took {best['code']}"
        return best, "ok"


def synthetic(rel, m):
    """A stand-in card record for a scan MarvelCDB does not index (yet), keyed by its folders and name."""
    parts = [p for p in re.split(r"[\\/]", rel) if p]
    if len(parts) < 2:
        return None
    fname = clean_stem(os.path.splitext(parts[-1])[0])
    if NOT_A_CARD.search(fname):
        return None
    if DECK_LIST.search(fname):
        ctx = m.context(parts)
        hero = ctx["hero_set"]
        if not hero:
            return None
        side = None
        ms = re.search(r"_(?:side )?\d*([ab])$", fname, re.I) or re.search(r"^(\d*)([ab])_", fname, re.I)
        if ms:
            side = ms.group(ms.lastindex).lower()
        kind = "rules" if re.search(r"rules", fname, re.I) else "decklist"
        code = "x:decklist:" + hero + ":" + kind + (side or "")
        return {"code": code, "name": ("Rules reference" if kind == "rules" else "Deck list"), "type_code": "decklist",
                "stage": None, "side": side, "pack": "", "set": "", "hero_set": hero, "synthetic": True}
    names, typ, stage, side, sub, num = parse_name(fname)
    if not names:
        return None
    folders = [re.sub(r"^MC \d+_", "", f) for f in parts[:-1] if f.lower() not in SKIP_FOLDERS]
    pack = folders[0] if folders else parts[0]
    setname = folders[-1] if len(folders) > 1 else pack
    name = " ".join(names) + (f" ({sub})" if sub else "")
    code = "x:" + norm(pack) + ":" + norm(setname) + ":" + norm(name) + (":" + stage if stage else "") + (side or "")
    return {"code": code, "name": name, "type_code": typ or "unknown", "stage": stage, "side": side,
            "pack": pack, "set": setname, "synthetic": True}


def iter_images(sources):
    """Yield (display_path, open_fn) for every image in the given folders / zip files."""
    for src in sources:
        if os.path.isdir(src):
            for root, _, files in os.walk(src):
                for f in files:
                    if f.lower().endswith(IMG_EXT):
                        p = os.path.join(root, f)
                        yield os.path.relpath(p, os.path.dirname(src.rstrip("\\/"))), (lambda p=p: open(p, "rb"))
        elif zipfile.is_zipfile(src):
            z = zipfile.ZipFile(src)
            for info in z.infolist():
                if info.filename.lower().endswith(IMG_EXT) and not info.is_dir():
                    yield info.filename, (lambda z=z, n=info.filename: z.open(n))


def main(sources, dry=False, log=print, stop=None):
    """log: where progress lines go; stop: callable returning True to abandon the run (progress so far is kept)."""
    m = Matcher(load_cards())
    libp, extrap, srcp = (os.path.join(LIB, n) for n in ("library.json", "extra.json", "sources.json"))
    lib = json.load(open(libp, encoding="utf-8")) if os.path.exists(libp) else {}
    extras = json.load(open(extrap, encoding="utf-8")) if os.path.exists(extrap) else {}
    lib_src = json.load(open(srcp, encoding="utf-8")) if os.path.exists(srcp) else {}
    done, skipped, ignored, unmatched, notes = 0, 0, 0, [], []
    for rel, opener in iter_images(sources):
        if stop and stop():
            break
        card, why = m.match(rel)
        if not card and why.startswith("not a card"):
            ignored += 1
            continue
        if not card:
            card = synthetic(rel, m)
            if not card:
                unmatched.append(f"{rel}\t{why}")
                continue
            extras[card["code"]] = card
            why = "unindexed scan (not in MarvelCDB yet)"
        code = card["code"]
        # a second scan of a card with art variants (a/b/c) gets the next unused variant code
        if code in lib_src and lib_src[code] != rel and m.last_alternates:
            alt = next((c for c in m.last_alternates if c["code"] not in lib_src), None)
            if alt:
                card, code, why = alt, alt["code"], why + f"; variant -> {alt['code']}"
        if why != "ok":
            notes.append(f"{rel}\t{why}")
        out = re.sub(r"[^\w.\-]", "~", code) + ".jpg"
        if code in lib and os.path.exists(os.path.join(LIB, lib[code])):
            if lib_src.get(code) and lib_src[code] != rel:
                notes.append(f"{rel}\tsame card as {lib_src[code]} ({code}); kept the first")
                if code in extras:  # unindexed set: the Drive has one scan per printed copy, so duplicates give the count
                    extras[code]["qty"] = extras[code].get("qty", 1) + 1
            skipped += 1
            continue
        lib_src[code] = rel
        if dry:
            lib[code] = out
            done += 1
            continue
        with opener() as fh:
            data = fh.read()
        tmp = os.path.join(LIB, "_tmp" + os.path.splitext(rel)[1])
        open(tmp, "wb").write(data)
        try:
            mc_format.format_card(tmp, os.path.join(LIB, out))
        finally:
            os.remove(tmp)
        lib[code] = out
        done += 1
        if done % 25 == 0:
            json.dump(lib, open(libp, "w", encoding="utf-8"), indent=0)
            json.dump(lib_src, open(srcp, "w", encoding="utf-8"), indent=0)
            log(f"  {done} converted...")
    if not dry:
        json.dump(lib, open(libp, "w", encoding="utf-8"), indent=0)
        json.dump(extras, open(extrap, "w", encoding="utf-8"), indent=1)
        json.dump(lib_src, open(srcp, "w", encoding="utf-8"), indent=0)
        open(os.path.join(LIB, "unmatched.txt"), "a", encoding="utf-8").write("\n".join(unmatched) + ("\n" if unmatched else ""))
        open(os.path.join(LIB, "notes.txt"), "a", encoding="utf-8").write("\n".join(notes) + ("\n" if notes else ""))
    log(f"converted {done}, already had {skipped}, ignored {ignored} (deck lists etc), unmatched {len(unmatched)}, "
        f"noted {len(notes)} -> library has {len(lib)} cards")
    return lib, unmatched, notes


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry"]
    srcs = [p for a in args for p in (glob.glob(a) or [a])]
    main(srcs, dry="--dry" in sys.argv)
