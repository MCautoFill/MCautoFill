# Troubleshooting

## The page says "0 card images in library"

The `library/` folder is empty or missing. Run `mc_import.py` on your scans (see [Building the card library](Building-the-card-library)). The app reads the library on every request, so no restart is needed after an import.

## A card shows a grey "no image yet" placeholder

That card was not matched from the scans. Check `library/unmatched.txt` for the file name and why it failed, rename the scan so the card name and type are unambiguous, and run the import again. Cards without an image are skipped at build time and counted in the Selected cards tab.

## A card got the wrong image

Look the card up in `library/sources.json` to see which scan it came from, and in `library/notes.txt` for "ambiguous" entries. Delete the wrong `library/<code>.jpg`, remove its entry from `library.json`, rename the scan, and import again.

## The importer says "no name match" for a card that exists

MarvelCDB may not have the card yet (very new products), or the scan name is far from the printed name. Cards that are in the scans but not in MarvelCDB can still be included: the importer records them in `library/extra.json` and the app shows them in a "(from scans)" encounter set for that product.

## "Include Core Set reprints" is off but a card still shows 3 copies

Only the earliest printing is zeroed by the reprint rules. A card from the pack you selected that was first printed there keeps its copies, even if it was later reprinted elsewhere. The "also in" line under the card tells you where else it appeared.

## The upload stops with a yellow banner

Auto-save is on and you are not signed in to MPC. Sign in inside the automated browser window; the app resumes on its own.

## The browser does not open, or Selenium errors

- Make sure the chosen browser is installed. Selenium fetches the driver itself; a first run can take a few seconds while it downloads.
- Set **Browser binary** in the settings dialog if the browser is installed in a non-standard place.
- On macOS, allow the automation prompt the first time.
- Firefox is the fallback if Chrome or Edge misbehave after a browser update.

## An order was built into the wrong folder / I want to start over

Order folders are just files under `orders/`. Delete the ones you do not want. Selections live in the browser's local storage; the None buttons and "Clear all" reset them, or clear site data for 127.0.0.1:8765.

## Python changes are not taking effect

`ui/index.html` is read on every page load, but the `.py` files are loaded once. Restart the app after editing them.
