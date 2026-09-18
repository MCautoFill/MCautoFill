# Building the card library

The repository ships no card images. You build the `library/` folder yourself from scans, either straight from a shared Google Drive folder inside the app (easiest) or from a local copy with `mc_import.py`. Both match each scan to a MarvelCDB card code, convert it to MPC size, and record what they found.

## Pulling scans from a shared Google Drive (Image library tab)

Open the **Image library** tab, paste the link of a shared Drive folder and click **Load folder**. Nothing else is needed: the folder only has to be shared with "anyone with the link".

The tab lists every importable folder in the Drive, grouped the way the community scan drive is laid out:

```
Heros/<Alter ego>_<Hero>/            one folder per hero pack (hero cards, nemesis set, deck list)
Expansion Campaings/<Box>/           one folder per campaign box (heroes, aspect cards, villains, modulars)
Scenario Packs/<Pack>/
Modular Sets/<Set>/
Aspects/<Aspect>/                    aspect and basic cards that came in hero packs
Core Set/                            Aspects, Heros, Modular Sets, Villains sub-folders
```

Any other top-level folder (box art, promo art, sheet scans) is listed under *Other* and left unticked.

- Folders already in the library are badged **in library**; use *Select everything not imported yet* to pick the rest.
- **Download & import** fetches one folder at a time into `drive_tmp/`, runs the importer on it, and deletes the download, so disk use stays at one folder's worth of scans (a hero pack is about 1 GB, the Core Set about 5 GB). Progress, the current file and the importer's summary lines are shown at the top of the tab, and **Stop** finishes the current file and quits. Finished folders are remembered in `library/drive_done.json`, so a stopped run resumes where it left off.
- Tick *keep the raw scans* to move each folder's downloads into `scans/` instead of deleting them.
- The full drive is roughly 60 GB of TIFFs; expect a few hours for everything. Downloads run four at a time.
- **Drive API key (optional).** Listing and downloading use Google's public endpoints and need no account. If Google starts refusing anonymous downloads ("quota hit" in the log), create a free API key in the Google Cloud console with the Drive API enabled, paste it in the tab, and the same calls go through the official API instead.

The result is identical to running `mc_import.py` on a local copy, described next.

## Importing a local copy

## Scan requirements

- One image per card face. Double-sided cards (hero/alter-ego, main schemes, some villains) are two files.
- 600 DPI is what the formatter expects. Scans at that resolution are around 1452×2080 pixels for the card face. TIFF (8 or 16 bit), JPG and PNG all work.
- Scans should be trimmed to the card edge. The formatter adds the bleed; it does not crop.

## How file names are matched

The importer reads the card name and hints from the file name and the folders above it. It is tolerant of the usual scan naming, for example:

```
Heros/Peter Parker_Spider-Man/Spider-Man_Swinging Web Kick_Event_5.tiff
Expansion Campaigns/NeXt Evolution/Cable/Cable_Hero_A.tiff
Villains/Klaw/Klaw_Stage I_Villain.tiff
Modular Sets/Legions Of Hydra/Legions Of Hydra_Hydra Soldier_182.tiff
```

Things it understands:

- **Hero, villain, set and pack folders.** A folder named after a hero, encounter set or product narrows the search to that content. Put each product's scans in a folder named after the product.
- **Type words** (`Hero`, `Alter-Ego`, `Event`, `Upgrade`, `Minion`, `Treachery`, `Villain`, `Main Scheme`, …) settle ambiguous names.
- **Stages and sides.** `Stage I`, `1`, `A1`, `1A`, `A`, `B`, `Side A` all work for villains, schemes and identities.
- **Trailing numbers** are treated as the card number within the pack.
- **Scanner noise** such as `- Copy`, `_4 copies`, `-denoise-sharpen`, `_5.15` copy counters and glued-together words is stripped.
- **Duplicate scans** of the same card are kept once; the extra copies are noted, not converted.

Everything that could not be matched is listed in `library/unmatched.txt`. Anything that matched with a caveat (an ambiguous name, a variant art pick, a duplicate) is in `library/notes.txt`. Deck lists, rules references and card backs are ignored.

## Running the import

```bash
python mc_import.py "D:/Scans/Marvel Champions/Heros" "D:/Scans/Marvel Champions/Core Set"
```

- Accepts folders, zip files and glob patterns, any number of them.
- Skips scans whose card is already in the library, so you can run it again after adding a set.
- `--dry` prints what would happen without converting anything.
- Conversion is about one second per card. A full hero pack takes a minute; the Core Set a few minutes.

Output goes to `library/`:

| File | Contents |
| --- | --- |
| `<code>.jpg` | The MPC-ready image, one per card face (1632×2220, quality 92) |
| `library.json` | Card code → image file |
| `extra.json` | Cards that exist in the scans but not in MarvelCDB, with their copy counts |
| `sources.json` | Which scan each image came from |
| `notes.txt`, `unmatched.txt` | The review lists described above |

## Image format

MPC prints 2.48×3.46 inch cards from 2.72×3.70 inch files (0.12 inch bleed on every side). At 600 DPI that is 1632×2220 pixels.

`mc_format.py` places the card face on that canvas without cropping, fills the bleed by extending the edge pixels outward (blurred, so a pattern edge does not produce a hard line), and rounds the corner area with the border colour. Text is never mirrored into the bleed.

## Card backs

The repository ships a set of generic "promo" style backs in the `backs/` folder (player, encounter and villain), so nothing needs to be added before the first order. To use other backs, for example the original ones, put them in the same folder, named:

```
backs/original_player.jpg     backs/promo_player.jpg
backs/original_encounter.jpg  backs/promo_encounter.jpg
backs/original_villain.jpg    backs/promo_villain.jpg
```

- `player` is used for hero, alter-ego and aspect/basic cards; `encounter` for encounter cards; `villain` for villain and leader cards.
- Any size works; 816×1110 (300 DPI) or 1632×2220 are typical. They are copied into each order as-is.
- Missing files fall back: villain → encounter, and original ↔ promo. With only the shipped promo backs present, the "Original" choice in the app silently uses them.
