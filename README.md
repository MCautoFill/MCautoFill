# MC Autofill

A local web app for turning Marvel Champions card scans into [MakePlayingCards](https://www.makeplayingcards.com) print orders.

Pick heroes, campaign expansions and scenario packs, review the cards and copy counts, choose original or promo card backs, and let the app upload the whole order to MPC for you. The upload uses an embedded copy of the [mpc-autofill desktop tool](https://github.com/chilli-axe/mpc-autofill), with all of its prompts routed into the app's own UI.

**Full instructions are in the [wiki](../../wiki).**

## Quick start

```bash
pip install -r requirements.txt
python mc_app.py
```

Then build the card library from your scans (see the wiki page *Building the card library*):

```bash
python mc_import.py "path/to/Marvel Champions"
```

On Windows you can double-click `Start MC Autofill.bat`; on macOS, `Start MC Autofill.command`.

## What is in the repository

| Path | Purpose |
| --- | --- |
| `mc_app.py` | Flask server and JSON API (runs on http://127.0.0.1:8765) |
| `ui/index.html` | The single-page UI |
| `mc_order.py` | Turns a selection into an order folder with MPC-sized images and `order.xml` |
| `mc_autofill.py` | Runs the embedded mpc-autofill tool on a background thread, prompts go to the UI |
| `mc_import.py` | Matches scan file names to MarvelCDB cards and converts them into the library |
| `mc_format.py` | Converts a 600 DPI scan into a 1632×2220 MPC image with bleed |
| `mc_catalog.py` | Builds `catalog.json` (heroes, packs, encounter sets) from `marvelcdb_cards.json` |
| `catalog.json`, `marvelcdb_cards.json` | Card database snapshot from [MarvelCDB](https://marvelcdb.com) |
| `vendor/mpc_autofill/` | Unmodified copy of the mpc-autofill desktop tool (GPL-3.0) |

Not in the repository: the `library/` of converted card images, the `backs/` card-back images and any built `orders/`. You create these locally.

## License

GPL-3.0, because the app embeds the GPL-3.0 mpc-autofill desktop tool. See `LICENSE`.

Marvel Champions is © Fantasy Flight Games / Marvel. This project contains no card images and is for personal proxies and replacements only.
