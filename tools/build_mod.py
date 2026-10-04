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

from aom import farmland, interface, loadscreen, menu, screens, slp  # noqa: E402
from aom.datfile import Graphic, Terrain, read_graphics, read_terrains  # noqa: E402
from aom.drs import Drs  # noqa: E402
from aom.export import blank, render_frames  # noqa: E402
from aom.palette import Quantiser, parse_jasc  # noqa: E402
from aom.roster import ROSTER  # noqa: E402
from aom.slpmap import BLANK, NAME_PREFIXES, SHARED, SUFFIX_ACTIONS, TARGETS, Target  # noqa: E402
from aom import spritemap  # noqa: E402

# --only also accepts these groups of buildings and scenery
STATIC_GROUPS = {"buildings", "farms", "walls", "wonders", "nature", "decorations", "projectiles", "interface",
                 "rails"}
LAVA = "lava"  # and this: the lava, its Dock rule and the Team Lava Islands map
RAILS = "rails"  # the rails' sprites (a group above), and the rails and trains in the .dat


def static_group(spec: dict) -> str:
    m = spec["model"]
    if m in ("wall", "gate", "gate_tower", "gate_site"):
        return "walls"
    if m == "rail":
        return "rails"
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
    for words, group in (("rail", "rails"), ("wall gate", "walls"), ("wonder monument", "wonders"),
                         ("tree forest mine", "nature"), ("javelin", "projectiles"),
                         ("flag decoration", "decorations")):
        if any(w in why for w in words.split()):
            return group
    return "buildings"

MOD = "age_of_minecraft"  # the UserPatch data mod: Games\\age_of_minecraft.xml, its folder, age2_x1\\age_of_minecraft.exe
LEFTOVERS = ("Games/AoM.xml", "age2_x1/AoM.exe")  # what one earlier build called the mod
NAME = "Age of Minecraft"
BACKUP = ".aom-backup"
# the game's own name, where a language file has it as a string of its own: the mod's copy calls it NAME
GAME_TITLES = ("Age of Empires II Expansion", "Age of Empires II: The Conquerors Expansion",
               "Age of Empires II: The Conquerors")
MENU_PICTURES = (50189, 50190, 50688)  # interfac.drs: the Conquerors main menu, its dialogue and its buttons
MENU_PALETTE = 50589
EXE_TITLE = "Age of Empires II Expansion"  # the game window's title: the mod's own exe calls it NAME

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
             # where the game's own language files have each civilisation's name (10230 + civ: Britons 10231),
             # help text (20150 + civ - 1) and its computer players' names: the Conquerors civs' at 4660 +
             # aiNameOffset + 20 per civ from the Spanish (4800). WololoKingdoms' 10270 and 6840 are for its own
             # language file; here they left the Conquerors civs' computer players without a name.
             '  <civilizations langId="10230" descId="20150" aiNameOffset="140" uiBaseId="51100" uiStride="20" '
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

    def data_file(self, fid: int) -> Optional[bytes]:
        """A data file (a palette, a screen file) from the first archive that has it."""
        for _, drs in self._searched():
            if fid in drs.ids("bina"):
                return drs.get(fid, "bina")
        return None

    def screens(self) -> tuple[list[screens.Screen], dict[int, int]]:
        """The screen files, and every screen picture with its palette (not the main menu or the panels)."""
        found = screens.read(sorted(set().union(*(d.ids("bina") for _, d in self._searched()))), self.data_file)
        slps = sorted(s for _, d in self._searched() for s in d.ids() if s in screens.INTERFACE)
        return found, screens.pictures(found, slps, self.original, set(MENU_PICTURES))

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
    if job[0] in ("interface", "menu", "screen", "team copies", "recolour"):
        return 30
    return 20  # a farm texture: one render, cut into tiles


def _render(job) -> tuple[int, bytes, int]:
    if job[0] == "team copies":
        _, slp_id, original, palettes, found = job
        data = screens.encode_copies(original, found, palettes)
        return slp_id, data, slp.info(data).num_frames
    if job[0] == "screen":
        _, slp_id, original, palettes, out = job
        data = screens.encode(slp_id, original, palettes, out)
        return slp_id, data, slp.info(data).num_frames
    if job[0] == "menu":  # the menu's picture, drawn for its new palette (the old one is for the old glow colours)
        _, slp_id, original, palette, new = job
        frames = menu.pictures(slp.decode(original), palette, menu.Nearest(new))
        data = slp.encode(frames, props=slp.frame_props(original))
        return slp_id, data, len(frames)
    if job[0] == "recolour":  # the same pictures, each pixel the nearest colour in the new palette
        _, slp_id, original, palette, new = job
        near = menu.Nearest(new).indices(np.asarray(palette, np.int64)[:256, :3])
        frames = [slp.SlpFrame(np.where((f.pixels >= 0) & (f.pixels < 256), near[np.clip(f.pixels, 0, 255)],
                                        f.pixels).astype(np.int16), f.hotspot) for f in slp.decode(original)]
        data = slp.encode(frames, props=slp.frame_props(original))
        return slp_id, data, len(frames)
    if job[0] == "food":  # UserPatch's food icon, which it draws over the bar's: the bar's, on clear pixels
        _, slp_id, original = job
        data = interface.food_icon(original, _STATE["quant"])
        return slp_id, data, slp.info(data).num_frames
    if job[0] == "interface":
        _, slp_id, original = job
        try:
            data = interface.encode(original, _STATE["quant"].palette, _STATE["quant"])
        except ValueError as exc:  # its resource bar is not the known one: it keeps its look
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
    if only and not only <= set(ROSTER) | STATIC_GROUPS | {LAVA}:
        raise SystemExit(f"unknown units: {', '.join(sorted(only - set(ROSTER) - STATIC_GROUPS - {LAVA}))}")
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
    screen_files, screen_pictures = game.screens()
    panels: list[tuple[int, tuple[int, int]]] = []
    loading, teams = None, []
    if only is None or "interface" in only:
        for slp_id, size, data in interface.panels(game.original):
            jobs.append(("interface", slp_id, data))
            panels.append((slp_id, size))
        data = game.original(interface.FOOD)
        if data is not None:  # UserPatch's own food icon (a steak on black), drawn over the bar's
            jobs.append(("food", interface.FOOD, data))
            panels.append((interface.FOOD, tuple(slp.info(data).sizes[0][:2])))
        data, raw = game.original(menu.MENU), game.interfac.get(menu.PALETTE, "bina")
        old_menu = new_menu = None  # the main menu's palette, and its new one
        if data is not None and raw is not None:
            if menu.known([(w, h) for w, h, _, _ in slp.info(data).sizes]):
                old_menu = parse_jasc(raw)
                new_menu = menu_palette(game, old_menu)
                jobs.append(("menu", menu.MENU, data, old_menu, new_menu))
                panels.append((menu.MENU, (800, 600)))
                icons = game.original(MENU_PICTURES[2])
                if icons is not None:  # the menu's checkboxes and arrows: the same, in its new palette
                    jobs.append(("recolour", MENU_PICTURES[2], icons, old_menu, new_menu))
                    panels.append((MENU_PICTURES[2], tuple(slp.info(icons).sizes[0][:2])))
                menu_settings(game, screen_files, new_menu, log)
            else:
                log(f"main menu: picture {menu.MENU} is not the one this build knows; it keeps its look")
        # the other screens: the setup screens, the dialogues, the history, the loading screen
        for sid in sorted(screens.RESTYLED):
            data = game.original(sid)
            if data is None:
                continue
            if not screens.fits(sid, data):
                log(f"screen picture {sid} is not the one this build knows; it keeps its look")
                continue
            ids = [p for p in screens.palette_ids(sid, screen_files) if game.data_file(p)]
            palettes = [old_menu if p == menu.PALETTE and old_menu is not None else parse_jasc(game.data_file(p))
                        for p in ids]  # (the archives already hold the menu's new one)
            out = [new_menu if p == menu.PALETTE and new_menu is not None else pal for p, pal in zip(ids, palettes)]
            if palettes:  # a picture shown with the main menu's palette is drawn for its new colours
                jobs.append(("screen", sid, data, palettes, out if menu.PALETTE in ids else None))
                panels.append((sid, tuple(slp.info(data).sizes[0][:2])))
        copied = team_copies(game)
        teams = team_places(game, [screens.TEAMS] + [sid for sid, _, _ in copied])
        teams += [f"  {sid:6d}  pictures {', '.join(str(k) for k, _ in found)} are the team marks (or nearly): "
                  "redrawn too" for sid, _, found in copied]
        for sid, data, found in copied:
            raws = [game.data_file(p) for p in screens.palette_ids(screens.TEAMS, screen_files)]
            jobs.append(("team copies", sid, data, [parse_jasc(raw) for raw in raws if raw], found))
            panels.append((sid, tuple(slp.info(data).sizes[0][:2])))
            log(f"team marks: picture{'s' if len(found) > 1 else ''} {', '.join(str(k) for k, _ in found)} of {sid} "
                f"{'are copies' if len(found) > 1 else 'is a copy'} of the team marks ({screens.TEAMS}): redrawn too")
        loading = loading_plan(game, screen_files, log)
        if loading:
            panels.append((screens.LOADING, (loadscreen.W, loadscreen.H)))

    target_slps = {j[1] for j in jobs}
    blanks = {} if only else {s: why for s, why in BLANK}
    if not only:
        blanks.update(game.delta_blanks(target_slps))
    blanks.update(static_blanks)
    blanks = {s: why for s, why in blanks.items() if s not in target_slps and game.original(s) is not None}

    log(f"plan: {sum(j[0] == 'unit' for j in jobs)} unit sprites, {len(statics)} building/scenery "
        f"sprites, {len(farms)} farm textures and {len(panels)} interface pictures to render, {len(blanks)} layers to "
        f"blank, {len(skipped)} skipped")
    if args.dry_run:
        write_report(game, planned, skipped, blanks, report, Path.cwd() / "aom_report.txt", statics, farms, panels,
                     screen_files=screen_files, screen_pictures=screen_pictures, teams=teams)
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
    if only is None or "interface" in only:
        if loading:
            try:
                rendered[screens.LOADING] = draw_loading(game, *loading, log)
            except Exception:  # it keeps its look
                failed.append((screens.LOADING, traceback.format_exc()))
                log(f"  could not draw the loading screen; keeping the original. Details:\n{failed[-1][1]}")

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
    dragon = not args.no_wonder_pacman and (only is None or "dragon" in only)
    lava = not args.no_wonder_pacman and (only is None or LAVA in only)
    rails = not args.no_wonder_pacman and (only is None or RAILS in only)
    javelina = bool(created) or (jav is not None and (only is None or "javelina" in only))
    if not args.no_dat and (pacman or javelina or dragon or lava or rails):
        apply_gameplay(game, args.mode, log, pacman=pacman, javelina=javelina, dragon=dragon, lava=lava, rails=rails)
    exe_ok = False
    if args.mode == "upmod":
        mod_archive(game, log)
        mod_language(game, log)
        exe_ok = not args.no_exe and make_exe(game.root, log)
        make_shortcuts(game, exe_ok, log)
        save_menu_pictures(game, out_dir, log)
        save_screen_pictures(game, screen_pictures, out_dir, log)
    write_report(game, planned, skipped, blanks, report, out_dir / "aom_report.txt", statics, farms, panels,
                 dict(failed), screen_files, screen_pictures, teams)
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


def team_copies(game: Game) -> list[tuple[int, bytes, list[tuple[int, int]]]]:
    """Every other interface picture, in any archive, that is one of the team marks or nearly (the game, or
    UserPatch, may draw one of those): (id, file, [(picture, mark)])."""
    data = game.original(screens.TEAMS)
    if data is None or not screens.fits(screens.TEAMS, data):
        return []
    marks = slp.decode(data)
    shapes = {m.pixels.shape for m in marks}
    ids = set()
    for _, drs in game._searched():
        ids |= {s for s in drs.ids() if s in screens.INTERFACE}
    out = []
    for sid in sorted(ids - {screens.TEAMS}):
        other = game.original(sid)
        try:
            if other is None or not any((h, w) in shapes for w, h, _, _ in slp.info(other).sizes):
                continue
            found = screens.copies(marks, slp.decode(other))
        except (ValueError, IndexError, struct.error):
            continue
        if found:
            out.append((sid, other, found))
    return out


def team_places(game: Game, ids: list[int]) -> list[str]:
    """Report lines: every archive of the game's that has these pictures, with their sizes (before the build)."""
    lines = []
    for sid in ids:
        for name, drs in game.holders(sid):
            try:
                shapes = ", ".join(f"{w}x{h}" for w, h, _, _ in slp.info(drs.get(sid)).sizes)
            except (ValueError, IndexError, struct.error):
                shapes = "unreadable"
            lines.append(f"  {sid:6d}  {name:20s} {shapes}")
    return lines


def loading_plan(game: Game, screen_files, log) -> Optional[tuple[bytes, int, np.ndarray]]:
    """The loading screen's picture, palette id and palette, if they are the ones this build knows."""
    data = game.original(screens.LOADING)
    ids = screens.palette_ids(screens.LOADING, screen_files)
    raw = game.data_file(ids[0]) if ids and ids[0] != screens.MAIN_PALETTE else None
    try:
        sizes = slp.info(data).sizes if data else []
    except (ValueError, IndexError):
        sizes = []
    if data is None or raw is None:
        return None
    if [s[:2] for s in sizes] != [(loadscreen.W, loadscreen.H)]:
        log(f"loading screen: picture {screens.LOADING} is not the one this build knows; it keeps its look")
        return None
    return data, ids[0], parse_jasc(raw)


def menu_palette(game: Game, old: np.ndarray) -> np.ndarray:
    """The main menu's new palette, written into every archive that has it: from the new menu picture and the other
    pictures shown with it (its dialogue, as the build redraws it, and its checkboxes and arrows)."""
    extra = []
    icons = game.original(MENU_PICTURES[2])
    if icons is not None:
        used = sorted({int(i) for f in slp.decode(icons) for i in np.unique(f.pixels[(f.pixels >= 0) & (f.pixels < 256)])})
        extra.append(np.repeat(old[used, :3] / 255, 40, 0))
    dialogue = game.original(MENU_PICTURES[1])
    if dialogue is not None and screens.fits(MENU_PICTURES[1], dialogue):
        px = slp.decode(dialogue)[0].pixels
        opaque = (px >= 0) & (px < 256)
        rgb = screens.hall(np.asarray(old, np.float64)[np.clip(px, 0, 255), :3] / 255, opaque, MENU_PICTURES[1])
        extra.append(rgb[opaque])
    new = menu.palette(old, np.concatenate(extra) if extra else None)
    for _, drs in game._searched():
        if menu.PALETTE in drs.ids("bina"):
            drs.put(menu.PALETTE, loadscreen.jasc(new), "bina")
    return new


def menu_settings(game: Game, screen_files, palette: np.ndarray, log) -> None:
    """The main menu's screen files (the menu, its dialogue) with Minecraft's buttons: the game fills the Single
    Player menu's buttons in Minecraft's grey with its light and dark edges, and writes the names in white, the one
    the mouse is on in yellow. Written into every archive that has them."""
    conf = menu.settings(palette)
    for sc in screen_files:
        if sc.palette != menu.PALETTE:
            continue
        new = game.data_file(sc.id)
        for key, words in conf.items():
            if key in sc.fields:
                new = screens.with_field(new, key, words)
        for _, drs in game._searched():
            if sc.id in drs.ids("bina"):
                drs.put(sc.id, new, "bina")
        log(f"main menu: Minecraft buttons and white names (screen file {sc.id}), its own palette {menu.PALETTE}")


def draw_loading(game: Game, data: bytes, pal_id: int, palette: np.ndarray, log) -> bytes:
    """The Minecraft loading screen, and its own palette (only this screen uses it) in every archive that has it."""
    picture, pal = loadscreen.encode(data, palette)
    for _, drs in game._searched():
        if pal_id in drs.ids("bina"):
            drs.put(pal_id, loadscreen.jasc(pal), "bina")
    log(f"loading screen: a Minecraft title screen, with its own palette {pal_id}")
    return picture


def find_setup(root: Path) -> Optional[Path]:
    """UserPatch's installer, SetupAoC.exe: in the game folder or one folder below it."""
    folders = [root] + sorted(d for d in root.iterdir() if d.is_dir())
    for folder in folders:
        hit = pick(folder, "SetupAoC.exe")
        if hit is not None:
            return hit
    return None


def make_exe(root: Path, log) -> bool:
    """The mod's own exe, made once: SetupAoC.exe -g:<mod> makes age2_x1\\<mod>.exe, then it gets our icon. The
    installer hands over to a copy of itself running as administrator and returns at once, so the exe appears only
    when Install is clicked in its window: wait for it. The game's own age2_x1.exe must not change; if the
    installer changes it anyway, it is put back as it was."""
    age2 = pick(root, "age2_x1") or root / "age2_x1"
    exe = age2 / f"{MOD}.exe"
    if exe.exists():
        log(f"mod exe: {exe} is there (made by an earlier build)")
        finish_exe(exe, log)
        return True
    setup = find_setup(root)
    if setup is None:
        log(f"mod exe: SetupAoC.exe (the UserPatch installer) is not in {root}, so the mod exe can't be made.")
        return False
    if os.name != "nt":
        log(f"mod exe: on Windows, run  {setup.name} -g:{MOD}  in {setup.parent}")
        return False
    game_exe = pick(age2, "age2_x1.exe")
    before = game_exe.read_bytes() if game_exe is not None else None
    log(f"mod exe: running {setup} -g:{MOD}")
    log("         A UserPatch window opens: click its Install button and wait for it to finish.")
    try:
        done = subprocess.run([str(setup), f"-g:{MOD}"], cwd=setup.parent, timeout=600, check=False,
                              capture_output=True, text=True, errors="replace")
        log(f"mod exe: SetupAoC.exe returned code {done.returncode}")
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"mod exe: could not run SetupAoC.exe ({exc})")
    waited = 0
    while not exe.exists() and waited < 600 and _installer_running():
        if waited % 20 == 0:
            print("  waiting for the UserPatch window: click Install there (or close it to go on without the exe)")
        time.sleep(2)
        waited += 2
    last = -1
    while exe.exists() and exe.stat().st_size != last:  # until it is written completely
        last = exe.stat().st_size
        time.sleep(1)
    if before is not None and game_exe.exists() and game_exe.read_bytes() != before:
        game_exe.write_bytes(before)
        log("mod exe: SetupAoC.exe changed your age2_x1.exe; it is put back as it was")
    if exe.exists():
        log(f"mod exe: made {exe}")
        finish_exe(exe, log)
        return True
    found = sorted(p.name for p in age2.iterdir() if p.suffix.lower() == ".exe") if age2.is_dir() else []
    log(f"mod exe: {exe.name} was not made. Exes in age2_x1: {', '.join(found) or 'none'}")
    return False


def _installer_running() -> bool:
    """True while a SetupAoC.exe is running (Windows' tasklist; True if it can't tell)."""
    try:
        done = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SetupAoC.exe", "/NH"], capture_output=True,
                              text=True, errors="replace", timeout=30)
        return "setupaoc.exe" in done.stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return True


def finish_exe(exe: Path, log) -> None:
    """Our icon and name in the mod's own exe (only that copy; the game's exe is never changed). Both are changed
    in place, so no other byte of the exe moves."""
    from aom import appicon, pe
    try:
        data = exe.read_bytes()
    except OSError as exc:
        log(f"mod exe: could not read {exe.name} ({exc})")
        return
    try:
        new, notes = appicon.into_exe(data)
        log(f"icon: {exe.name} has the {NAME} icon ({', '.join(notes) or 'it has no icon pictures'})")
    except (ValueError, struct.error) as exc:
        new = data
        log(f"icon: could not put it into {exe.name} ({exc})")
    new, places = retitle(new)
    if places:
        log(f"window title: '{EXE_TITLE}' is now '{NAME}' in {exe.name} ({places} places)")
    elif any(t in new for t in _texts(NAME)):
        log(f"window title: {exe.name} already says '{NAME}'")
    else:
        log(f"window title: '{EXE_TITLE}' is not in {exe.name}; the window keeps its title")
    if new != data:
        try:
            new = pe.with_checksum(new)
        except (pe.PeError, struct.error):
            pass
        tmp = exe.with_name(exe.name + ".tmp")
        tmp.write_bytes(new)
        tmp.replace(exe)


def _texts(text: str) -> list[bytes]:
    """A text as the exe can hold it, on its own: between zero bytes, as single-byte or UTF-16 characters."""
    return [b"\0" + text.encode("latin-1") + b"\0", b"\0\0" + text.encode("utf-16-le") + b"\0\0"]


def retitle(data: bytes, old: str = EXE_TITLE, new: str = NAME) -> tuple[bytes, int]:
    """The exe with the text `old` (only where it stands on its own, not inside a longer text) replaced by `new`,
    padded with zero bytes to the same length. Returns it and how many places changed."""
    out, count = bytearray(data), 0
    for find, put in zip(_texts(old), _texts(new)):
        put = put[:-1].ljust(len(find) - 1, b"\0") + put[-1:]
        at = out.find(find)
        while at >= 0:
            out[at:at + len(find)] = put
            count += 1
            at = out.find(find, at + len(find) - 1)
    return bytes(out), count


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


def mod_archive(game: Game, log) -> None:
    """The mod's own gamedata_x1_p1.drs: the game's (UserPatch's), with every changed sprite, farm texture, panel,
    menu picture, icon and sound in it. A UserPatch mod's Data folder is read for its patch archive, rules and
    language file (WololoKingdoms puts all its pictures there too), and the game looks in the patch archive first,
    so these win over graphics.drs, terrain.drs and interfac.drs. Any copies of those that earlier builds put into
    the mod's folder are removed."""
    patch = game.patch if game.patch is not None else Drs()
    for _, drs in game._searched():
        if drs is not patch:
            for kind, entries in drs.added.items():
                for fid, data in entries.items():
                    patch.put(fid, data, kind)
    folder = (pick(game.root, "Games") or game.root / "Games") / MOD / "Data"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "gamedata_x1_p1.drs"
    tmp = path.with_name(path.name + ".tmp")
    patch.write(tmp)
    tmp.replace(path)
    log(f"wrote {path} ({sum(len(e) for e in patch.added.values())} changed files)")
    for name in ("graphics.drs", "interfac.drs", "terrain.drs", "gamedata_x1.drs", "gamedata.drs"):
        old = pick(folder, name)
        if old is not None:
            old.unlink()
            log(f"removed {old} (the game doesn't read it from a mod; everything is in gamedata_x1_p1.drs)")


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


def save_pictures(game: Game, pictures: dict[int, int], out: Path) -> list[str]:
    """Pictures from the game's files as PNG files (<id>_<frame>.png), each in its palette; notes on each."""
    from aom import appicon
    palettes: dict[int, np.ndarray] = {}
    notes = []
    for sid, pal in pictures.items():
        if pal not in palettes:
            raw = game.data_file(pal)
            palettes[pal] = parse_jasc(raw) if raw else game.palette
        palette = palettes[pal]
        data = game.original(sid)
        try:
            frames = slp.decode(data) if data else []
        except (ValueError, IndexError, struct.error) as exc:
            notes.append(f"{sid}: could not read ({exc})")
            continue
        for k, f in enumerate(frames):
            out.mkdir(parents=True, exist_ok=True)
            px = f.pixels
            if ((px >= 0) & (px < 256)).all():  # an opaque picture: a small paletted PNG
                (out / f"{sid}_{k:02d}.png").write_bytes(appicon.png(px.astype(np.uint8), palette))
                continue
            rgba = np.zeros((*px.shape, 4), np.uint8)
            solid = (px >= 0) & (px < 256)
            rgba[solid, :3], rgba[solid, 3] = palette[px[solid]], 255
            team = px >= slp.PLAYER
            rgba[team, :3], rgba[team, 3] = palette[16 + px[team] - slp.PLAYER], 255
            rgba[px == slp.SHADOW] = (0, 0, 0, 128)
            (out / f"{sid}_{k:02d}.png").write_bytes(appicon.png(rgba))
        if frames:
            sizes = sorted({f"{f.pixels.shape[1]}x{f.pixels.shape[0]}" for f in frames})
            notes.append(f"{sid}: {len(frames)} pictures ({', '.join(sizes)})")
    return notes


def save_menu_pictures(game: Game, folder: Path, log) -> None:
    """The game's main menu pictures as PNG files, so a Minecraft menu can be drawn over exactly the same places."""
    out = folder / "menu_originals"
    notes = save_pictures(game, {sid: MENU_PALETTE for sid in MENU_PICTURES}, out)
    log(f"menu pictures: {'; '.join(notes) or 'none found'}" + (f", saved in {out}" if out.exists() else ""))


def save_screen_pictures(game: Game, pictures: dict[int, int], folder: Path, log) -> None:
    """The pictures of the game's other screens (setup, options, loading, dialogues...) as PNG files, so Minecraft
    ones can be drawn to fit their layout."""
    out = folder / "screen_originals"
    notes = save_pictures(game, pictures, out)
    log(f"screen pictures: {len(notes)} saved in {out}" if notes else "screen pictures: none found")


def write_outputs(game: Game, mode: str, rendered: dict[int, bytes], log) -> Path:
    changes: dict[str, tuple[Drs, set[int]]] = {}
    for s in rendered:  # into every archive that has the sprite; new sprites go into graphics.drs
        for name, drs in game.holders(s) or [(game.graphics_path.name, game.graphics)]:
            changes.setdefault(name, (drs, set()))[1].add(s)
    if mode == "upmod":  # all of it goes into the mod's own patch archive, written by mod_archive
        for name, (drs, ids) in changes.items():
            for s in ids:
                drs.put(s, rendered[s])
        games = pick(game.root, "Games") or (game.root / "Games")
        (games / MOD / "Data").mkdir(parents=True, exist_ok=True)
        (games / f"{MOD}.xml").write_bytes(mod_xml())
        log(f"wrote {games / (MOD + '.xml')}")
        for leftover in LEFTOVERS:
            old = game.root / leftover
            if old.exists():
                old.unlink()
                log(f"removed {old} (an earlier build's name for the mod)")
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
        if name.lower().endswith(".drs"):  # its changes go into the mod's own patch archive (mod_archive)
            return
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


GIANT_SLP = 15600  # the first id tried for the giant Pac-Man's SLP
GROUND_SLP = 15000  # the first id tried for the lava's and the gravel's textures (the terrain textures' start there)


def apply_gameplay(game: Game, mode: str, log, pacman: bool = True, javelina: bool = True,
                   dragon: bool = True, lava: bool = True, rails: bool = True) -> None:
    """The .dat changes (Pac-Man and the dragon at the Wonder, the Javelina's own sprites, the lava, the rails and
    trains), their icons, names, sounds, textures and the lava's map."""
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
    giant_icon = None  # the giant red Pac-Man's icon, right after Pac-Man's
    if icon is not None:
        added = []
        for name, drs, new_sheet in new_sheets:
            sheet, msg = gameplay.add_giant_icon(new_sheet, icon + 1, quant) if new_sheet else (None, "")
            added.append((name, drs, sheet or new_sheet))
            if new_sheet:
                log(f"Giant Pac-Man icon in {name}: {msg}")
        if all(sheet is not None and slp.info(sheet).num_frames == icon + 2 for _, _, sheet in added
               if sheet is not None):
            new_sheets, giant_icon = added, icon + 1
    dragon_icon, dragon_sheets = None, []  # the dragon's, after those (in every copy, with Pac-Man's or not)
    if dragon:
        with_pacman = {n: sheet for n, _, sheet in new_sheets if sheet is not None} if icon is not None else {}
        current = [(n, d, with_pacman.get(n, sheet)) for n, d, sheet in gameplay.icon_sheets(archives)]
        if current:
            index = max(slp.info(sheet).num_frames for _, _, sheet in current)
            added = [(n, d, gameplay.add_dragon_icon(sheet, index, quant)) for n, d, sheet in current]
            for n, _, (_, msg) in added:
                log(f"Dragon icon in {n}: {msg}")
            if all(sheet is not None for _, _, (sheet, _) in added):
                dragon_sheets, dragon_icon = [(n, d, sheet) for n, d, (sheet, _) in added], index
    rail_icon, rail_sheets = None, []  # the rail's, in every building icon sheet (one per icon set), at one index
    if rails:
        from aom import rails as rail_map
        current = [(n, d, sid, d.get(sid)) for sid in rail_map.BUILDING_ICONS for n, d in archives
                   if d is not None and sid in d.ids()]
        if current:
            index = max(slp.info(sheet).num_frames for _, _, _, sheet in current)
            added = [(n, d, sid, rail_map.add_icon(sheet, index, quant)) for n, d, sid, sheet in current]
            for n, _, sid, (_, msg) in added:
                log(f"Rail icon in {n} (sheet {sid}): {msg}")
            if all(sheet is not None for _, _, _, (sheet, _) in added):
                rail_sheets, rail_icon = [(n, d, sid, sheet) for n, d, sid, (sheet, _) in added], index
        else:
            log(f"Rail icon: no building icon sheet ({', '.join(map(str, rail_map.BUILDING_ICONS))}); it keeps the "
                "Sea Wall's")
    raw = game.dat_path.read_bytes()
    waves, sound_ids, sound_drs, roars, roar_ids = {}, None, None, {}, None
    if pacman or dragon:  # their sounds go where the game finds new files: the patch archive if there is one
        sound_name, sound_drs = next(((n, d) for n, d in game.archives if n.lower() == "gamedata_x1_p1.drs"),
                                     (game.graphics_path.name, game.graphics))
    if pacman:
        from aom import sounds
        waves = sounds.pacman_sounds()
    if dragon:
        from aom.roars import dragon_sounds
        roars = dragon_sounds(gameplay.dragon_fall(game.graphics_table))
    free = free_resource_ids(game, raw, sum(len(v) for v in [*waves.values(), *roars.values()]))
    if pacman:  # his first, so his ids stay what they were
        sound_ids = {name: [next(free) for _ in variants] for name, variants in waves.items()}
    if dragon:
        roar_ids = {name: [next(free) for _ in variants] for name, variants in roars.items()}
    pictures = free_resource_ids(game, raw, 2, start=GIANT_SLP)
    giant = next(pictures) if pacman else None  # the giant's own SLP
    fire = next(pictures) if dragon else None  # the dragon's fireball's
    lava_dat = lava_tiles = None
    ground_ids = free_resource_ids(game, raw, 2, start=GROUND_SLP)  # the new terrain textures: lava's, gravel's
    if lava:  # in the Water's tile shapes: the old water that becomes the lava was drawn with the Water's texture
        from aom import lava as lava_map
        water = next((t for t in game.terrains or [] if t.id == lava_map.WATER), None)
        original = game.original(water.slp) if water is not None and water.slp > 0 else None
        if original is None:
            log("Lava: not added, the Water's texture is not in your game files")
        else:
            lava_tiles = lava_map.encode(original, quant)
            colour = int(quant.indices(np.array([lava_map.MINIMAP]))[0])
            lava_dat = (next(ground_ids), colour)
    rails_dat = gravel = None
    if rails:  # in the Grass's tile shapes: the old grass that becomes the gravel was drawn with the Grass's texture
        grass = next((t for t in game.terrains or [] if t.id == rail_map.GRASS), None)
        original = game.original(grass.slp) if grass is not None and grass.slp > 0 else None
        if original is None:
            log("Rails: not added, the Grass's texture is not in your game files")
        else:
            gravel = rail_map.encode(original, quant)
            colour = int(quant.indices(np.array([rail_map.MINIMAP]))[0])
            rails_dat = (next(ground_ids), colour, rail_icon)
    patch, notes = gameplay.patch_dat(raw, game.graphics_table, pacman, javelina, icon, sound_ids, giant, giant_icon,
                                      fire, dragon_icon, roar_ids, lava_dat, rails_dat)
    for note in notes:
        log(note)
    if patch is None:
        return
    write_game_file(game, mode, "empires2_x1_p1.dat", patch.data, log)
    if not patch.pacman_strings and not patch.dragon_strings and not patch.lava and not patch.rail_strings:
        return
    touched: dict[str, Drs] = {}
    if patch.dragon_strings and dragon_icon is not None:
        new_sheets = dragon_sheets
    elif not patch.pacman_strings or icon is None:
        new_sheets = []
    for name, drs, new_sheet in new_sheets:  # the icons: Pac-Man's and the giant's, the dragon's
        if new_sheet is not None:
            drs.put(gameplay.UNIT_ICONS, new_sheet)
            touched[name] = drs
    if patch.dragon_strings:  # its fireball's picture, where the game finds new files
        art_name, art_drs = next(((n, d) for n, d in game.archives if n.lower() == "gamedata_x1_p1.drs"),
                                 (game.graphics_path.name, game.graphics))
        art_drs.put(fire, gameplay.fireball_slp(quant, *patch.fire_layout))
        touched[art_name] = art_drs
        log(f"Dragon: its fireball is SLP {fire} in {art_name}")
    if patch.sounds_added:
        from aom import sounds
        for name, variants in waves.items():
            for rid, x in zip(sound_ids[name], variants):
                sound_drs.put(rid, sounds.wav(x), "wav")
        touched[sound_name] = sound_drs
        log(f"Pac-Man's sounds: {sum(len(v) for v in waves.values())} WAV files in {sound_name} "
            f"(ids {min(min(v) for v in sound_ids.values())}-{max(max(v) for v in sound_ids.values())})")
    if patch.dragon_sounds_added:
        from aom import sounds
        for name, variants in roars.items():
            for rid, x in zip(roar_ids[name], variants):
                sound_drs.put(rid, sounds.wav(x), "wav")
        touched[sound_name] = sound_drs
        log(f"Dragon's sounds: {sum(len(v) for v in roars.values())} WAV files in {sound_name} "
            f"(ids {min(min(v) for v in roar_ids.values())}-{max(max(v) for v in roar_ids.values())})")
    if patch.lava:  # its texture with the other terrain textures
        terrain_name, terrain_drs = (("terrain.drs", game.terrain) if game.terrain is not None
                                     else (game.graphics_path.name, game.graphics))
        terrain_drs.put(lava_dat[0], lava_tiles)
        touched[terrain_name] = terrain_drs
        log(f"Lava: its texture is SLP {lava_dat[0]} in {terrain_name} ({slp.info(lava_tiles).num_frames} tiles)")
    if patch.rail_strings:  # the gravel's texture with the other terrain textures, and the rail's icon
        terrain_name, terrain_drs = (("terrain.drs", game.terrain) if game.terrain is not None
                                     else (game.graphics_path.name, game.graphics))
        terrain_drs.put(rails_dat[0], gravel)
        touched[terrain_name] = terrain_drs
        log(f"Rails: the gravel's texture is SLP {rails_dat[0]} in {terrain_name} ({slp.info(gravel).num_frames} "
            "tiles)")
        for name, drs, sid, sheet in rail_sheets:
            drs.put(sid, sheet)
            touched[name] = drs
    if patch.giant_name is not None:  # the giant red Pac-Man's picture, where the game finds new files
        sound_drs.put(giant, gameplay.giant_slp(quant))
        touched[sound_name] = sound_drs
        log(f"Giant Pac-Man: his picture is SLP {giant} in {sound_name}")
        name_giant(game, mode, patch.giant_name, log)
    for name, drs in touched.items():  # each archive written once
        tmp = game.data / (name + ".aom-new")
        drs.write(tmp)
        write_game_file(game, mode, name, tmp.read_bytes(), log)
        tmp.unlink()
    if patch.pacman_strings:
        rename_pacman(game, mode, patch.pacman_strings, log)
    if patch.dragon_strings:  # last: in direct mode it adds to the language files as the lines above left them
        name_dragon(game, mode, patch.dragon_strings, log)
    if patch.rail_strings:
        name_rails(game, mode, patch.rail_strings, log)
    if patch.lava:
        write_map(game, mode, lava_map.MAP_FILE, lava_map.script(), lava_map.MARK, log)


def write_map(game: Game, mode: str, name: str, text: str, mark: str, log) -> None:
    """A random map: into the mod's Script.RM folder, where the game lists the mod's custom maps, or (direct mode)
    the game's Random folder, where `restore` removes it again (any file there of that name without `mark` is the
    player's own, and stays)."""
    if mode == "upmod":
        mod = (pick(game.root, "Games") or game.root / "Games") / MOD
        folder = pick(mod, "Script.RM") or mod / "Script.RM"
    else:
        folder = pick(game.root, "Random") or game.root / "Random"
    path = pick(folder, name) or folder / name
    if mode != "upmod" and path.exists() and mark not in path.read_text("latin-1"):
        log(f"{name}: not written, your Random folder has a map of that name")
        return
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("latin-1"))
    log(f"wrote {path}")


def name_giant(game: Game, mode: str, sid: int, log) -> None:
    """The giant's name: in the mod's own language file, or in the game's where it fits in place."""
    from aom import gameplay, langdll
    if mode == "upmod":
        game.mod_strings[sid] = gameplay.GIANT_NAME
        return
    for name, path in game.language_files().items():
        data = path.read_bytes()
        try:
            if not langdll.read_string(data, sid):
                continue
            write_game_file(game, mode, name, langdll.set_string(data, sid, gameplay.GIANT_NAME), log,
                            folder=game.root)
        except (langdll.DllError, struct.error) as exc:
            log(f"Giant Pac-Man's name: {name} not changed ({exc})")


def name_dragon(game: Game, mode: str, strings: dict[str, int], log) -> None:
    """The dragon's name, button and help texts: in the mod's own language file, or in the game's where they fit."""
    from aom import gameplay, langdll
    texts = {sid: gameplay.DRAGON_TEXTS[key] for key, sid in strings.items()}
    if mode == "upmod":
        game.mod_strings.update(texts)
        return
    short = gameplay.DRAGON_TEXTS["creation"]  # a help text that fits where the game's placeholder was
    for name in game.language_files():
        path = pick(game.root, name)  # as rename_pacman and name_giant left it
        data = new = path.read_bytes()
        for sid, text in texts.items():
            for attempt in (text, short) if sid == strings.get("help") else (text,):
                try:
                    if langdll.read_string(new, sid):
                        new = langdll.set_string(new, sid, attempt)
                    break
                except (langdll.DllError, struct.error) as exc:
                    log(f"Dragon's texts: string {sid} in {name} not set to {attempt[:30]!r} ({exc})")
        if new != data:
            write_game_file(game, mode, name, new, log, folder=game.root)


def name_rails(game: Game, mode: str, strings: dict[str, dict[str, int]], log) -> None:
    """The rail's and the train's names, buttons and help texts: in the mod's own language file, or in the game's
    where they fit (a help text too long for its place gets a short one; the Sea Wall has none to replace)."""
    from aom import langdll, rails as rail_map
    texts = {sid: (rail_map.TEXTS[unit][key], rail_map.SHORT_HELP[unit] if key == "help" else None)
             for unit, ids in strings.items() for key, sid in ids.items()}
    if mode == "upmod":
        game.mod_strings.update({sid: text for sid, (text, _) in texts.items()})
        return
    for name in game.language_files():
        path = pick(game.root, name)  # as the texts before them left it
        data = new = path.read_bytes()
        for sid, (text, short) in texts.items():
            for attempt in (text, short) if short else (text,):
                try:
                    if langdll.read_string(new, sid):
                        new = langdll.set_string(new, sid, attempt)
                    break
                except (langdll.DllError, struct.error) as exc:
                    log(f"Rails' texts: string {sid} in {name} not set to {attempt[:30]!r} ({exc})")
        if new != data:
            write_game_file(game, mode, name, new, log, folder=game.root)


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
    from aom import lava as lava_map
    data = pick(root, "Data")
    restored = 0
    for p in [*(data.iterdir() if data else []), *root.iterdir()]:  # Data files, and the language files
        if p.is_file() and p.name.endswith(BACKUP):
            live = p.with_name(p.name[:-len(BACKUP)])
            shutil.copy2(p, live)
            p.unlink()
            restored += 1
            print(f"restored {live}")
    maps = pick(root, "Random")
    ours = pick(maps, lava_map.MAP_FILE) if maps else None
    if ours is not None and lava_map.MARK in ours.read_text("latin-1"):  # the map the build added
        ours.unlink()
        restored += 1
        print(f"removed {ours}")
    print("nothing to restore" if not restored else "original files are back")
    return 0


def write_report(game: Game, planned, skipped, blanks, header: list[str], path: Path, statics=(),
                 farms=(), panels=(), failed=None, screen_files=(), screen_pictures=None, teams=()) -> None:
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
    lines += ["", "INTERFACE PANELS AND SCREENS (slp, size, result)"]
    for s, (w, h) in panels:
        result = "planned" if failed is None else ("Minecraft style" if s not in failed else failed[s])
        lines.append(f"  {s:6d}  {w}x{h:<5d} {result}")
    lines += ["", "SCREENS (screen file: its pictures and palette, then its settings)"]

    def sizes(sid: int) -> str:
        data = game.original(sid)
        try:
            found = slp.info(data).sizes if data else []
        except (ValueError, IndexError):
            return "unreadable"
        if not found:
            return "not in your files"
        return f"{found[0][0]}x{found[0][1]}" + (f", {len(found)} pictures" if len(found) > 1 else "")

    named = set()
    for sc in screen_files:
        named |= set(sc.backgrounds)
        pics = ", ".join(f"{b} ({sizes(b)})" for b in sc.backgrounds) or "no pictures of its own"
        lines.append(f"  {sc.id:6d}  {pics}; palette {sc.palette}")
        lines.append("          " + " | ".join(" ".join([k, *v]) for k, v in sc.fields.items()))
    lines += ["", f"TEAM MARKS (the achievements' team column, {screens.TEAMS}, and its copies: in your game's "
                  "archives, pictures)", *teams]
    lines += ["", "OTHER LARGE PICTURES (slp, size)"]
    lines += [f"  {s:6d}  {sizes(s)}" for s in sorted(screen_pictures or {}) if s not in named]
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
