# Handoff: continuing on the Windows laptop (2026-10-05)

The player is moving from the Linux PC (where Claude Code ran) to their Windows laptop, which has the game, and will
continue there with Claude Desktop. This file carries everything the next session needs. The full conversation was
too large to export (246 MB).

**To the next Claude session:** read this whole file, then CLAUDE.md. Branch `claude/busy-ritchie-8lktbr`.

## The player and how they work

- Plays Age of Empires II: The Conquerors + UserPatch 1.5 on Windows 11. Builds with `build_mod.bat` (the standalone
  "Age of Minecraft" mod, upmod mode) from the branch zip:
  https://github.com/alexsson-xexpanderx/age-of-minecraft/archive/refs/heads/claude/busy-ritchie-8lktbr.zip
- After every change, push and give the zip link. Commit subjects describe the change from the player's side.
- Running the game is cumbersome for them: show previews instead of asking for test runs, and batch all fixes into
  one change. They like choosing between options.
- They get annoyed by command-line arguments. Give them double-click `.bat` files instead (CRLF line endings).
- **Pac-Man is hands-off.** Never change anything about Pac-Man (name, .dat patch, icon, sounds, model, or the code
  paths feeding them) without asking. Removing his rename once upset them badly.
- **No unasked extras.** No jokes, slogans or extra text. Offer extras as options, don't build them in.
- Never commit their game files. On the Linux PC a copy lived in `~/Downloads/Age Of Empires II Gold Edition/`.
- "Bad Image" 0xc0e90002 on a language DLL was Windows Smart App Control, not the mod (turned off 2026-09-29).
- Don't make the computer players aware of Pac-Man (they declined it).

## Recent work (all pushed)

- **Dragon** at the Wonder (button 2), in the unused Advanced Heavy Crossbowman slot 493. It flies (terrain restriction
  0, layer 22), spits fireballs (unused TORCH2 graphic, SLP 15601) and has its own synthesised sounds (`roars.py`).
  Untested in game.
- **Giant red Pac-Man** (the "to smithereens" cheat's Saboteur, 706) no longer blows himself up: resource capacity 1,
  no hero flag 32. Untested in game.
- **Team Lava Islands** map: terrain 15 ("Old Water") becomes dark lava, Docks stand on lava instead of in Shallows,
  and the map goes in the mod's `Script.RM`. Untested in game.
- **Trains** (`tools/aom/rails.py`): see below. Built and driven in game by the player. **It crashes.**

## The train crash: cause found (2026-10-10, on the Windows laptop)

Windows' error log (`Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000}`) had six crashes of
`age_of_minecraft.exe` on 2026-10-04, all access violations, at a different place each time (0x4dc179, 0x5, 0x57114d,
0xcb23, 0x57121f, 0x439758; image base 0x400000, no relocations). Disassembling the player's exe (capstone):

- 0x5710a7-0x5712a1 is a unit's "leave pass graphics behind" code: `world+0x64`[row] is the row's 16-byte records per
  terrain (exit, enter, walk graphic id, replication as an int), `world+0x44`[id] the graphic. It calls 0x4d5890.
- 0x4d5890 makes the ground piece. Its lifetime is `round(frames x frame time) + 1` seconds. It files the piece in a
  wheel of **60 one-second slots** (`manager+0xc`, cursor `+0xfc`, advanced by 0x4d5d70 every 1000 ms) at
  `cursor + lifetime`, minus 60 **once** (0x4d5b03). Lifetimes over 60 also count rounds, but the slot is never taken
  modulo 60, so the piece's pointer is written past the wheel: over the cursor (+0xfc), the map pointer (+0x100), and
  the heap after. Memory is corrupted and the game dies later somewhere unrelated, more quickly when a blocked train
  drops piece after piece.
- Crash times against commits: 18:52 (86f0eea, 86400 s), 19:04 (aada632, 300 s), 19:50 + 19:51 (5883298, 300 s),
  22:43 + 22:48 (533719e, 300 s). fb7ca30 (31 s, pushed 22:46) was too late for the 22:48 crash, and there is no crash
  in the log after it. So the "fb7ca30 crashed even when not blocked" report was most likely the 533719e build.
- Vanilla tracks last 31 s, so the bug never shows in the unmodded game. That's also why Wine (tested on fb7ca30) and
  the `--only rails` bisect (fb7ca30's rails) did not crash.

Fixed in code: `rails.WHEEL` = 60, `rails.lifetime(g)`, and `track_graphic` refuses cart tracks lasting longer, so the
trains are left unchanged instead of crashing. Test `test_rails_last_under_a_minute`.

**To do:** the player builds the whole mod with `build_mod.bat` and plays their usual game to confirm no crash.
Options to offer (don't build unasked): rails lasting up to ~54 s (9 pictures of 6 s; changes the graphic's frame
count, which `track_graphic` now pins at 5). Truly permanent rails cannot come from pass graphics at all.

Also fixed: on Windows the tests wrote an "Age of Minecraft" shortcut on the real desktop pointing at a temp folder
(`build_mod.DESKTOP` now redirects it in tests), and `test_find_game` found the real game in `C:\Games`.

### What the trains are now (commit fb7ca30 and later)
- The Trade Cart (units 128 empty, 204 loaded) looks like a Minecraft train: a furnace minecart pulling a chest
  minecart, 1.6 times its old size (`TRAIN_SCALE`). It is named "Train".
- It lays its own rails. It keeps the Trade Cart's terrain restriction row 20, whose "pass graphics" (what a unit
  leaves on the ground behind it; vanilla: wheel tracks in snow) become the cart tracks (graphic CARTSTPS, 5705) on
  every passable terrain. The tracks get our rail SLP (15602 in a full build) and keep every other setting:
  5 frames × 6 s, so 30 s. The siege units that shared row 20 move to row 7, which is exactly equal (they leave
  footprints in snow).
- The Villager-built rails (Sea Wall 788, gravel terrain 16) were tried first and dropped. The player wants the
  train to lay rails by itself when right-clicked onto another player's Market, never through buildings or trees,
  and ideally permanently. Permanence via decals isn't safe: pieces pile up.

### Crash history (the player's Windows PC; "game just closes", no message; all explained above)
| Build | What it had | Result |
|---|---|---|
| 86f0eea | new row 5 for trains, decal = GALLY_A1 (16 dirs, 1 frame of 86400 s) | crash when blocked by units |
| aada632 | row 21 (sea buildings'), GALLY_A1 50 frames × 6 s | crash |
| 5883298 | row 20 kept, siege moved to row 7, GALLY_A1 8 dirs | crash |
| 533719e | decal = CARTSTPS itself, 50 frames × 6 s | crash |
| fb7ca30 | CARTSTPS 5 frames × 6 s (vanilla timing), frame props 16 | crash, "even when not blocked" |

- The player confirmed that rails always appeared behind the train, on land too, in every build.
- **Bisect** (commit 98883f3 added the bat files): `test_1_rails_only.bat` (`--only rails`: the .dat train changes,
  old horse-cart look) did **not** crash. `test_2_train_look_only.bat` (`--only trade_cart`: the new look, no .dat
  changes) did **not** crash. So each part works alone; the full build crashes. Note: `--only` also leaves out
  Pac-Man, the Dragon, lava, the giant and every other sprite.
- **The player's setup:** `build_mod.bat`; Standard game (random map), single player with ONE computer player on THEIR
  team (no enemies), Post-Imperial Age, highest resources.

### Reproduction attempt on Linux (Wine on a hidden Xvfb screen, full mod build)
- Scenario editor test: 4 trains of player 1 trading with an allied player 2 Market, a block of 25 archers on the
  route. The trains traded (gold came in), laid rails and steered round the archers. **No crash in 7 minutes.**
- Death Match, two allied computers (population limit was 25 by mistake): no crash in 26:40 game time, but the
  computers did no trading (trade profit 0). That doesn't cover computer-run trains.
- An exact copy of the player's setup (me + 1 allied computer, Post-Imperial, high resources, my own Market and 5
  trains queued) was set up but not finished.
- Wine notes, if needed again: the game draws only at 800x600 (`Screen Width/Height` registry values). The chat box
  (typing cheats) freezes the picture. DDrawCompat crashes under Xvfb. Input via XTest (ctypes libXtst). The EULA
  flag `HKCU\...\Age of Empires II: The Conquerors Expansion\1.0\EULA FIRSTRUN=1` was copied from the player's own
  Wine setup, where they had accepted it. Scratchpad helper: `x.py` (shot/click/drag/key/type).

### Hypotheses from before the cause was found (now ruled out or moot)
1. The **computer ally's trains**: the AI trains and sends its own trains to the player's Market. None of my tests had
   AI trains. The AI might do something with them that crashes together with the changed row/graphics.
2. Something about the **combination**: the full build's other parts (Dragon, lava, giant, all sprites) with the trains.
   The Dragon and lava are themselves untested in game; the crash may not even be the trains'.
3. **Windows-only behaviour.** Wine didn't crash in the same scenario.

### Next steps on the Windows laptop (as planned before; step 1 found the cause)
1. After a crash, look in **Event Viewer → Windows Logs → Application** for the "Application Error" entry (faulting
   module, exception code, offset). On Windows Claude can run `Get-WinEvent -FilterHashtable @{LogName='Application';
   Id=1000} -MaxEvents 5 | Format-List` in PowerShell. This is the most valuable clue. Also look for UserPatch logs
   in the game folder.
2. Reproduce the player's exact game: allied computer, Post-Imperial, high resources, trains to the ally's Market.
   Watch whether the computer builds its own trains.
3. Bisect further with double-click bats. Ideas:
   - `--only rails,trade_cart` (both train parts, nothing else);
   - the full build without the train .dat changes. That needs a new option, e.g. `--no-rails` setting `rails=False`
     in `build_mod.main`.
4. Possible fallbacks, as options for the player:
   - keep the train look and drop the self-laid rails;
   - rails only on the player's trains;
   - shorter or no tracks.

## Where things are in the code
- `tools/aom/rails.py`: the trains' .dat patch (`patch`, `siege_row`, `track_graphic`), the rail pictures
  (`track`, `track_slp`) and the texts (`TEXTS`). Wired up in `gameplay.patch_dat(..., rails=)` and
  `build_mod.apply_gameplay(..., rails=)`; texts by `build_mod.name_train`.
- `tools/aom/siege.py` `trade_cart()`: the train model. `animation.py`: wheels 1-8 and the smoke (`SMOKE`).
- `previews/rails.png`: trains laying rails round a wood (`concept_sheet.rails_scene`).
- Tests: `python tools/tests/test_export.py` (18 tests, about 30 s; all pass on Windows too).
- With trains left out (`--no-wonder-pacman` or `--only` without `rails`), the .dat comes out byte-identical to
  before.
