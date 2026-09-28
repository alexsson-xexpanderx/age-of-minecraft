# Age of Minecraft

A mod for **Age of Empires II: Gold Edition** that replaces the units and
buildings with blocky, pixel-art Minecraft-style ones. There are villagers in
robes, diamond-armoured champions, skeleton archers, pillager crossbowmen and
snow-golem skirmishers. Knights ride horses in Minecraft horse armour. Ravagers
serve as battering rams, dispenser minecarts as mangonels, and a TNT cannon as
the bombard. Creepers are the petards, and the fleet sails under team-coloured
wool. All 90 units are modelled.

![battle](previews/battle.png)

The sprites are generated, not hand-drawn. Each unit is a Minecraft-style box
model and each building a grid of blocks. A small renderer draws them from
AoE2's isometric camera, in all directions and animation frames, with
team-colour regions ready for the game palette.

See [docs/DESIGN.md](docs/DESIGN.md) for the art direction and the path into
the game, and [docs/UNITS.md](docs/UNITS.md) for the full unit list.

## Try it in your game

You need AoE2: The Conquerors with UserPatch 1.5, and Python 3.
Double-click **`build_mod.bat`** (it finds your game or asks for the folder),
then start `age2_x1\AgeOfMinecraft.exe`. The build reads your own game files and
writes a separate UserPatch mod, so your normal game stays untouched. Full
steps and options are in [docs/INSTALL.md](docs/INSTALL.md).

## Previews

```sh
pip install -r tools/requirements.txt
python tools/concept_sheet.py        # writes previews/* and docs/UNITS.md
```

| File | Shows |
|---|---|
| `previews/roster_<group>.png` | every unit of a group in the 5 stored directions (civilians, infantry, cavalry, siege, ships, uniques, animals) |
| `previews/anim_<group>.gif` | walk, attack, work and death cycles for each group |
| `previews/battle.png` | siege and cavalry storming a town |
| `previews/harbor.png` | the fleet off the coast |
| `previews/scene.png` | two armies at in-game size |
| `previews/village.png` | Town Center and houses with working villagers |
| `previews/player_colors.png` | a unit in all 8 player colours |

## Layout

```
tools/aom/textures.py    pixel-art texture helpers (ASCII-art faces, noise, team colour)
tools/aom/geometry.py    box models: parts, pivots, held items as extruded sprites
tools/aom/render.py      isometric ray-caster -> palette-agnostic frames
tools/aom/animation.py   rigs and attack styles: stand / walk / attack / die / carry poses
tools/aom/items.py       held items: swords, tools, bows, crossbows, tridents, firework gun...
tools/aom/units.py       biped builder, mob looks, foot units, villagers and their jobs
tools/aom/mounted.py     horses, donkeys, zombie horses, llamas and their riders
tools/aom/siege.py       ravagers, dispenser carts, crossbow turrets, TNT cannon, trebuchet, wagons
tools/aom/ships.py       boats and warships with team sails
tools/aom/animals.py     sheep, chicken, goat, hoglin, pig, wolf
tools/aom/roster.py      the full roster and preview groups
tools/aom/buildings.py   block textures, block shapes (stairs, slabs, panes) and the buildings
tools/aom/slp.py         SLP 2.0N sprite encoder/decoder
tools/aom/drs.py         DRS archive reader/writer
tools/aom/palette.py     game palette and colour matching
tools/aom/datfile.py     graphics table reader for empires2_x1_p1.dat
tools/aom/slpmap.py      which original sprite id each render replaces
tools/aom/export.py      renders an animation in the original sprite's frame layout
tools/build_mod.py       builds the mod from your game files (build_mod.bat on Windows)
tools/concept_sheet.py   preview generator
tools/tests/             format round trips and a full build against a fake game folder
```

## Status

All 90 units are modelled and animated, and the exporter to the game is ready
for a first in-game test. Two buildings (House, Town Center) are designed.
Next come fixes from the first test, the last 5 units' sprite ids, then the
Castle, walls and the other buildings.
