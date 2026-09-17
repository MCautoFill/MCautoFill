# Building the card library

The repository ships no card images. You build the `library/` folder yourself from scans with `mc_import.py`. It matches each scan to a MarvelCDB card code, converts it to MPC size, and records what it found.

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

Backs are not in the repository. Put them in a `backs/` folder inside the app folder, named:

```
backs/original_player.jpg     backs/promo_player.jpg
backs/original_encounter.jpg  backs/promo_encounter.jpg
backs/original_villain.jpg    backs/promo_villain.jpg
```

- `player` is used for hero, alter-ego and aspect/basic cards; `encounter` for encounter cards; `villain` for villain and leader cards.
- Any size works; 816×1110 (300 DPI) or 1632×2220 are typical. They are copied into each order as-is.
- Missing files fall back: villain → encounter, and original ↔ promo. If only the promo backs exist, the "Original" choice in the app silently uses them.
