# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `HANDOFF.md` first.** It holds the player's setup, how they like to work, and the train crash's cause
(found 2026-10-10 from Windows' error log).

## What this is

A graphics mod for Age of Empires II: The Conquerors (Gold Edition, UserPatch 1.5) that swaps every unit, building
and map object for a Minecraft-style sprite. Nothing is hand-drawn and no game or Mojang files are in the repo:
every sprite is generated from box/voxel models in Python. The mod is built on the player's own PC from their own
game files. `README.md` has the module-by-module layout table, and `docs/DESIGN.md` has the art rules and the pipeline.

## Commands

```bash
pip install -r tools/requirements.txt          # numpy (build) + pillow (previews only)
python tools/tests/test_export.py              # the whole suite, about 25 s
python tools/concept_sheet.py [out_dir]        # regenerate previews/* (and always docs/UNITS.md)
python tools/build_mod.py --game <AoE2 folder> [--only militia,archer | buildings,walls,...] [--dry-run]
```

- Tests use a custom runner. `pytest tools/tests` only half works: tests that take a `tmp: Path` argument error
  because there is no `tmp` fixture. Pytest is fine for the others (`-k slp_round_trip`). To run one `tmp` test:
  `python -c "import sys,tempfile,pathlib; sys.path.insert(0,'tools/tests'); import test_export as t; t.test_full_build(pathlib.Path(tempfile.mkdtemp()))"`
- No real game install is available in development. `test_export.py` builds a fake game folder (`fake_palette`,
  `fake_civs`, `fake_dat`, `fake_game`) that mirrors the binary formats byte for byte. If you change how
  `datfile.py`/`datunits.py` parse records, change those fake builders (e.g. `_unit_bytes`) to match.
- The `.bat` files are the player's entry points on Windows. They wrap `build_mod.py` (`--mode direct`, `--restore`).
- There is no linter config. The code uses `from __future__ import annotations`, ~120-column lines and module
  docstrings that explain the why.

## Architecture

Everything lives in `tools/aom/` as one package. `build_mod.py`, `concept_sheet.py` and the tests import it by
putting `tools/` on `sys.path`.

**Models → frames (does not need the game).**
- A unit is a `units.Unit`: a tree of `geometry.Part`s holding textured `Box`es, measured in Minecraft pixels.
  It names a `rig` and an `attack` style, which `animation.pose(unit, action, t)` turns into part rotations.
- The group modules (`units.FOOT`, `mounted.MOUNTED`, `siege.SIEGE`, `ships.SHIPS`, `animals.ANIMALS`,
  `easter.EASTER`) are dicts of key → builder. They merge into `roster.ROSTER`. That key is the same one used by
  `--only`, `slpmap.Target.unit` and `docs/UNITS.md`.
- Buildings and scenery are `voxel.Structure`s on an integer block grid, with textures from `blocks.py` and
  materials from `styles.py` (per style letter and age). Each set builds in its own way (`architecture.py`:
  `ground`, `hall`, `door`, `tower`, `shed`), so the sets differ in shape; the shared Dark Age look (style G) is
  the `_dark_*` builders in `structures.py`. `props.render_static(spec, …)` builds and renders them.
  The spec's `mode` (variants / anim / facing / pieces / overlay) says how the original SLP's frames are organised.
- `render.py` is an orthographic ray-caster from AoE2's camera. It outputs palette-agnostic `Frame`s whose pixels
  each have a *kind* (TRANSPARENT, SOLID, PLAYER, SHADOW, OUTLINE). `palette.Quantiser` maps them to the game's
  palette indices and player-colour ranges, and `slp.encode` writes SLP 2.0N.

**Game files → mod (`build_mod.main`).**
1. `Game` opens the player's DRS archives (the patch archives take precedence), the palette (`interfac.drs` 50500),
   the `.dat` graphics table and the language DLLs. If a `*.aom-backup` exists, it always reads that instead, so
   rebuilding after `--mode direct` starts from the originals.
2. It chooses the targets:
   - Units use fixed SLP ids from `slpmap.TARGETS`, plus `Game.name_targets` (graphic name prefixes).
   - Buildings, walls, trees and decorations are never listed by id. `spritemap.plan()` finds them by parsing the
     `.dat`'s systematic graphic names (e.g. `BRKS3NNM` = barracks, Castle Age, main sprite, Middle Eastern).
   - Farms are terrain, not sprites. `datfile.read_terrains` reads the `.dat`'s terrain table, and
     `farmland.farm_slps` picks terrains 7, 8 and 29–31. If the table can't be read, it falls back to the original
     ids. Their textures in `terrain.drs` are redrawn one diamond tile per frame.
   - The screen panels are full-screen pictures in `interfac.drs` (51101–51160, one per civ and screen size).
     `interface.py` repaints them by brightness class and puts item icons over the resource icons.
     The resource bar has one fixed layout in every picture (`interface.places`: an icon every 77 px from x 8, the
     game's dark amount box ending 69 px after it); each item fills a 16x16 square, and a flat near-black box
     (`BOX`, 17-71 from the icon) holds the amount, which the game writes right-aligned, ending at icon + 66.
     UserPatch draws its own food icon (`interface.FOOD`, 53010, a steak on black) over the bar's; `food_icon`
     makes it the bar's meat at the same place, the rest clear.
   - The main menu (`interfac.drs` 50189) is redrawn by `menu.py`: a new 800x600 picture, and each button's
     pictures cut from it at the original places (`menu.BUTTONS`), with the original's glow colour. Only a menu
     with exactly the known picture sizes (`menu.known`) is replaced. Names sit on Minecraft buttons drawn where a
     screenshot showed the game writes them (`menu.SIGNS`); hovered things darken (`DARKER`, no glow). The menu
     palette 50589 (used by 50089/50090 only) is replaced (`menu.palette`, `build_mod.menu_palette`); the menu, its
     dialogue 50190 (`screens.encode(..., out=)`) and its icons 50688 (a "recolour" job) are drawn for it, and
     `menu_settings` gives the screen files Minecraft buttons (`menu.settings`: `background_color` is the fill of
     the game's own buttons, 0 = none; bevel colours, white/yellow text).
   - The other screens (`screens.RESTYLED`: setup screens, dialogues, history, achievements, loading screen 50163) are
     found through the screen files (`screens.read`, `Game.screens`) and redrawn by `screens.hall`: parchment
     (`screens.sheets`) becomes a window in a middle grey (`screens.WINDOWS`: white, cream, black and player colours
     all readable); everything around it one material, deepslate or dark oak (`WOODEN`), never mixed (the player
     asked for that); the achievements and timeline are the dark window. `screens.quantise` picks
     colours good in every palette a picture is shown in; `LAYOUTS` gives the sheets of a few pictures by hand.
     Pictures without parchment are one solid colour (the game writes scores in player colours on them). The
     achievements' flags (`screens.FLAGS`, no screen file names them: `SHOWN_WITH` gives the achievements' palette)
     become banners coloured from each flag's own pixels, as that palette lacks Minecraft's wool colours. Its tabs
     (`TABS`, 12 pictures: each tab not chosen / chosen, told apart by the dark edge at their top) lose their top
     rows, which ran under the Play Again and Main Menu buttons; the team marks (`TEAMS`: teams 1-4, then the small
     "no team" one; the game writes the number in each shield's dark middle) become Minecraft shields in each team's
     pattern (`TEAM_PATTERNS`) with that middle kept dark, and `team_copies` redraws copies and near copies (85% of
     pixels) in any archive (the report's TEAM MARKS section lists every archive holding them).
   - The mod's XML points UserPatch at the game's own strings: `langId` 10230 (civ names, Britons 10231),
     `descId` 20150, `aiNameOffset` 140 (the Conquerors civs' computer names at 4800); WololoKingdoms' values are
     for its own language file and left those computer players nameless.
     The game writes names in white, black or the player's colour, so the banners' stripe is a middle grey; the
     scores are in player colours, so they sit on a light panel (`LAYOUTS` "panels") in the dark window.
   - A picture listed by screens with very different palettes only looks right in one: `screens.intended` picks
     it (neighbouring pixels most alike) and drops palettes too different to share colours with. The PNGs in
     `screen_originals/` use the first screen's palette, so some of them show scrambled colours.
   - The loading screen (50163) is `loadscreen.py`'s title screen. Its palette (50563) is used by that screen alone,
     so the build writes a new one made from the picture (`loadscreen.palette`, median cut; indices 0-9 and 246-255,
     the Windows colours, kept) as a "bina" entry next to it (`draw_loading`, after the render pool).
   - `terrain.drs` and `interfac.drs` are searched by `Game.original`/`holders` (`Game._searched`) but kept out of
     `Game.archives`, so Pac-Man's icon and sound code sees exactly the archives it always did.
3. `Game.layout()` takes each sprite's frames per angle, angle count and mirroring from the `.dat`, falling back
   to the SLP header. Rendering must match the original layout exactly. After rendering, the build refuses to
   write any SLP whose frame count differs from the original.
4. The jobs render in a `multiprocessing.Pool` (`_render`). A sprite that fails keeps the original.
5. Extra layers of composite sprites are replaced with empty SLPs of the same frame count. These come from
   `slpmap.BLANK`, `Game.delta_blanks` and `spritemap`'s blanks, and cover shadows, flags, sails, ram heads and
   roof pieces.
6. `write_outputs` writes the UserPatch mod, a standalone game `MOD` = `age_of_minecraft` (`Games/age_of_minecraft/`),
   or patches `Data/` directly with backups. Then `apply_gameplay` runs:
   - `gameplay.py` + `datunits.py` patch the `.dat` so the Wonder trains Pac-Man, and give the Javelina its own
     sprites. The Saboteur ("to smithereens", 706) becomes the giant red Pac-Man (`gameplay._giant`): Pac-Man's
     attacks, armours and sounds written over its own in place, resource capacity 1 (`GIANT_CARRY`: UserPatch 1.5
     otherwise blows up units 440, 527, 528 and 706 on their first attack), and an unused graphic (`GIANT_GRAPHICS`, found by
     `giant_graphic`) pointed at his new SLP (`giant_slp`, in red-team palette shades, written next to Pac-Man's
     sounds), as the Saboteur shares the Petard's sprites. The Wonder also trains the dragon (`gameplay._dragon`), in
     the never-used Advanced Heavy Crossbowman's slot (493): its own sprites (slpmap), every terrain, its shots
     (508, and 520 after Chemistry) drawn by an unused graphic (`FIRE_GRAPHICS`) pointed at a new fireball SLP
     (`fireball_slp`), its texts by `name_dragon`.
   - `lava.py` makes terrain 15 ("Old Water": no texture of its own, drawn as the Water, passable as water) lava, in
     place: its own texture (the Water's tile shapes, cut by `farmland.cut`), minimap colour and the Water's blending;
     the Docks' placement terrains (Water, Shallows) become (Water, lava). Its map, `Team Lava Islands.rms` (written
     from scratch, `lava.script`), goes into the mod's `Script.RM` (`write_map`), or in direct mode the game's
     `Random`, which `restore` empties of it (only a file carrying `lava.MARK`). `--only lava` builds just this.
   - `rails.py` makes the Trade Cart (128, 204) a train that lays its own rails, in place: it keeps its terrain
     restriction row (20), whose pass graphics (what a unit leaves on the ground behind it) become the cart tracks
     (CARTSTPS) on every terrain it goes on, not only snow; the siege weapons that shared row 20 move to the row
     exactly like it that most units use (`siege_row`: 7), so the cart tracks are the trains' alone. Their graphic
     keeps every setting (5 frames of 6 s) but its SLP (`track_slp`, written after the giant's and the fireball's:
     a straight piece of rails behind the train, never ahead, so it only lies where the train went; frame properties
     16, as the original's). A piece must last under a minute (`rails.WHEEL`, `track_graphic` refuses longer): the
     game files ground pieces in a 60-slot one-second wheel and writes past it for longer ones (004d5b03), corrupting
     memory; the four builds whose pieces lasted a day, then 5 minutes, crashed so. The train is drawn
     `TRAIN_SCALE` big, the track as wide (`GAUGE`); its texts by `name_train`. `--only rails` builds just this.
   - `volcano.py` makes the never-built Sea Tower (785, still a tower: class 52, so tower upgrades reach it) the
     volcano, in place: built by Villagers (118, button 5 on the military page: the page is the interface kind, 2 economic, 10 military;
     a button 14 did not show) on the Dock's placement rules (side terrains, row, hill
     mode, copied from the unit named DOCK) with placement terrain 15, lava under its middle, 3x3. Fishing Ships cannot
     build it: the game hard-codes the Fishing Ship (13) to the Fish Trap (199) (004b9b8f and others); a test game of
     three Dock copies for Fishing Ships, on the Dock's, the Fish Trap's and the volcano's rules, placed none. It shoots
     its own unused shots (786, 787)
     as lobbed lava bombs. Its three graphics (STWR1NN at rest; 787's MFSTW, made one direction of 12 frames, its
     attack graphic: buildings play attack graphics, as the unpacked Trebuchet does; 786's MRSTW the bomb) draw new
     SLPs (`volcano_slp`, `eruption_slp`, `bomb_slp`, written after the rails'), their old shadow deltas set to -1.
     Its icon goes at the end of the four building icon sheets (50705-50708, one per age); its texts by
     `name_volcano`. `--only volcano` builds just this.
   - `sounds.py` (Pac-Man's) and `roars.py` (the dragon's) WAVs go into `gamedata_x1_p1.drs`. The dragon's sounds
     come after Pac-Man's in the `.dat`'s sound table and take resource ids after his, so his never move.
   - `langdll.py` renames the unit: in direct mode in the game's own DLLs, in place. In the standalone mod,
     `mod_language` gives the mod its own `language_x1_p1.dll` (`langdll.with_strings`: a new resource section
     added by `pe.py`) with his texts and "Age of Minecraft".
   In the standalone mod, `mod_archive` then writes every archive's changes into the mod's own
   `gamedata_x1_p1.drs`: a UserPatch mod's Data folder is only read for that, its `.dat` and `language_x1_p1.dll`
   (the game looks in the patch archive first; WololoKingdoms does the same). It then gets its exe once
   (`SetupAoC.exe -g:age_of_minecraft` returns at once and finishes after Install is clicked, so `make_exe` waits;
   icon swapped in place by `appicon.into_exe`, window title by `retitle`: only the NUL-bounded text "Age of Empires
   II Expansion", never longer texts or the settings' registry name "...: The Conquerors Expansion"), "Age of Minecraft" shortcuts (PowerShell,
   Windows only) and the original pictures as PNGs: `menu_originals/` and `screen_originals/` (every screen
   file's backgrounds, found by `screens.read`, plus every other large interfac.drs picture, e.g. the loading
   screen). Last, the build writes `aom_report.txt`, whose SCREENS section lists each screen file's settings.

## Invariants that are easy to break

- **Keep binary patches in place.** `.dat` and DLL edits change only fixed-size fields, and the rest of the file
  stays byte-for-byte the same.
  - `datunits` parses every civilisation completely and checks it ends where the next one begins
    (`DatLayoutError`).
  - When the file must grow (task lists, sound table), it grows back to front so earlier offsets stay valid, and
    the result is read back to check it.
  - `langdll` rewrites a string only if the new text fits in the old space.
- **Take counts from the game.** Frame and angle counts always come from the player's files, never from code.
  With mirroring, `a // 2 + 1` angles are stored (S, SW, W, NW, N) and the game mirrors the rest.
- **Wall frames have a fixed meaning:** 0 `/`, 1 `\`, 2 the post (at ends and corners), 3 `--`, 4 `|`.
- **Terrain tiles must fit together.** The game picks a terrain frame by map position, so a farm texture repeats
  every tile (`farmland.PER_TILE` = 2 blocks to a tile, camera scale `farmland.scale`). Each new frame fills exactly the original frame's pixels.
- **Don't change Pac-Man without asking.** His `.dat` patch, icon, sounds and name took many rounds of testing in
  the player's game.
- **Seed randomness with `zlib.crc32`, never `hash()`.** Python's string hashes change every run, so the sprites and
  previews would too (`Painter` seeds with crc32; `test_renders_are_reproducible` checks two hash seeds).
- **Keep the `.bat` files' Windows line endings (CRLF).** Editing them with a tool that writes `\n` converts them.
- **Windows players come first.** Look files up with the case-insensitive `pick()`. Never write into the player's
  `Data/` without a `.aom-backup`, and make sure `--restore` can undo every file the build touches.
- **Textures are original pixel art made in code** (`textures.py` ASCII-art grids, noise and team-colour specs).
  Don't add image assets.
- **Preview sheets need matching entries.** Every stem in `roster.SHEETS` needs an entry in
  `concept_sheet.ANIMATIONS`. A unit shows up on a sheet through its `group`, or its `civ` for unique units.

## Conventions

- A change players can notice also updates `docs/DESIGN.md` and/or `docs/INSTALL.md`, written in the same plain,
  non-technical English. If the visuals change, regenerate the affected `previews/`.
- Commit subjects describe the change from the player's side ("Let ships unload Pac-Man onto the beach"). The
  body explains the cause and the in-game reasoning.
