# Trying Age of Minecraft in your game

The mod is built **on your own PC, from your own game files**. The build
reads your game's colour palette, how many frames each original sprite has,
and the graphics table in your `.dat` file. It then renders every Minecraft
sprite to match exactly. Your original files are not changed.

You need **Age of Empires II: The Conquerors** (Gold Edition), **UserPatch
1.5**, and **Python 3**.

## 1. Install Python (one time)

1. Download Python 3 from <https://www.python.org/downloads/> and run the
   installer. Tick **"Add python.exe to PATH"**.
2. That's all. The helper script installs the one library it needs
   (`numpy`) by itself.

## 2. Get the mod

Download this repository as a ZIP (on GitHub: **Code → Download ZIP**) and
extract it anywhere, for example to your Desktop.

## 3. Build it

Open the extracted folder and **double-click `build_mod.bat`**. Leave it in
that folder: it needs the `tools` folder next to it.

* It looks for your game in the usual places, for example
  `C:\Program Files (x86)\Microsoft Games\Age of Empires II`.
* If it can't find the game, it asks for the folder. Open your
  **Age of Empires II** folder in File Explorer (the one with the `Data`
  folder inside), click the address bar at the top, copy the path, paste it
  into the black window and press Enter.
* Tip: if you extract the mod *inside* your Age of Empires II folder, it
  always finds the game.

The build takes about two to ten minutes, depending on your PC. It makes
**Age of Minecraft** a game of its own: your normal Age of Empires exe and
files are not changed. It writes:

```
Games\age_of_minecraft.xml                    the UserPatch mod definition ("Age of Minecraft")
Games\age_of_minecraft\Data\gamedata_x1_p1.drs  every Minecraft sprite, farm, panel, the menu and screens, the lava, Pac-Man's and the Dragon's icons and sounds
Games\age_of_minecraft\Data\empires2_x1_p1.dat  its rules: Pac-Man and the Dragon at the Wonder, the lava, the Javelina's own look
Games\age_of_minecraft\Script.RM\Team Lava Islands.rms  the Team Lava Islands map
Games\age_of_minecraft\Data\language_x1_p1.dll  its own texts: Pac-Man's and the Dragon's names, and "Age of Minecraft"
Games\age_of_minecraft\age_of_minecraft.ico    its icon, a villager king
Games\age_of_minecraft\menu_originals\         your game's main menu pictures (for a Minecraft menu)
Games\age_of_minecraft\screen_originals\       your game's other screens (setup, loading, dialogues...)
Games\age_of_minecraft\aom_report.txt         what was replaced, what was skipped, and why
age2_x1\age_of_minecraft.exe                  its own exe, made by UserPatch's SetupAoC.exe: its window says "Age of Minecraft"
Age of Minecraft (shortcut)                   on your desktop and in the game folder, with the icon
```

> If your game is under *Program Files*, Windows may block writing there and
> the window says so. Then right-click `build_mod.bat` and choose
> **Run as administrator**.

## 4. Play

Double-click **Age of Minecraft** on your desktop (or in your game folder).
It starts `age2_x1\age_of_minecraft.exe`. Your normal game starts as always
and stays exactly as it was.

**Used `build_mod_direct.bat` before?** That one changed your normal game's
files. Double-click **`restore_original.bat`** once to give your normal game
its original files back; Age of Minecraft doesn't need them.

**The UserPatch window.** The first build opens it to make
`age_of_minecraft.exe`: click its **Install** button and wait; the build waits
for it too. Later builds keep that exe and don't open the window again.

**No `age_of_minecraft.exe`?** The exe is made by UserPatch's installer,
`SetupAoC.exe`, which must be in your game folder (it comes with UserPatch 1.5
from <https://userpatch.aiscripters.net/>). Without it the shortcut still
works: it starts your normal exe with `GAME=age_of_minecraft`, which tells
UserPatch to load Age of Minecraft instead. The end of the black window (under
**RESULT**) says which one you got; everything shown there is also saved to
**`aom_build_log.txt`**, next to `build_mod.bat`.

**Rather have the Minecraft look in your normal game?** Double-click
**`build_mod_direct.bat`**: it puts everything into your normal game's files,
each one backed up first, and **`restore_original.bat`** puts them back.

## Options

| Command | What it does |
|---|---|
| `build_mod.bat "<game>" --only militia,archer,villager` | build only some units, for a quick test (keys are listed in [UNITS.md](UNITS.md)) |
| `build_mod.bat "<game>" --only buildings,farms,walls,wonders,nature,decorations,projectiles` | build only buildings and scenery (any of these groups; `buildings` includes the farms) |
| `build_mod.bat "<game>" --only interface` | build only the Minecraft-style panels at the top and bottom of the screen |
| `build_mod.bat "<game>" --dry-run` | only plan and write `aom_report.txt` |
| `build_mod_direct.bat` | put the sprites straight into `Data\graphics.drs`, the farms into `Data\terrain.drs` and the panels into `Data\interfac.drs` (no mod exe needed); each file is backed up first as `<name>.aom-backup` |
| `restore_original.bat` | undo `build_mod_direct.bat` (graphics, farms, panels, the rules file, the icons, the language files and the Team Lava Islands map) |
| `build_mod.bat "<game>" --no-wonder-pacman` | keep the game's rules unchanged (no Pac-Man or Dragon at the Wonder, no lava, and the cheat unit keeps its name and icon) |
| `build_mod.bat "<game>" --no-dat` | do not touch `empires2_x1_p1.dat` at all (no Pac-Man or Dragon at the Wonder, no lava, and the Javelina keeps the Wild Boar's look) |

## What to expect in this test

* All unit sprites are replaced: standing, walking, attacking, dying and
  decaying, plus villager work and carry animations. Male and female
  villagers share the Minecraft villager models.
* All buildings are replaced, in the five village styles (West European,
  Central European, Middle Eastern, Asian, Meso-American) and every age, with
  walls, gates, towers, castles, docks and the eighteen wonders.
* Farms are Minecraft farmland. A farm is part of the ground in this game,
  so the build replaces its textures in `terrain.drs`. The wheat grows in
  rows with bare farmland between them. While a villager builds a farm, the
  wheat sprouts and grows. A finished farm is ripe golden wheat, and an
  exhausted farm is dry farmland. The edges blend into the
  grass as the original farms do.
* The main menu is a Minecraft world on a clear day: the buttons are a
  shield, a book on a lectern, crossed diamond swords, a map, an anvil and
  more, in the same places as before, each name on a Minecraft button, under
  an "AGE OF MINECRAFT" block title. The Single Player menu opens on
  Minecraft's dark dirt background, with Minecraft buttons.
* The panels at the top and bottom of the screen are Minecraft style. The
  parchment is the grey of Minecraft's inventory, the dark area behind the
  minimap is an inventory slot, and the carved frames are planks. The
  resource icons are an oak log (wood), a leg of meat (food), a gold block,
  cobblestone (stone) and a villager's face (population), all the same size
  and each as far from its amount. If a panel's icons
  can't be found, that panel keeps its original look, and the report says so.
* The map is replaced too: forests, chopped trees, gold and stone mines,
  berry bushes, rocks, plants, animals, fish and decorations.
* Projectiles: Minecraft arrows and bolts, spinning axes, snowballs from the
  snow golem skirmishers, cobblestone from mangonels and TNT from the bombard
  cannon. Their ground shadows are the game's own.
* Original sprites are built in layers (shadows, flags, roof pieces, sails).
  The build reads these layers from your `.dat` and hides the extra ones, so
  only the Minecraft sprite shows.
* The Elite Eagle Warrior uses the Eagle Warrior's sprites, as in the
  original game.
* The Javelina borrows the Wild Boar's sprites in the original game (its own
  were never shipped). The mod renders its own pig sprites and points the
  Javelina at them in `empires2_x1_p1.dat`, with a pig carcass that holds the
  same food as the boar's.
* A few original sprite files hold a frame or two more than the game uses.
  The build follows the game's own frame layout for those and fills the
  unused frames, so every direction still lines up.
* Still original: cliffs, bridges, the rest of the terrain, fire and explosions, ships sinking,
  and the other menus. Unit names are unchanged, except Pac-Man's, the giant's and the Dragon's.

## Easter eggs

**Pac-Man at the Wonder.** Once you have built a Wonder, select it: its
first button trains **Pac-Man** (500 food, 500 gold, 5 minutes, 250 hit
points; he takes 1 population like any unit). He is big, taller than a
knight on horseback, and takes as much room as a Mangonel, so nothing stands
inside him, and he still fits through gates. He has his own Pac-Man icon, and
the game calls him **Pac-Man**. He is faster than any unit in the game, even
the Cobra Car cheat: 5 tiles a second, more than three times a Hussar. This
works for every civilisation. He is infantry, not a wild animal like the cheat
unit: he boards Transport Ships (and gets off again on any shore), walks on
beaches, garrisons like a foot soldier, and gets the
Blacksmith's infantry upgrades and your civilisation's infantry bonuses.

He has his own arcade sounds: click on him and he goes "waka-waka" (or
boings, or giggles), orders get a "wakawakawaka" or a big CHOMP and
"nom nom", the Wonder plays a little jingle when he is ready, every bite
chomps, and he dies with a sad "wah wah wah waaah" and two pops. Listen to
them in `previews/sounds/`. He, the Dragon and the lava below are the mod's
changes to the game's rules; `--no-wonder-pacman` leaves the rules alone.

**The Dragon at the Wonder.** The Wonder's second button trains a **Dragon**
(300 food, 300 gold, 2 minutes, 600 hit points, 1 population), for every
civilisation. It is black like Minecraft's Ender Dragon, with purple eyes and
wings in your team colour, and it is always up in the air, its shadow on the
ground below. It flies over land, water and the deep sea, so it needs no
ship. It spits fireballs: 40 damage every 3 seconds, at a range of 6 tiles,
and its fire burns buildings as well as units. Armour: 4 against melee, 6
against arrows. It flies at 1.4 tiles a second, as fast as Light Cavalry. It
counts as an archer, so the Blacksmith's archer upgrades give it more range.
It has its own sounds: it growls, snorts or rumbles when you click on it,
beats its wings when it moves, roars when you send it to attack and when the
Wonder trains it, every fireball goes "fwoosh", and it dies with a falling
roar, a thud as it hits the ground and a last groan. Listen to them in
`previews/sounds/`. Its icon is the dragon's head breathing fire. It lives in a slot the
game has but never uses (the "Advanced Heavy Crossbowman"), so no other unit
changes. With `build_mod_direct.bat` its help text is too long for the
game's own language file: hovering over its button there says only "Create
Dragon".

**Team Lava Islands.** A new map, like Team Islands but with a sea of
lava instead of water (dark red crust with glowing cracks): each team shares
an island, and the lava around it shows orange on the minimap. In the game setup, set the map style
to **Custom** and pick **Team Lava Islands**. Ships sail on the lava as they
would on water: build your Docks on the lava by your island's beach (every
island has one, all round), then Transport Ships, warships and Fish Traps.
Nothing lives in lava, so there are no fish; each island has more berries,
deer, boar and sheep instead. Like Team Islands, the islands are grassland,
desert, mountains or snow, at random. One thing changes on every map: Docks
can no longer be built in shallow fords (they can on lava instead). With
`build_mod_direct.bat` the map goes into your game's `Random` folder, and
`restore_original.bat` removes it again.

His name lives in the game's language files (`language_x1_p1.dll`,
`language_x1.dll`, `language.dll`, in the game's main folder). Age of
Minecraft has its own `language_x1_p1.dll` with his name added, so your
game's files stay as they are. `build_mod_direct.bat` renames him in the
game's own files instead, keeping a backup of each file it changes, and
`restore_original.bat` puts them back. Windows 11's Smart App Control refuses
language files that were changed ("Bad Image", error 0xc0e90002); if you see
that, Smart App Control has to be off.

> Multiplayer: because the rules change, every player needs the same build
> of the mod, or the game goes out of sync.

**Cheats.** Four hidden cheat units are replaced. In a single-player game,
press **Enter**, type the cheat and press **Enter** again; the unit appears
next to your Town Center:

| Cheat | You get |
|---|---|
| `furious the monkey boy` | **Pac-Man**, who chomps as he runs and attacks, and dies the arcade way |
| `i love the monkey head` | a **ghost** in your team colour (red for player 2, like Blinky) |
| `how do you turn this on` | the **Cobra Car**, built from blocks in your team colour, with white racing stripes |
| `to smithereens` | a **giant red Pac-Man**, bigger than a Castle and a Wonder side by side: Pac-Man's bite and armour, 10000 hit points, and he no longer blows himself up. He boards and leaves Transport Ships, and takes as much room on the map as a Mangonel, so he fits through gates; his picture covers everything near him. His icon is a red Pac-Man |

In a multiplayer game, cheats only work if "Allow cheats" is ticked in the
game setup.

**Please send back** `Games\age_of_minecraft\aom_report.txt`, the pictures in
`Games\age_of_minecraft\menu_originals\` and `screen_originals\` (zip the
folders) and a few screenshots. The report lists your game's full graphics table, so anything
that looks off can be mapped exactly in the next round.
