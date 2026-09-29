# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A graphics mod for Age of Empires II: The Conquerors (Gold Edition, UserPatch 1.5) that swaps every unit, building
and map object for a Minecraft-style sprite. Nothing is hand-drawn and no game or Mojang files are in the repo:
every sprite is generated from box/voxel models in Python. The mod is built on the player's own PC from their own
game files. `README.md` has the module-by-module layout table, and `docs/DESIGN.md` has the art rules and the pipeline.

## Commands

```bash
pip install -r tools/requirements.txt          # numpy (build) + pillow (previews only)
python tools/tests/test_export.py              # the whole suite, about 7 s
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
  materials from `styles.py` (per style letter and age). `props.render_static(spec, …)` builds and renders them.
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
3. `Game.layout()` takes each sprite's frames per angle, angle count and mirroring from the `.dat`, falling back
   to the SLP header. Rendering must match the original layout exactly. After rendering, the build refuses to
   write any SLP whose frame count differs from the original.
4. The jobs render in a `multiprocessing.Pool` (`_render`). A sprite that fails keeps the original.
5. Extra layers of composite sprites are replaced with empty SLPs of the same frame count. These come from
   `slpmap.BLANK`, `Game.delta_blanks` and `spritemap`'s blanks, and cover shadows, flags, sails, ram heads and
   roof pieces.
6. `write_outputs` writes the UserPatch mod (`Games/AgeOfMinecraft/...`, then `SetupAoC.exe -g:AgeOfMinecraft`)
   or patches `Data/` directly with backups. Then `apply_gameplay` runs:
   - `gameplay.py` + `datunits.py` patch the `.dat` so the Wonder trains Pac-Man, and give the Javelina its own
     sprites.
   - `sounds.py` WAVs go into `gamedata_x1_p1.drs`.
   - `langdll.py` renames the unit.
   Last, the build writes `aom_report.txt`.

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
