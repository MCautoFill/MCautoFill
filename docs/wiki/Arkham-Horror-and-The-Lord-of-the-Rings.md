# Arkham Horror and The Lord of the Rings

Switch the **Game** dropdown in the header to *Arkham Horror LCG* or *The Lord of the Rings LCG*. Both work the same way; only the catalog differs.

## Where the images come from

[Proxy Nexus](https://proxynexus.net/) keeps high-quality scans of both games and can export them ready for MPC. This app does not download from it; you generate the exports there and the app imports the zips:

1. On Proxy Nexus pick the game, open the **Set** tab and choose a set (a pack, a deluxe box, a nightmare deck...).
2. Format **MPC**, sides **Double**, then **Generate**. A `proxynexus_export.zip` lands in your Downloads folder. Repeat per set.
3. In the app open the **Image library** tab and click **Scan folder** (the Downloads folder by default; any folder path works). Every export is listed with its game and card count. Tick the ones to import and click **Import**.

Each zip holds one image per card side, named after Proxy Nexus's own card ids, which are also the ids in this app's catalogs, so importing is a rename: the images land in `games/<game>/library/`, unchanged (they already carry the MPC bleed), and the generic card backs that ship in every export land in `games/<game>/backs/`. Exports of another game are shown greyed out; switch the game to import them. Importing a zip again replaces its images.

## Cycles & packs tab

The catalog is grouped the way the games are sold:

- **Arkham Horror**: the Core Sets, one cycle per campaign (deluxe box plus its Mythos packs, or the Investigator + Campaign expansions for the newer ones), the *Return to* boxes, investigator starter decks, standalone scenarios, promos and the parallel investigators. The repackaged Investigator / Campaign expansions of the old cycles contain the same cards as the original boxes, so they are noted on the cycle rather than listed twice. Every pack is split into *Investigators*, one section per class, *Weaknesses* and one section per encounter set.
- **The Lord of the Rings**: the Core Sets, one cycle per deluxe expansion with its adventure packs, the Hobbit and Lord of the Rings sagas, standalone and print-on-demand scenarios, starter decks, the ALeP fan-made sets and the nightmare decks. Every pack is split into *Heroes*, one section per sphere, one per quest and one per encounter set.

Tick a cycle or a pack for all of it, or expand a pack and tick sections one by one. Every section shows its copy count and how many of its cards have images; a greyed-out section has none yet and adds 0 copies. *Select everything with images* ticks every section the library can print. The filter box matches pack and section names.

Copy counts are the printed ones (two of most Arkham player cards, three of most Lord of the Rings player cards, encounter cards as printed). As for Marvel Champions, a card without an image defaults to 0 copies, a two-sided card needs both sides, and the order list on the right lets you change any count.

## Skipping cards the revised editions reprint (The Lord of the Rings)

The header has **exclude player cards reprinted in the revised editions**, off by default. With it on, a player card from an older pack that was printed again in the Revised Core Set, the Angmar Awakened, Dream-chaser or Ered Mithrin Hero and Campaign Expansions, the repackaged sagas (The Fellowship of the Ring, The Two Towers, The Return of the King) or the four starter decks is set to 0 copies, so you only print what the new line does not give you. Cards are matched by title, type and sphere against Hall of Beorn's data; encounter and quest cards are never affected, and the revised products themselves are not touched. The order list marks each affected card with "reprinted in …", and a count typed there still overrides the 0.

## Backs and building

Player, encounter (and, for The Lord of the Rings, quest) backs are chosen per card automatically. The *Card back* dropdown lists the back sets the imported exports brought: *original* for the official ones, *alep* for the A Long-extended Party style. **Build order folder** and **Build & autofill…** work exactly as for Marvel Champions; the order goes to `orders/<order name>/`.

## Rebuilding the catalogs

`python ah_catalog.py` rebuilds `games/arkham/catalog.json` from ArkhamDB. `python lotr_catalog.py` rebuilds `games/lotr/catalog.json` from `games/lotr/proxynexus_lotr.json` (the card and pack ids extracted from Proxy Nexus's database), Hall of Beorn's card exports and RingsDB's pack list. Neither is needed unless new products appear.
