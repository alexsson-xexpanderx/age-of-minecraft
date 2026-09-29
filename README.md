# Age of Minecraft

A mod for **Age of Empires II: Gold Edition** that replaces the units and
buildings with blocky, pixel-art Minecraft-style ones. There are villagers in
robes, diamond-armoured champions, skeleton archers, pillager crossbowmen and
snow-golem skirmishers. Knights ride horses in Minecraft horse armour. Ravagers
serve as battering rams, dispenser minecarts as mangonels, and a TNT cannon as
the bombard. Creepers are the petards, and the fleet sails under team-coloured
wool. All 90 units are modelled, and every building too: houses, town centers,
castles, walls and gates in five Minecraft village styles that upgrade with
each age, the eighteen wonders, wheat farms, and the whole map (forests, gold
and stone, berry bushes, animals, fish and decorations). Even the panels at the
top and bottom of the screen look like Minecraft's inventory. And an easter
egg: build a Wonder and it trains Pac-Man.

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
then double-click **Age of Minecraft** on your desktop. The build reads your own
game files and makes Age of Minecraft a game of its own (a UserPatch mod with
its own `age_of_minecraft.exe` and a villager king icon), so your normal game
stays untouched. Full steps and options are in [docs/INSTALL.md](docs/INSTALL.md).

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
| `previews/village.png` | a Dark Age village with fields, a forest and mines |
| `previews/buildings.png` | every building in the five village styles and the ages |
| `previews/fortifications.png` | walls, gates, towers and castles |
| `previews/walls.png` | wall lines in every direction and with corners, placed as the game places them |
| `previews/wonders.png` | the eighteen wonders and the scenario monuments |
| `previews/nature.png` | trees, resources and map decorations |
| `previews/farms.png` | farms, which the game draws as ground: being built, grown and exhausted |
| `previews/interface.png` | the resource bar and bottom panel in the Minecraft style, on a stand-in for the game's own panel |
| `previews/menu.png` | the main menu: a block village on a clear day, with the game's texts and buttons drawn over it |
| `previews/screens.png` | the other screens as the deepslate hall, and the loading screen, on stand-in screens |
| `previews/player_colors.png` | a unit in all 8 player colours |
| `previews/roster_easter.png` | the easter eggs: Pac-Man and a ghost in the cheat units' slots |
| `previews/sounds/pacman_*.wav` | Pac-Man's sounds: clicking on him, orders, training, bites and his death |

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
tools/aom/animals.py     sheep, chicken, goat, hoglin, pig, wolf, ocelot, phantom, parrot, fish, dolphin
tools/aom/roster.py      the full roster and preview groups
tools/aom/blocks.py      Minecraft block textures (woods, stones, ores, glass, leaves, workstations)
tools/aom/voxel.py       block structures: shapes (stairs, slabs, fences, walls, panes), roofs, domes
tools/aom/styles.py      the five village styles and their materials per age
tools/aom/structures.py  houses, town center, mill, camps, barracks, range, stable, market, dock...
tools/aom/fortifications.py  walls, gates, towers and castles
tools/aom/wonders.py     the eighteen wonders and scenario monuments
tools/aom/nature.py      trees, stumps, mines, berry bushes, rocks and plants
tools/aom/gaia.py        map decorations: yurts, ruins, graves, flags, torches, the relic
tools/aom/farmland.py    farms, which are terrain: Minecraft farmland and wheat in terrain.drs
tools/aom/interface.py   the screen panels repainted: planks, inventory grey, slots and item icons
tools/aom/menu.py        the main menu: a block village by day, every button a Minecraft thing, names on Minecraft buttons
tools/aom/screens.py     the other screens: found by their screen files, redrawn as the deepslate hall
tools/aom/loadscreen.py  the loading screen: the logo, open sky and a floating block island, in a palette of its own
tools/aom/props.py       renders buildings and scenery in the original sprite's frame layout
tools/aom/slp.py         SLP 2.0N sprite encoder/decoder
tools/aom/drs.py         DRS archive reader/writer
tools/aom/palette.py     game palette and colour matching
tools/aom/datfile.py     graphics and terrain table reader for empires2_x1_p1.dat
tools/aom/datunits.py    reads and patches the civilisations' unit tables in the .dat
tools/aom/gameplay.py    Pac-Man at the Wonder: the .dat change, his icon, name and sounds
tools/aom/langdll.py     reads and changes strings in the game's language DLLs
tools/aom/pe.py          Windows DLL/exe resources: read them, give a copy new ones in an added section
tools/aom/appicon.py     the villager king icon: the .ico file, and in place in the mod's own exe (and PNGs)
tools/aom/sounds.py      Pac-Man's sounds, synthesised in an 8-bit arcade style
tools/aom/easter.py      Pac-Man and the ghost
tools/aom/slpmap.py      which original sprite id each unit render replaces
tools/aom/spritemap.py   finds buildings, walls, trees and decorations by name in the .dat
tools/aom/export.py      renders an animation in the original sprite's frame layout
tools/build_mod.py       builds the mod from your game files (build_mod.bat on Windows)
tools/concept_sheet.py   preview generator
tools/tests/             format round trips and a full build against a fake game folder
```

## Status

All 90 units, every building in all five styles and ages, walls and gates,
the wonders, the farms, and the map's nature and animals are modelled and
exported. The next step is testing them together in the game.
