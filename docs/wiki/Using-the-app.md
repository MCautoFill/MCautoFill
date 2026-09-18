# Using the app

Open http://127.0.0.1:8765 after starting the app. The header shows how many card images are in the library. Everything you select is saved in the browser, so you can close the tab and come back.

## Header options

- **Order name** — the folder name under `orders/` that the build writes to.
- **Card back** — Original or Promo. Applied per card type automatically (player, encounter, villain).
- **Copies** — *As printed in pack* uses the real copy count of every card (three of most aspect cards, one of each hero card, and so on). *1 of each player card* prints a single copy of each player card; encounter cards keep their printed counts.
- **Include Core Set reprints** — off by default. Aspect and basic cards that are reprints of Core Set cards are set to 0 copies unless this is on, so you do not print a second Core Set by accident.
- **Include duplicates from other sets** — off by default. A card first printed in another (non-Core) product is set to 0 copies; the earliest printing keeps its copies. Encounter cards are never affected by either option.
- **Build order folder** — writes the order without uploading.
- **Build & autofill…** — writes the order and starts the upload (see [Uploading to MPC](Uploading-to-MPC)).

## Heroes tab

Pick heroes from the dropdown (it is multi-select with a filter, plus All / None). Each chosen hero gets a group showing:

- **Hero cards** — the identity card (front and back) and the hero's own cards, including the deck list card when the scans have one.
- **Nemesis set** — on by default.
- **Modular set** — the modular encounter set(s) that shipped in the hero's pack, on by default.
- **Hero + pack's aspect/basic cards** — switch the mode to also include the aspect and basic cards from that hero pack.

Cards with a dashed outline have no image in the library yet and are skipped at build time. The small "also in" line under a card lists other products it was printed in.

## Campaign expansions tab

Pick the Core Set or any campaign box from the dropdown. Everything in a box is on by default. The left panel lists the box's components so you can untick what you already own:

- each hero individually (hero cards plus nemesis set),
- the aspect and basic cards,
- every encounter set, with its kind (villain, modular, campaign).

The cards for each selected box appear on the right, grouped the same way.

## Scenario packs tab

Tick a pack to include all of its encounter sets, or expand it and tick individual sets.

## Order list (right panel)

Every card in the current selection with its copy count. Edit a number to change how many copies get printed; 0 leaves the card out. The "reset" button puts every count back to the printed number. Counts in red differ from the default.

## Card library tab

Where card images come from. Paste a shared Google Drive folder link, load it, tick the folders you want and import them; see [Building the card library](Building-the-card-library#pulling-scans-from-a-shared-google-drive-card-library-tab). Folders already in the library are badged, and an import can be stopped and resumed. The other tabs pick up new images as soon as the import finishes.

## Selected cards tab

A summary: total cards, unique cards, cards without an image, and whether the order fits MPC's 612-card project limit. Below it every card is shown grouped by where it came from.

## The order folder

`Build order folder` writes `orders/<name>/`:

- `images/` — one file per card face, plus the card backs used
- `order.xml` — the mpc-autofill order file, with absolute paths, quantities, stock and the default back
- `selection.json` — what was selected, and which cards were skipped for lack of an image

The folder is self-contained; you can also feed `order.xml` to the stand-alone mpc-autofill desktop tool if you prefer.
