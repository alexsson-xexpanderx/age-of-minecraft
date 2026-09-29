"""Build the Age of Minecraft mod for your own AoE2: The Conquerors + UserPatch 1.5.

    python tools/build_mod.py            (finds the game, or asks for its folder)
    python tools/build_mod.py --game "C:\\Program Files (x86)\\Microsoft Games\\Age of Empires II"

It reads your game's palette, sprite frame counts and graphics table, renders
every Minecraft sprite to match exactly, and writes a UserPatch data mod, a game
of its own called Age of Minecraft:

    Games\\age_of_minecraft.xml
    Games\\age_of_minecraft\\Data\\graphics.drs    your graphics.drs with our sprites swapped in
    Games\\age_of_minecraft\\aom_report.txt        what was replaced, skipped and why
    age2_x1\\age_of_minecraft.exe                 its own exe (by UserPatch's SetupAoC.exe), and shortcuts

Your own Data folder and exe are left alone. With --mode direct the sprites go into
Data\\graphics.drs itself instead (a backup is kept; --restore puts it back).
Options: --only militia,archer (just some units)  --jobs 4  --dry-run
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import shutil
import struct
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aom import farmland, interface, slp  # noqa: E402
from aom.datfile import Graphic, Terrain, read_graphics, read_terrains  # noqa: E402
from aom.drs import Drs  # noqa: E402
from aom.export import blank, render_frames  # noqa: E402
from aom.palette import Quantiser, parse_jasc  # noqa: E402
from aom.roster import ROSTER  # noqa: E402
from aom.slpmap import BLANK, NAME_PREFIXES, SHARED, SUFFIX_ACTIONS, TARGETS, Target  # noqa: E402
from aom import spritemap  # noqa: E402

# --only also accepts these groups of buildings and scenery
STATIC_GROUPS = {"buildings", "farms", "walls", "wonders", "nature", "decorations", "projectiles", "interface"}


def static_group(spec: dict) -> str:
    m = spec["model"]
    if m in ("wall", "gate", "gate_tower", "gate_site"):
        return "walls"
    if m in ("wonder", "monument"):
        return "wonders"
    if m in ("tree", "stump", "ore", "berry_bush", "rock", "plants", "cactus"):
        return "nature"
    if m in ("gaia", "haystack"):
        return "decorations"
    if m == "projectile":
        return "projectiles"
    return "buildings"


def blank_group(why: str) -> str:
    """The --only group a hidden layer belongs to, from the reason the sprite map gives."""
    for words, group in (("wall gate", "walls"), ("wonder monument", "wonders"), ("tree forest mine", "nature"),
                         ("javelin", "projectiles"), ("flag decoration", "decorations")):
        if any(w in why for w in words.split()):
            return group
    return "buildings"

MOD = "age_of_minecraft"  # the UserPatch data mod: Games\\age_of_minecraft, started by age2_x1\\age_of_minecraft.exe
NAME = "Age of Minecraft"
BACKUP = ".aom-backup"
# the game's own name, where a language file has it as a string of its own: the mod's copy calls it NAME
GAME_TITLES = ("Age of Empires II Expansion", "Age of Empires II: The Conquerors Expansion",
               "Age of Empires II: The Conquerors")
MENU_PICTURES = (50189, 50190, 50688)  # interfac.drs: the Conquerors main menu, its dialogue and its buttons
MENU_PALETTE = 50589

# The 18 Conquerors civilisations, in their standard ids (UserPatch data mod format).
CIVS = [
    (1, "briton", "british", 8, 530, -277, 360, 3), (2, "frankish", "french", 281, 531, -272, 363, 83),
    (3, "gothic", "goth", 41, 555, -279, 365, 16), (4, "teutonic", "teuton", 25, 554, -273, 364, 11),
    (5, "japanese", "japanese", 291, 560, -274, 366, 59), (6, "chinese", "chinese", 73, 559, -280, 362, 52),
    (7, "byzantine", "byzantin", 40, 553, -281, 361, 61), (8, "persian", "persian", 239, 558, -271, 367, 7),
    (9, "saracen", "saracen", 282, 556, -276, 368, 9), (10, "turkish", "turk", 46, 557, -278, 369, 10),
    (11, "viking", "viking", 692, 694, -282, 398, 49), (12, "mongol", "mongol", 11, 561, -275, 371, 6),
    (13, "celtic", "celt", 232, 534, -269, 370, 5), (14, "spanish", "spanish", 771, 773, -264, 60, 440),
    (15, "aztec", "aztecs", 725, 726, -268, 432, 24), (16, "mayan", "mayans", 763, 765, -266, 27, 4),
    (17, "hun", "huns", 755, 757, -265, 2, 21), (18, "korean", "koreans", 827, 829, -270, 450, 445),
]


def mod_xml() -> bytes:
    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             f'<configuration game="{MOD}">',
             f"  <name>{NAME}</name>",
             f"  <path>{MOD}</path>",
             '  <civilizations langId="10270" descId="20150" aiNameOffset="6840" uiBaseId="51100" uiStride="20" '
             'uiOffset="0">',
             '    <civilization id="0" name="gaia" soundFile="stream\\random.mp3" scoutUnit="448" uniqueUnit="0" '
             'eliteUniqueUnit="0" uniqueUnitLine="0" uniqueUnitUpgrade="0" uniqueResearch="0" />']
    for cid, name, sound, uu, euu, line, upgrade, research in CIVS:
        scout = 751 if name in ("aztec", "mayan") else 448
        lines.append(f'    <civilization id="{cid}" name="{name}" soundFile="stream\\{sound}.mp3" scoutUnit="{scout}" '
                     f'uniqueUnit="{uu}" eliteUniqueUnit="{euu}" uniqueUnitLine="{line}" '
                     f'uniqueUnitUpgrade="{upgrade}" uniqueResearch="{research}" />')
    lines += ["  </civilizations>", "</configuration>", ""]
    return b"\xef\xbb\xbf" + "\r\n".join(lines).encode("utf-8")  # UserPatch wants the BOM


# --------------------------------------------------------------------------- reading the game

def pick(folder: Path, name: str) -> Optional[Path]:
    """Case-insensitive file lookup (Windows installs vary: DATA, Data, data...)."""
    if not folder.is_dir():
        return None
    for p in folder.iterdir():
        if p.name.lower() == name.lower():
            return p
    return None


class Game:
    def __init__(self, root: Path, log):
        self.root = root
        self.data = pick(root, "Data")
        if self.data is None:
            raise SystemExit(f"No Data folder in {root}. Point --game at your Age of Empires II folder.")
        self.graphics_path = pick(self.data, "graphics.drs")
        if self.graphics_path is None:
            raise SystemExit(f"No graphics.drs in {self.data}.")
        backup = self.graphics_path.with_name(self.graphics_path.name + BACKUP)
        self.graphics = Drs(backup if backup.exists() else self.graphics_path)  # always start from the original
        self.patch = self._drs("gamedata_x1_p1.drs")
        # every archive that can hold sprites, the patch files first (they win when an id is in several)
        self.archives: list[tuple[str, Drs]] = []
        for name in ("gamedata_x1_p1.drs", "gamedata_x1.drs", "gamedata.drs"):
            drs = self.patch if name == "gamedata_x1_p1.drs" else self._drs(name)
            if drs is not None:
                self.archives.append((name, drs))
        self.archives.append((self.graphics_path.name, self.graphics))
        self.terrain = self._drs("terrain.drs")  # the ground's textures, farms among them
        interfac = self._drs("interfac.drs")
        self.interfac = interfac
        if interfac is None or interfac.get(50500, "bina") is None:
            raise SystemExit("Could not find the game palette (interfac.drs, 50500).")
        self.palette = parse_jasc(interfac.get(50500, "bina"))
        self.graphics_table: dict[int, Graphic] = {}
        dat = pick(self.data, "empires2_x1_p1.dat")
        if dat is not None and dat.with_name(dat.name + BACKUP).exists():
            dat = dat.with_name(dat.name + BACKUP)  # always start from the original rules
        self.dat_path = dat
        try:
            self.graphics_table = read_graphics(dat) if dat else {}
            log(f"graphics table: {len(self.graphics_table)} graphics read from {dat.name}")
        except Exception as exc:  # the build still works from the SLP headers alone
            log(f"graphics table: could not read ({exc}); using the sprite files only")
        self.by_slp: dict[int, list[Graphic]] = {}
        for g in self.graphics_table.values():
            self.by_slp.setdefault(g.slp, []).append(g)
        self.mod_strings: dict[int, str] = {}  # texts for the mod's own language file (standalone mode)
        self.terrains: list[Terrain] = []
        try:
            self.terrains = read_terrains(dat) if dat and self.graphics_table else []
            log(f"terrain table: {sum(t.enabled for t in self.terrains)} terrains in use")
        except Exception as exc:  # farms then fall back to the original game's texture ids
            log(f"terrain table: could not read ({exc}); farms use the original game's texture ids")

    def language_files(self) -> dict[str, Path]:
        """The game's language files (unit names and help texts), read from their originals if backed up."""
        from aom.langdll import FILES
        found = {}
        for name in FILES:
            p = pick(self.root, name)
            if p is not None:
                backup = p.with_name(p.name + BACKUP)
                found[p.name] = backup if backup.exists() else p
        return found

    def _drs(self, name: str) -> Optional[Drs]:
        p = pick(self.data, name)
        if p is None:
            return None
        backup = p.with_name(p.name + BACKUP)
        return Drs(backup if backup.exists() else p)

    def _searched(self) -> list[tuple[str, Drs]]:
        """The sprite archives, then terrain.drs (farms) and interfac.drs (the screen panels)."""
        more = [("terrain.drs", self.terrain)] if self.terrain is not None else []
        return self.archives + more + [("interfac.drs", self.interfac)]

    def original(self, slp_id: int) -> Optional[bytes]:
        for _, drs in self._searched():
            if slp_id in drs.ids():
                return drs.get(slp_id)
        return None

    def holders(self, slp_id: int) -> list[tuple[str, Drs]]:
        """Every archive that has this sprite (all of them get our version, so load order cannot matter)."""
        return [(name, drs) for name, drs in self._searched() if slp_id in drs.ids()]

    def layout(self, slp_id: int, num_frames: int) -> tuple[int, int, bool, int, str]:
        """(frames per angle, angle count, mirrored, extra frames, source) matching the original sprite.

        The game finds a frame as angle * frames per angle + frame, using the counts in the .dat, so
        the .dat wins. Some original files carry a few frames more than the .dat uses; those are
        filled with copies of the last frame so the file keeps its frame count."""
        fits = [(g.stored_angles * max(1, g.frame_count), g) for g in self.by_slp.get(slp_id, [])]
        fits = [(used, g) for used, g in fits if used <= num_frames]
        if fits:
            used, g = max(fits, key=lambda f: f[0])
            extra = num_frames - used
            source = f"dat, plus {extra} unused frames" if extra else "dat"
            return max(1, g.frame_count), max(1, g.angle_count), bool(g.mirroring), extra, source
        if num_frames % 5 == 0:
            return num_frames // 5, 8, True, 0, "guessed 8 mirrored angles"
        return num_frames, 1, False, 0, "guessed 1 angle"

    def name_targets(self, known: set[int]) -> list[Target]:
        """Sprites for units missing from the id list, found by their internal graphic names."""
        found = []
        for unit, prefixes in NAME_PREFIXES.items():
            for g in self.graphics_table.values():
                name = g.name.upper()
                action = SUFFIX_ACTIONS.get(name[-2:])
                if not action or g.slp <= 0 or g.slp in known or not name.startswith(tuple(prefixes)):
                    continue
                if g.deltas and not any(d.graphic_id == -1 for d in g.deltas):
                    continue  # its own sprite is never drawn
                owners = self.by_slp.get(g.slp, [])
                if not all(o.name.upper().startswith(tuple(prefixes)) for o in owners):
                    continue  # shared with other things (e.g. the petard's explosion)
                found.append(Target(g.slp, unit, action, f"found by name {g.name}"))
                known.add(g.slp)
        return found

    def delta_blanks(self, target_slps: set[int]) -> dict[int, str]:
        """Layered parts of the sprites we replace that no other graphic needs."""
        table = self.graphics_table
        if not table:
            return {}
        owners = {gid for gid, g in table.items() if g.slp in target_slps}
        parents = {gid for gid, g in table.items() if any(d.graphic_id in owners for d in g.deltas)}
        family = set(owners) | parents
        children = {d.graphic_id for gid in family for d in table[gid].deltas if d.graphic_id in table}
        family |= children
        users: dict[int, set[int]] = {}
        for gid, g in table.items():
            refs = {g.slp} | {table[d.graphic_id].slp for d in g.deltas if d.graphic_id in table}
            for s in refs:
                users.setdefault(s, set()).add(gid)
        blanks = {}
        for gid in children | parents:
            s = table[gid].slp
            if s > 0 and s not in target_slps and users.get(s, set()) <= family:
                blanks[s] = f"layer '{table[gid].name}' of a replaced sprite"
        return blanks


COMMON_INSTALLS = [
    r"C:\Program Files (x86)\Microsoft Games\Age of Empires II",
    r"C:\Program Files\Microsoft Games\Age of Empires II",
    r"C:\Program Files (x86)\Age of Empires II",
    r"C:\Program Files\Age of Empires II",
    r"C:\Games\Age of Empires II",
    r"D:\Games\Age of Empires II",
    r"C:\Age of Empires II",
]


def is_game(folder: Path) -> bool:
    data = pick(folder, "Data")
    return data is not None and pick(data, "graphics.drs") is not None


SEARCH_FOLDERS = [r"C:\Games", r"D:\Games", r"E:\Games", r"C:\Program Files (x86)", r"C:\Program Files",
                  r"C:\Program Files (x86)\Microsoft Games", r"C:\Program Files\Microsoft Games", "C:\\", "D:\\"]


def find_game(start: Path = Path(__file__).resolve()) -> Optional[Path]:
    """The game folder: one this mod was unpacked into, a usual install location, or any
    'Age of Empires...' folder in the usual places (e.g. C:\\Games\\Age Of Empires II Gold Edition)."""
    for folder in [start, *start.parents]:
        if is_game(folder):
            return folder
    for c in COMMON_INSTALLS:
        if is_game(Path(c)):
            return Path(c)
    for base in map(Path, SEARCH_FOLDERS):
        try:
            children = sorted(base.iterdir()) if base.is_dir() else []
        except OSError:
            continue
        for child in children:
            name = child.name.lower()
            if ("age of empires" in name or "aoe" in name or "age2" in name) and is_game(child):
                return child
    return None


def ask_for_game(log) -> Path:
    found = find_game()
    if found is not None:
        log(f"found your game at {found}")
        return found
    print("Could not find Age of Empires II automatically.")
    print("In File Explorer, open your Age of Empires II folder (the one with the Data folder),")
    print("click the address bar at the top, copy the path, paste it here and press Enter.")
    answer = Path(input("Game folder: ").strip().strip('"')).expanduser()
    if not is_game(answer):
        raise SystemExit(f"{answer} does not look like the game folder (no Data\\graphics.drs inside).")
    return answer


# --------------------------------------------------------------------------- rendering (worker processes)

_STATE: dict = {}


def _init(palette) -> None:
    _STATE["quant"] = Quantiser(palette)
    _STATE["units"] = {}


def _cost(job) -> int:
    """Roughly how long a job takes to render."""
    if job[0] == "unit":
        return job[4] * (job[5] // 2 + 1)
    if job[0] == "static":
        return job[3] * 4
    if job[0] == "interface":
        return 30
    return 20  # a farm texture: one render, cut into tiles


def _render(job) -> tuple[int, bytes, int]:
    if job[0] == "interface":
        _, slp_id, original, big = job
        try:
            data = interface.encode(original, big, _STATE["quant"].palette, _STATE["quant"])
        except ValueError as exc:  # its resource icons weren't found: it keeps its look
            return slp_id, None, str(exc)
        return slp_id, data, slp.info(data).num_frames
    if job[0] == "terrain":
        _, slp_id, stage, original = job
        data = farmland.encode(stage, original, _STATE["quant"])
        return slp_id, data, slp.info(data).num_frames
    if job[0] == "static":
        _, slp_id, spec, num_frames, frames, angles, mirrored, original = job
        from aom.props import render_static
        out = render_static(spec, num_frames, frames, angles, mirrored, _STATE["quant"], original)
        return slp_id, slp.encode(out), len(out)
    _, slp_id, unit_key, action, frames, angles, mirrored, extra = job
    units = _STATE["units"]
    if unit_key not in units:
        units[unit_key] = ROSTER[unit_key]()
    out = render_frames(units[unit_key], action, frames, angles, mirrored, _STATE["quant"])
    out += [out[-1]] * extra
    return slp_id, slp.encode(out), len(out)


def _safe_render(job):
    try:
        return _render(job)
    except Exception:
        return job[1], None, traceback.format_exc()


# --------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Age of Minecraft mod from your own AoE2 install.")
    ap.add_argument("--game", type=Path, help="your Age of Empires II folder (found automatically if left out)")
    ap.add_argument("--mode", choices=("upmod", "direct"), default="upmod",
                    help="upmod: separate UserPatch mod (default); direct: patch Data\\graphics.drs (with backup)")
    ap.add_argument("--only", help="comma-separated unit keys (see docs/UNITS.md), e.g. militia,archer,villager")
    ap.add_argument("--jobs", type=int, default=max(1, (mp.cpu_count() or 2) - 1))
    ap.add_argument("--dry-run", action="store_true", help="plan and report only, write nothing")
    ap.add_argument("--restore", action="store_true", help="undo --mode direct from the backups")
    ap.add_argument("--no-exe", action="store_true", help="do not run UserPatch's SetupAoC.exe to create the mod exe")
    ap.add_argument("--no-wonder-pacman", action="store_true",
                    help="leave the game rules alone (Pac-Man then only comes with the cheat)")
    ap.add_argument("--no-dat", action="store_true",
                    help="do not change empires2_x1_p1.dat at all (no Pac-Man at the Wonder, no Javelina sprites)")
    args = ap.parse_args(argv)

    report: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        report.append(msg)

    game_root = args.game.expanduser() if args.game else ask_for_game(log)
    if args.restore:
        return restore(game_root)
    game = Game(game_root, log)
    log(f"palette: {len(game.palette)} colours")

    only = set(args.only.split(",")) if args.only else None
    if only and not only <= set(ROSTER) | STATIC_GROUPS:
        raise SystemExit(f"unknown units: {', '.join(sorted(only - set(ROSTER) - STATIC_GROUPS))}")
    targets = list(TARGETS) + game.name_targets({t.slp for t in TARGETS})
    targets = [t for t in targets if only is None or t.unit in only]

    # sprites the .dat names but the game never shipped, which the mod adds (the Javelina's own)
    from aom import gameplay
    created: dict[int, int] = {}  # slp -> frame count
    jav = gameplay.javelina_graphics(game.graphics_table) if not args.no_dat else None
    if jav and (only is None or "javelina" in only):
        for name, g in jav.items():
            if game.original(g.slp) is None:
                created[g.slp] = g.stored_angles * max(1, g.frame_count)
    jobs, skipped, planned = [], [], []
    for t in targets:
        data = game.original(t.slp)
        if data is None and t.slp in created:
            g = jav[next(n for n, gg in jav.items() if gg.slp == t.slp)]
            jobs.append(("unit", t.slp, t.unit, t.action, max(1, g.frame_count), max(1, g.angle_count),
                         bool(g.mirroring), 0))
            planned.append((t, created[t.slp], max(1, g.frame_count), max(1, g.angle_count), bool(g.mirroring),
                            "new sprite"))
            continue
        if data is None:
            skipped.append((t, "not in your game files"))
            continue
        try:
            info = slp.info(data)
        except ValueError as exc:
            skipped.append((t, str(exc)))
            continue
        frames, angles, mirrored, extra, source = game.layout(t.slp, info.num_frames)
        jobs.append(("unit", t.slp, t.unit, t.action, frames, angles, mirrored, extra))
        planned.append((t, info.num_frames, frames, angles, mirrored, source))

    # buildings, walls, trees and decorations, found by name in the graphics table
    statics: list[tuple[spritemap.Sprite, int]] = []
    static_blanks: dict[int, str] = {}
    if game.graphics_table and (only is None or only & STATIC_GROUPS):
        taken = {t.slp for t in TARGETS} | {j[1] for j in jobs} | {s for s, _ in BLANK}
        sprite_plan = spritemap.plan(game.graphics_table, taken)
        spritemap.resolve_offsets(sprite_plan, game.graphics_table)
        wanted = (lambda spec: True) if only is None else (lambda spec: static_group(spec) in only)
        for sp in sprite_plan.sprites.values():
            if not wanted(sp.spec):
                continue
            data = game.original(sp.slp)
            if data is None:
                continue
            try:
                n = slp.info(data).num_frames
            except ValueError as exc:
                skipped.append((Target(sp.slp, sp.source, "static"), str(exc)))
                continue
            frames, angles, mirrored, _, _ = game.layout(sp.slp, n)
            original = game.original(sp.spec.get("fit_slp", sp.slp)) if sp.spec.get("fit") else None
            jobs.append(("static", sp.slp, sp.spec, n, frames, angles, mirrored, original))
            statics.append((sp, n))
        static_blanks = {s: why for s, why in sprite_plan.blanks.items()
                         if only is None or blank_group(why) in only}

    # farms are terrain: their textures in terrain.drs become Minecraft farmland
    farms: list[tuple[int, str, str, int]] = []
    if only is None or only & {"farms", "buildings"}:
        for slp_id, stage, source in farmland.farm_slps(game.terrains):
            data = game.original(slp_id)
            if data is None:
                skipped.append((Target(slp_id, "farm", stage), f"farm texture ({source}) not in your game files"))
                continue
            try:
                n = slp.info(data).num_frames
            except ValueError as exc:
                skipped.append((Target(slp_id, "farm", stage), str(exc)))
                continue
            jobs.append(("terrain", slp_id, stage, data))
            farms.append((slp_id, stage, source, n))

    # the panels at the top and bottom of the screen, one picture per civilisation and screen size
    panels: list[tuple[int, tuple[int, int]]] = []
    if only is None or "interface" in only:
        for slp_id, size, data, big in interface.panels(game.original):
            jobs.append(("interface", slp_id, data, big))
            panels.append((slp_id, size))

    target_slps = {j[1] for j in jobs}
    blanks = {} if only else {s: why for s, why in BLANK}
    if not only:
        blanks.update(game.delta_blanks(target_slps))
    blanks.update(static_blanks)
    blanks = {s: why for s, why in blanks.items() if s not in target_slps and game.original(s) is not None}

    log(f"plan: {len(jobs) - len(statics) - len(farms) - len(panels)} unit sprites, {len(statics)} building/scenery "
        f"sprites, {len(farms)} farm textures and {len(panels)} interface panels to render, {len(blanks)} layers to "
        f"blank, {len(skipped)} skipped")
    if args.dry_run:
        write_report(game, planned, skipped, blanks, report, Path.cwd() / "aom_report.txt", statics, farms, panels)
        return 0

    started = time.time()
    rendered: dict[int, bytes] = {}
    failed: list[tuple[int, str]] = []
    jobs.sort(key=_cost, reverse=True)  # big ones first
    with mp.Pool(args.jobs, initializer=_init, initargs=(game.palette,)) as pool:
        for n, (slp_id, data, count) in enumerate(pool.imap_unordered(_safe_render, jobs), 1):
            if data is None:  # one broken sprite must not stop the whole build: keep the original
                failed.append((slp_id, count))
                log(f"  could not render sprite {slp_id}; keeping the original. Details:\n{count}")
            else:
                rendered[slp_id] = data
            if n % 20 == 0 or n == len(jobs):
                print(f"  rendered {n}/{len(jobs)} sprites ({time.time() - started:.0f}s)")
    for s in blanks:
        rendered[s] = blank(slp.info(game.original(s)).num_frames)

    for slp_id, data in rendered.items():  # never ship a sprite whose frame count differs from the original
        want = created[slp_id] if slp_id in created else slp.info(game.original(slp_id)).num_frames
        got = slp.info(data).num_frames
        if want != got:
            raise SystemExit(f"internal error: SLP {slp_id} has {got} frames, the game expects {want}")

    try:
        out_dir = write_outputs(game, args.mode, rendered, log)
    except PermissionError as exc:
        raise SystemExit(f"Windows would not let us write {exc.filename}.\n"
                         "Your game is probably under Program Files: run the command prompt as administrator "
                         "(right-click > Run as administrator) and try again.")
    pacman = not args.no_wonder_pacman and (only is None or "pacman" in only)
    javelina = bool(created) or (jav is not None and (only is None or "javelina" in only))
    if not args.no_dat and (pacman or javelina):
        apply_gameplay(game, args.mode, log, pacman=pacman, javelina=javelina)
    exe_ok = False
    if args.mode == "upmod":
        mod_language(game, log)
        exe_ok = not args.no_exe and make_exe(game.root, log)
        make_shortcuts(game, exe_ok, log)
        save_menu_pictures(game, out_dir, log)
    write_report(game, planned, skipped, blanks, report, out_dir / "aom_report.txt", statics, farms, panels,
                 dict(failed))
    log(f"done in {time.time() - started:.0f}s")
    log("")
    log("RESULT")
    log(f"  sprites: {len(rendered)} written ({'direct into Data' if args.mode == 'direct' else out_dir})")
    if args.mode == "direct":
        log("  To play: start the game as usual. To undo: double-click restore_original.bat")
    else:
        log(f"  To play: double-click '{NAME}' on your desktop or in your game folder.")
        if exe_ok:
            log(f"  Or start {game.root / 'age2_x1' / (MOD + '.exe')}. Your normal game is not changed.")
        else:
            log(f"  {NAME}'s own exe needs UserPatch's SetupAoC.exe in your game folder; until it is there the")
            log(f"  shortcut starts it with age2_x1.exe GAME={MOD}. Your normal game is not changed.")
    return 0


def find_setup(root: Path) -> Optional[Path]:
    """UserPatch's installer, SetupAoC.exe: in the game folder or one folder below it."""
    folders = [root] + sorted(d for d in root.iterdir() if d.is_dir())
    for folder in folders:
        hit = pick(folder, "SetupAoC.exe")
        if hit is not None:
            return hit
    return None


def make_exe(root: Path, log) -> bool:
    """UserPatch starts a data mod through its own exe: SetupAoC.exe -g:<mod> creates age2_x1\\<mod>.exe."""
    exe = root / "age2_x1" / f"{MOD}.exe"
    setup = find_setup(root)
    if setup is None:
        log(f"mod exe: SetupAoC.exe (the UserPatch installer) is not in {root}, so the mod exe can't be made.")
        return False
    if os.name != "nt":
        log(f"mod exe: on Windows, run  {setup.name} -g:{MOD}  in {setup.parent}")
        return False
    log(f"mod exe: running {setup} -g:{MOD}")
    log("         (if a UserPatch window opens, click its Install / Run button and wait for it to finish)")
    try:
        done = subprocess.run([str(setup), f"-g:{MOD}"], cwd=setup.parent, timeout=600, check=False,
                              capture_output=True, text=True, errors="replace")
        log(f"mod exe: SetupAoC.exe finished with code {done.returncode}")
        for line in (done.stdout + done.stderr).strip().splitlines()[-20:]:
            log("         " + line)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"mod exe: could not run SetupAoC.exe ({exc})")
    if exe.exists():
        add_icon(exe, log)
        return True
    folder = pick(root, "age2_x1")
    found = sorted(p.name for p in folder.iterdir() if p.suffix.lower() == ".exe") if folder else []
    log(f"mod exe: {exe} was not created. Exes in age2_x1: {', '.join(found) or 'none'}")
    return False


def add_icon(exe: Path, log) -> None:
    """Our icon in the mod's own exe (only that copy; the game's exe is never changed)."""
    from aom import appicon
    try:
        data = exe.read_bytes()
        new, notes = appicon.into_exe(data)
    except (OSError, ValueError, struct.error) as exc:
        log(f"icon: could not put it into {exe.name} ({exc})")
        return
    if new != data:
        tmp = exe.with_name(exe.name + ".tmp")
        tmp.write_bytes(new)
        tmp.replace(exe)
    log(f"icon: {exe.name} has the {NAME} icon ({', '.join(notes) or 'it has no icon pictures'})")


def make_shortcuts(game: Game, exe_ok: bool, log) -> None:
    """'Age of Minecraft' shortcuts with our icon, on the desktop and in the game folder. They start the mod's exe,
    or without one the game's exe with GAME=<mod> (UserPatch then loads Games\\<mod>.xml)."""
    from aom import appicon
    folder = (pick(game.root, "Games") or game.root / "Games") / MOD
    folder.mkdir(parents=True, exist_ok=True)
    icon = folder / f"{MOD}.ico"
    icon.write_bytes(appicon.ico())
    age2 = pick(game.root, "age2_x1") or game.root / "age2_x1"
    target = age2 / f"{MOD}.exe" if exe_ok else (pick(age2, "age2_x1.exe") or age2 / "age2_x1.exe")
    arguments = "" if exe_ok else f"GAME={MOD}"
    if os.name != "nt":
        log(f"shortcut: on Windows, '{NAME}' on the desktop and in the game folder starts {target.name} {arguments}")
        return

    def q(value) -> str:  # a PowerShell string
        return "'" + str(value).replace("'", "''") + "'"

    script = ("$shell = New-Object -ComObject WScript.Shell; "
              f"foreach ($dir in @([Environment]::GetFolderPath('Desktop'), {q(game.root)})) {{ "
              f"$s = $shell.CreateShortcut((Join-Path $dir {q(NAME + '.lnk')})); $s.TargetPath = {q(target)}; "
              f"$s.Arguments = {q(arguments)}; $s.WorkingDirectory = {q(target.parent)}; "
              f"$s.IconLocation = {q(str(icon) + ',0')}; $s.Description = {q(NAME)}; $s.Save() }}")
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                              timeout=60, capture_output=True, text=True, errors="replace")
        if done.returncode:
            raise OSError(done.stderr.strip()[-300:] or f"code {done.returncode}")
        log(f"shortcut: '{NAME}' on your desktop and in {game.root} (starts {target.name} {arguments}".rstrip() + ")")
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"shortcut: could not make it ({exc}); start {target} {arguments} instead")


def mod_language(game: Game, log) -> None:
    """The mod's own language_x1_p1.dll: the game's, with Pac-Man's texts (when he was patched) and the game's name
    as NAME added. A UserPatch mod reads its own copy first, so the game's language files stay as they are."""
    from aom import langdll, pe
    files = {name.lower(): path.read_bytes() for name, path in game.language_files().items()}
    strings = dict(game.mod_strings)
    for name in langdll.FILES:
        try:
            for sid, text in (langdll.all_strings(files[name]).items() if name in files else ()):
                if text.strip() in GAME_TITLES and sid not in strings:
                    strings[sid] = NAME
        except (langdll.DllError, pe.PeError, struct.error):
            continue
    if not strings:
        log("language: nothing to add to the mod's language file")
        return
    p1 = files.get("language_x1_p1.dll")
    try:
        data = langdll.with_strings(p1, strings) if p1 else langdll.build_dll(strings)
    except (langdll.DllError, pe.PeError, struct.error) as exc:
        log(f"language: could not add to language_x1_p1.dll ({exc}); the mod gets a new one with its texts")
        data = langdll.build_dll({**langdll.all_strings(p1), **strings})
    write_game_file(game, "upmod", "language_x1_p1.dll", data, log)
    log("language: the mod's language_x1_p1.dll has " + ", ".join(f"{sid} {text[:40]!r}"
                                                                   for sid, text in sorted(strings.items())))


def save_menu_pictures(game: Game, folder: Path, log) -> None:
    """The game's main menu pictures as PNG files, so a Minecraft menu can be drawn over exactly the same places."""
    from aom import appicon
    raw = game.interfac.get(MENU_PALETTE, "bina")
    palette = parse_jasc(raw) if raw else game.palette
    out = folder / "menu_originals"
    notes = []
    for sid in MENU_PICTURES:
        data = game.original(sid)
        try:
            frames = slp.decode(data) if data else []
        except (ValueError, IndexError, struct.error) as exc:
            notes.append(f"{sid}: could not read ({exc})")
            continue
        for k, f in enumerate(frames):
            out.mkdir(parents=True, exist_ok=True)
            rgba = np.zeros((*f.pixels.shape, 4), np.uint8)
            solid = (f.pixels >= 0) & (f.pixels < 256)
            rgba[solid, :3], rgba[solid, 3] = palette[f.pixels[solid]], 255
            team = f.pixels >= slp.PLAYER
            rgba[team, :3], rgba[team, 3] = palette[16 + f.pixels[team] - slp.PLAYER], 255
            rgba[f.pixels == slp.SHADOW] = (0, 0, 0, 128)
            (out / f"{sid}_{k:02d}.png").write_bytes(appicon.png(rgba))
        if frames:
            sizes = sorted({f"{f.pixels.shape[1]}x{f.pixels.shape[0]}" for f in frames})
            notes.append(f"{sid}: {len(frames)} pictures ({', '.join(sizes)})")
    log(f"menu pictures: {'; '.join(notes) or 'none found'}" + (f", saved in {out}" if out.exists() else ""))


def write_outputs(game: Game, mode: str, rendered: dict[int, bytes], log) -> Path:
    changes: dict[str, tuple[Drs, set[int]]] = {}
    for s in rendered:  # into every archive that has the sprite; new sprites go into graphics.drs
        for name, drs in game.holders(s) or [(game.graphics_path.name, game.graphics)]:
            changes.setdefault(name, (drs, set()))[1].add(s)
    if mode == "upmod":
        games = pick(game.root, "Games") or (game.root / "Games")
        mod_data = games / MOD / "Data"
        mod_data.mkdir(parents=True, exist_ok=True)
        for name, (drs, ids) in changes.items():
            for s in ids:
                drs.put(s, rendered[s])
            drs.write(mod_data / name)
            log(f"wrote {mod_data / name} ({len(ids)} sprites)")
        (games / f"{MOD}.xml").write_bytes(mod_xml())
        log(f"wrote {games / (MOD + '.xml')}")
        return games / MOD
    # direct: patch the game's own files, keeping the originals once
    for name, (drs, ids) in changes.items():
        live = Path(drs.path)
        if live.name.endswith(BACKUP):
            live = live.with_name(live.name[:-len(BACKUP)])
        backup = live.with_name(live.name + BACKUP)
        if not backup.exists():
            shutil.copy2(live, backup)
            log(f"backed up {live.name} -> {backup.name}")
        drs.path = backup  # read untouched entries from the original copy from now on
        for s in ids:
            drs.put(s, rendered[s])
        tmp = live.with_name(live.name + ".tmp")
        drs.write(tmp)
        tmp.replace(live)
        log(f"patched {live} ({len(ids)} sprites)")
    return game.data


def write_game_file(game: Game, mode: str, name: str, data: bytes, log, folder: Path = None) -> None:
    """Write a changed game file: into the mod's Data folder, or over the game's own file in `folder` (the
    Data folder by default), backed up once."""
    if mode == "upmod":
        games = pick(game.root, "Games") or (game.root / "Games")
        path = games / MOD / "Data" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log(f"wrote {path}")
        return
    folder = folder or game.data
    live = pick(folder, name) or (folder / name)
    backup = live.with_name(live.name + BACKUP)
    if live.exists() and not backup.exists():
        shutil.copy2(live, backup)
        log(f"backed up {live.name} -> {backup.name}")
    tmp = live.with_name(live.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(live)
    log(f"patched {live}")


def apply_gameplay(game: Game, mode: str, log, pacman: bool = True, javelina: bool = True) -> None:
    """The .dat changes (Pac-Man at the Wonder, the Javelina's own sprites), Pac-Man's icon and his name."""
    from aom import gameplay
    if game.dat_path is None:
        log(".dat changes: no empires2_x1_p1.dat found, skipped")
        return
    archives = list(game.archives) + ([("interfac.drs", game.interfac)] if game.interfac is not None else [])
    sheets = gameplay.icon_sheets(archives) if pacman else []
    icon = gameplay.new_icon_index(sheets) if sheets else None
    quant = Quantiser(game.palette)
    new_sheets = []
    for name, drs, sheet in sheets:  # every copy, so the load order cannot matter
        new_sheet, msg = gameplay.add_icon(sheet, icon, quant)
        new_sheets.append((name, drs, new_sheet))
        log(f"Pac-Man icon in {name} (sheet {gameplay.UNIT_ICONS}, {slp.info(sheet).num_frames} icons): {msg}")
    if pacman and not sheets:
        log(f"Pac-Man icon: no unit icon sheet ({gameplay.UNIT_ICONS}) in {', '.join(n for n, _ in archives)}")
    if not any(new for _, _, new in new_sheets):
        icon = None  # he keeps the Monkey Boy's icon
    raw = game.dat_path.read_bytes()
    waves, sound_ids, sound_drs = {}, None, None
    if pacman:  # his sounds go where the game finds new files: the patch archive if there is one
        from aom import sounds
        sound_name, sound_drs = next(((n, d) for n, d in game.archives if n.lower() == "gamedata_x1_p1.drs"),
                                     (game.graphics_path.name, game.graphics))
        waves = sounds.pacman_sounds()
        free = free_resource_ids(game, raw, sum(len(v) for v in waves.values()))
        sound_ids = {name: [next(free) for _ in variants] for name, variants in waves.items()}
    patch, notes = gameplay.patch_dat(raw, game.graphics_table, pacman, javelina, icon, sound_ids)
    for note in notes:
        log(note)
    if patch is None:
        return
    write_game_file(game, mode, "empires2_x1_p1.dat", patch.data, log)
    if not patch.pacman_strings:
        return
    touched: dict[str, Drs] = {}
    for name, drs, new_sheet in new_sheets if icon is not None else []:
        if new_sheet is not None:
            drs.put(gameplay.UNIT_ICONS, new_sheet)
            touched[name] = drs
    if patch.sounds_added:
        from aom import sounds
        for name, variants in waves.items():
            for rid, x in zip(sound_ids[name], variants):
                sound_drs.put(rid, sounds.wav(x), "wav")
        touched[sound_name] = sound_drs
        log(f"Pac-Man's sounds: {sum(len(v) for v in waves.values())} WAV files in {sound_name} "
            f"(ids {min(min(v) for v in sound_ids.values())}-{max(max(v) for v in sound_ids.values())})")
    for name, drs in touched.items():  # each archive written once
        tmp = game.data / (name + ".aom-new")
        drs.write(tmp)
        write_game_file(game, mode, name, tmp.read_bytes(), log)
        tmp.unlink()
    rename_pacman(game, mode, patch.pacman_strings, log)


def free_resource_ids(game: Game, raw_dat: bytes, n: int, start: int = 15500):
    """Resource ids no archive in the Data folder uses and no sound in the .dat refers to."""
    from aom import datfile
    used: set[int] = set()
    for p in game.data.iterdir():
        if p.suffix.lower() == ".drs":
            backup = p.with_name(p.name + BACKUP)  # what a rebuild starts from
            try:
                drs = Drs(backup if backup.exists() else p)
            except (OSError, struct.error):
                continue
            for kind in drs.index:
                used |= drs.ids(kind)
    for _, drs in game.archives:
        for kind in set(drs.index) | set(drs.added):
            used |= drs.ids(kind)
    try:
        data = datfile.decompress(raw_dat)
        table = datfile.sound_table(data)
        at = table.count_at + 2
        for _ in range(table.count):
            _, _, files, _ = struct.unpack_from("<hhHi", data, at)
            at += 10
            for _ in range(files):
                used.add(datfile.SOUND_FILE.unpack_from(data, at)[1])
                at += datfile.SOUND_FILE.size
    except (ValueError, struct.error):
        pass
    rid = start
    for _ in range(n):
        while rid in used:
            rid += 1
        used.add(rid)
        yield rid


def rename_pacman(game: Game, mode: str, strings: dict[str, int], log) -> None:
    """Pac-Man's name in the language files. The mod exe reads language_x1_p1.dll from the mod's Data folder."""
    from aom import gameplay
    paths = game.language_files()
    changed, notes = gameplay.rename_pacman({name: p.read_bytes() for name, p in paths.items()}, strings)
    for note in notes:
        log(note)
    if mode == "upmod":  # the game's files stay as they are: his texts go into the mod's own language file
        from aom import langdll
        texts = {name.lower(): data for name, data in {**{n: p.read_bytes() for n, p in paths.items()},
                                                        **changed}.items()}
        for sid in strings.values():
            text = next((t for t in (langdll.read_string(texts[n], sid) for n in langdll.FILES if n in texts) if t),
                        None)
            if text:
                game.mod_strings[sid] = text
        return
    for name, data in changed.items():
        write_game_file(game, mode, name, data, log, folder=game.root)


def restore(root: Path) -> int:
    data = pick(root, "Data")
    restored = 0
    for p in [*(data.iterdir() if data else []), *root.iterdir()]:  # Data files, and the language files
        if p.is_file() and p.name.endswith(BACKUP):
            live = p.with_name(p.name[:-len(BACKUP)])
            shutil.copy2(p, live)
            p.unlink()
            restored += 1
            print(f"restored {live}")
    print("nothing to restore" if not restored else "original files are back")
    return 0


def write_report(game: Game, planned, skipped, blanks, header: list[str], path: Path, statics=(),
                 farms=(), panels=(), failed=None) -> None:
    lines = ["Age of Minecraft build report", "=" * 30, *header, "", "REPLACED (slp, unit, action, frames x angles)"]
    for t, n, frames, angles, mirrored, source in sorted(planned, key=lambda p: p[0].slp):
        m = " mirrored" if mirrored else ""
        lines.append(f"  {t.slp:6d}  {t.unit:24s} {t.action:7s} {n:4d} frames = {frames} x {angles} angles{m}"
                     f"  [{source}] {t.note}")
    lines += ["", "BUILDINGS AND SCENERY (slp, found by, model, frames)"]
    for sp, n in sorted(statics, key=lambda x: x[0].slp):
        spec = sp.spec
        what = spec["model"] + "".join(f" {k}={spec[k]}" for k in ("code", "style", "age", "kind", "forest",
                                                                     "letter", "name", "direction", "open",
                                                                     "part", "anchor_offset", "half") if k in spec)
        lines.append(f"  {sp.slp:6d}  {sp.source:14s} {what:60s} {n:3d} frames [{spec.get('mode')}] {sp.note}")
    lines += ["", "FARMS (terrain texture slp, stage, found by, tiles)"]
    lines += [f"  {s:6d}  {stage:8s} {farmland.STAGES[stage]:32s} {source:28s} {n:3d} tiles"
              for s, stage, source, n in farms]
    lines += ["", "INTERFACE PANELS (slp, screen size, result)"]
    for s, (w, h) in panels:
        result = "planned" if failed is None else ("Minecraft style" if s not in failed else failed[s])
        lines.append(f"  {s:6d}  {w}x{h:<5d} {result}")
    lines += ["", "BLANKED LAYERS"] + [f"  {s:6d}  {why}" for s, why in sorted(blanks.items())]
    lines += ["", "SKIPPED"] + [f"  {t.slp:6d}  {t.unit:24s} {t.action:7s} {why}" for t, why in skipped]
    covered = {p[0].unit for p in planned}
    covered |= {unit for unit, host in SHARED.items() if host in covered}
    lines += ["", "UNITS WITHOUT SPRITES YET: " + ", ".join(sorted(set(ROSTER) - covered))]
    if game.graphics_table:
        lines += ["", "GRAPHICS TABLE (id, name, slp, frames, angles, mirror, deltas with their x/y offsets)"]
        for gid, g in sorted(game.graphics_table.items()):
            deltas = ",".join(str(d.graphic_id) + (f"@{d.offset_x}/{d.offset_y}" if d.offset_x or d.offset_y else "")
                              for d in g.deltas)
            lines.append(f"  {gid:5d} {g.name:22s} {g.slp:6d} {g.frame_count:4d} {g.angle_count:3d} {g.mirroring:2d}"
                         f"  {deltas}")
    if game.terrains:
        lines += ["", "TERRAIN TABLE (id, enabled, name, file, slp, rows x cols)"]
        lines += [f"  {t.id:3d} {int(t.enabled):2d} {t.name:14s} {t.filename:14s} {t.slp:6d} {t.rows} x {t.cols}"
                  for t in game.terrains]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {path}")


class _Tee:
    """Show output in the window and keep a copy in aom_build_log.txt."""

    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, text):
        self.stream.write(text)
        self.fh.write(text)
        self.fh.flush()

    def flush(self):
        self.stream.flush()
        self.fh.flush()


def cli() -> int:
    log_path = Path(__file__).resolve().parent.parent / "aom_build_log.txt"
    try:
        fh = open(log_path, "w", encoding="utf-8")
    except OSError:
        log_path = Path.home() / "aom_build_log.txt"
        fh = open(log_path, "w", encoding="utf-8")
    sys.stdout, sys.stderr = _Tee(sys.stdout, fh), _Tee(sys.stderr, fh)
    print(f"Age of Minecraft build - a copy of this output is saved to {log_path}")
    try:
        return main()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print("\nERROR: " + exc.code)
            return 1
        return exc.code or 0
    except Exception:
        traceback.print_exc()
        print(f"\nERROR: the build crashed. Please send {log_path}")
        return 1
    finally:
        print(f"\n(log saved to {log_path})")


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(cli())
