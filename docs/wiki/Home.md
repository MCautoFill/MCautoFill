# MC Autofill

MC Autofill is a local web app that builds [MakePlayingCards](https://www.makeplayingcards.com) (MPC) print orders for Marvel Champions: The Card Game from your own card scans.

You pick what you want printed, the app works out the right number of copies of each card, pairs every card with the correct back, and then drives the MPC website to upload all of it into a project in your MPC account.

## How it works

1. **Card scans** (600 DPI TIFF or JPG, one file per card face) are matched to the MarvelCDB card database by their file names and converted into MPC-sized images with bleed. This is done once per set with `mc_import.py` and produces the `library/` folder.
2. **The app** (`mc_app.py`) serves a page at http://127.0.0.1:8765 where you select heroes, campaign expansions and scenario packs, adjust quantities, and choose card backs.
3. **Build** writes an order folder with the images and an `order.xml` that the mpc-autofill desktop tool understands.
4. **Build & autofill** does the same and then runs the embedded mpc-autofill tool, which opens a browser, creates or extends an MPC project and uploads every image. Progress, questions and the sign-in step appear at the top of the app.

## Pages

- [Installation](Installation) — Python, dependencies, Windows and macOS launchers
- [Building the card library](Building-the-card-library) — how scans are named, matched and converted; card backs
- [Using the app](Using-the-app) — the tabs, quantities, reprints, order list
- [Uploading to MPC](Uploading-to-MPC) — the autofill settings, the 612-card limit, sign-in
- [Troubleshooting](Troubleshooting)

## Credits

The upload is done by an unmodified copy of the [mpc-autofill](https://github.com/chilli-axe/mpc-autofill) desktop tool by chilli-axe (GPL-3.0), vendored under `vendor/mpc_autofill/`. Card data comes from [MarvelCDB](https://marvelcdb.com). Marvel Champions is © Fantasy Flight Games / Marvel; this project ships no card images.
