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

The build takes about two to ten minutes, depending on your PC. It writes:

```
Games\AgeOfMinecraft.xml                 the UserPatch mod definition
Games\AgeOfMinecraft\Data\graphics.drs   your graphics with the Minecraft sprites swapped in
Games\AgeOfMinecraft\aom_report.txt      what was replaced, what was skipped, and why
age2_x1\AgeOfMinecraft.exe               created by UserPatch's SetupAoC.exe
```

> If your game is under *Program Files*, Windows may block writing there and
> the window says so. Then right-click `build_mod.bat` and choose
> **Run as administrator**.

## 4. Play

Start **`age2_x1\AgeOfMinecraft.exe`**. Your normal `age2_x1.exe` stays
exactly as it was.

**No `AgeOfMinecraft.exe`?** The end of the black window (under **RESULT**)
says why. Everything shown there is also saved to **`aom_build_log.txt`**,
next to `build_mod.bat`. You have two options:

1. Make the exe yourself. Open your game folder in File Explorer, type `cmd`
   in the address bar and press Enter, then run
   `SetupAoC.exe -g:AgeOfMinecraft`. This needs UserPatch's installer
   `SetupAoC.exe` in that folder.
2. Skip the exe: double-click **`build_mod_direct.bat`**. It puts the
   Minecraft sprites into your normal game, so you start the game as usual.
   Your original `graphics.drs` is backed up first, and
   **`restore_original.bat`** puts it back.

## Options

| Command | What it does |
|---|---|
| `build_mod.bat "<game>" --only militia,archer,villager` | build only some units, for a quick test (keys are listed in [UNITS.md](UNITS.md)) |
| `build_mod.bat "<game>" --only buildings,walls,wonders,nature,decorations,projectiles` | build only buildings and scenery (any of these groups) |
| `build_mod.bat "<game>" --dry-run` | only plan and write `aom_report.txt` |
| `build_mod_direct.bat` | put the sprites straight into `Data\graphics.drs` (no mod exe needed); a backup is kept as `graphics.drs.aom-backup` |
| `restore_original.bat` | undo `build_mod_direct.bat` (graphics, the rules file and the icons) |
| `build_mod.bat "<game>" --no-wonder-pacman` | keep the game's rules unchanged (no Pac-Man at the Wonder) |
| `build_mod.bat "<game>" --no-dat` | do not touch `empires2_x1_p1.dat` at all (no Pac-Man at the Wonder, and the Javelina keeps the Wild Boar's look) |

## What to expect in this test

* All unit sprites are replaced: standing, walking, attacking, dying and
  decaying, plus villager work and carry animations. Male and female
  villagers share the Minecraft villager models.
* All buildings are replaced, in the five village styles (West European,
  Central European, Middle Eastern, Asian, Meso-American) and every age, with
  walls, gates, towers, castles, docks, farms and the eighteen wonders.
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
* Still original: cliffs, bridges, terrain, fire and explosions, ships sinking,
  and the game's interface. Unit names are unchanged.

## Easter eggs

**Pac-Man at the Wonder.** Once you have built a Wonder, select it: its
first button trains **Pac-Man** (200 food, 100 gold, 30 seconds, 250 hit
points), with his own Pac-Man icon. This works for every civilisation. It is
the only change the mod makes to the game's rules; `--no-wonder-pacman`
leaves the rules alone. His name in the game is still the cheat unit's.

> Multiplayer: because the rules change, every player needs the same build
> of the mod, or the game goes out of sync.

**Cheats.** Two hidden cheat units are replaced. In a single-player game,
press **Enter**, type the cheat and press **Enter** again; the unit appears
next to your Town Center:

| Cheat | You get |
|---|---|
| `furious the monkey boy` | **Pac-Man**, who chomps as he runs and attacks, and dies the arcade way |
| `i love the monkey head` | a **ghost** in your team colour (red for player 2, like Blinky) |

In a multiplayer game, cheats only work if "Allow cheats" is ticked in the
game setup.

**Please send back** `Games\AgeOfMinecraft\aom_report.txt` and a few
screenshots. The report lists your game's full graphics table, so anything
that looks off can be mapped exactly in the next round.
