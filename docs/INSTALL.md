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

The build takes about one to five minutes, depending on your PC. It writes:

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
| `build_mod.bat "<game>" --dry-run` | only plan and write `aom_report.txt` |
| `build_mod_direct.bat` | put the sprites straight into `Data\graphics.drs` (no mod exe needed); a backup is kept as `graphics.drs.aom-backup` |
| `restore_original.bat` | undo `build_mod_direct.bat` |

## What to expect in this first test

* All unit sprites are replaced: standing, walking, attacking, dying and
  decaying, plus villager work and carry animations. Male and female
  villagers share the Minecraft villager models.
* Some original sprites are built from several layers, such as ram heads and
  wheels, ship sails, and the war wagon. The build hides the extra layers
  where the `.dat` shows they belong only to the replaced unit. These units
  are the most likely to look wrong in the first test.
* The Halberdier, Petard, Javelina, Elite Eagle Warrior and Elite Cannon
  Galleon aren't mapped yet. Their original sprite ids will be picked out of
  your `aom_report.txt`.
* Unit names in the game are unchanged for now.
* Buildings are unchanged; they come after the units.

**Please send back** `Games\AgeOfMinecraft\aom_report.txt` and a few
screenshots. The report lists your game's full graphics table, so anything
that looks off can be mapped exactly in the next round.
