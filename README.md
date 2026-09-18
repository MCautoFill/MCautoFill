# MC Autofill

A local web app for turning card scans into [MakePlayingCards](https://www.makeplayingcards.com) print orders for **Marvel Champions**, **Arkham Horror: The Card Game** and **The Lord of the Rings: The Card Game**.

Pick heroes, campaigns, cycles, packs, quests and encounter sets, review the cards and copy counts, choose the card backs, and let the app upload the whole order to MPC for you. The upload uses an embedded copy of the [mpc-autofill desktop tool](https://github.com/chilli-axe/mpc-autofill), with all of its prompts routed into the app's own UI.

**Full instructions are in the [wiki](../../wiki).**

## Quick start

```bash
pip install -r requirements.txt
python mc_app.py
```

Then build the image library for the game picked in the header:

- **Marvel Champions**: open the **Image library** tab, paste the link of a shared Google Drive scan folder and import the folders you want. No Google account is needed. A local copy of the scans can be imported instead (see the wiki page *Building the card library*):

  ```bash
  python mc_import.py "path/to/Marvel Champions"
  ```

- **Arkham Horror / The Lord of the Rings**: generate MPC exports on [Proxy Nexus](https://proxynexus.net/) (one set at a time, format *MPC*, sides *Double*), then open the **Image library** tab and import the downloaded zips. Their card ids match the app's catalogs, and the generic card backs come along in the same zips.

On Windows you can double-click `Start MC Autofill.bat`; on macOS, `Start MC Autofill.command`.

## What is in the repository

| Path | Purpose |
| --- | --- |
| `mc_app.py` | Flask server and JSON API (runs on http://127.0.0.1:8765) |
| `ui/index.html` | The single-page UI |
| `mc_order.py` | Turns a selection into an order folder with MPC-sized images and `order.xml` |
| `mc_autofill.py` | Runs the embedded mpc-autofill tool on a background thread, prompts go to the UI |
| `mc_import.py` | Matches scan file names to MarvelCDB cards and converts them into the library |
| `mc_drive.py` | Lists and downloads a shared Google Drive scan folder, one sub-folder at a time, and feeds it to the importer |
| `mc_format.py` | Converts a 600 DPI scan into a 1632×2220 MPC image with bleed |
| `mc_catalog.py` | Builds `catalog.json` (heroes, packs, encounter sets) from `marvelcdb_cards.json` |
| `catalog.json`, `marvelcdb_cards.json` | Card database snapshot from [MarvelCDB](https://marvelcdb.com) |
| `games.py` | The games the app knows and where each keeps its catalog, library and backs |
| `set_order.py` | Selection → cards → order folder for the cycle/pack based games (Arkham Horror, The Lord of the Rings) |
| `pn_import.py` | Imports a Proxy Nexus MPC export (zip or folder) into a game's library |
| `ah_catalog.py`, `games/arkham/catalog.json` | Arkham Horror catalog built from [ArkhamDB](https://arkhamdb.com): cycles → packs → investigators, classes, encounter sets |
| `lotr_catalog.py`, `games/lotr/catalog.json` | The Lord of the Rings catalog: Proxy Nexus ids + [Hall of Beorn](http://hallofbeorn.com) card data + [RingsDB](https://ringsdb.com) cycles |
| `vendor/mpc_autofill/` | Unmodified copy of the mpc-autofill desktop tool (GPL-3.0) |

Not in the repository: the card image libraries (`library/` for Marvel Champions, `games/<game>/library/` for the others) and any built `orders/`. You create these locally. Generic promo-style Marvel Champions card backs ship in `backs/`; the Arkham and Lord of the Rings backs arrive with the Proxy Nexus exports.

## License

GPL-3.0, because the app embeds the GPL-3.0 mpc-autofill desktop tool. See `LICENSE`.

Marvel Champions, Arkham Horror: The Card Game and The Lord of the Rings: The Card Game are © Fantasy Flight Games (and Marvel / Middle-earth Enterprises). This project contains no card images and is for personal proxies and replacements only.
