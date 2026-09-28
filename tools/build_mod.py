"""Build the Age of Minecraft mod for your own AoE2: The Conquerors + UserPatch 1.5.

    python tools/build_mod.py --game "C:\\Program Files (x86)\\Microsoft Games\\Age of Empires II"

It reads your game's palette, sprite frame counts and graphics table, renders
every Minecraft sprite to match exactly, and writes a UserPatch data mod:

    Games\\AgeOfMinecraft.xml
    Games\\AgeOfMinecraft\\Data\\graphics.drs    your graphics.drs with our sprites swapped in
    Games\\AgeOfMinecraft\\aom_report.txt        what was replaced, skipped and why

Your own Data folder is left alone. With --mode direct the sprites go into
Data\\graphics.drs itself instead (a backup is kept; --restore puts it back).
Options: --only militia,archer (just some units)  --jobs 4  --dry-run
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aom import slp  # noqa: E402
from aom.datfile import Graphic, read_graphics  # noqa: E402
from aom.drs import Drs  # noqa: E402
from aom.export import blank, render_frames  # noqa: E402
from aom.palette import Quantiser, parse_jasc  # noqa: E402
from aom.roster import ROSTER  # noqa: E402
from aom.slpmap import BLANK, TARGETS  # noqa: E402

MOD = "AgeOfMinecraft"
BACKUP = ".aom-backup"

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
             "  <name>Age of Minecraft</name>",
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
        interfac = self._drs("interfac.drs")
        if interfac is None or interfac.get(50500, "bina") is None:
            raise SystemExit("Could not find the game palette (interfac.drs, 50500).")
        self.palette = parse_jasc(interfac.get(50500, "bina"))
        self.graphics_table: dict[int, Graphic] = {}
        dat = pick(self.data, "empires2_x1_p1.dat")
        try:
            self.graphics_table = read_graphics(dat) if dat else {}
            log(f"graphics table: {len(self.graphics_table)} graphics read from {dat.name}")
        except Exception as exc:  # the build still works from the SLP headers alone
            log(f"graphics table: could not read ({exc}); using the sprite files only")
        self.by_slp: dict[int, list[Graphic]] = {}
        for g in self.graphics_table.values():
            self.by_slp.setdefault(g.slp, []).append(g)

    def _drs(self, name: str) -> Optional[Drs]:
        p = pick(self.data, name)
        if p is None:
            return None
        backup = p.with_name(p.name + BACKUP)
        return Drs(backup if backup.exists() else p)

    def original(self, slp_id: int) -> Optional[bytes]:
        for drs in (self.patch, self.graphics):
            if drs is not None and slp_id in drs.ids():
                return drs.get(slp_id)
        return None

    def layout(self, slp_id: int, num_frames: int) -> tuple[int, int, bool, str]:
        """(frames per angle, angle count, mirrored, source) matching the original sprite."""
        for g in self.by_slp.get(slp_id, []):
            if g.stored_angles * max(1, g.frame_count) == num_frames:
                return max(1, g.frame_count), max(1, g.angle_count), bool(g.mirroring), "dat"
        if num_frames % 5 == 0:
            return num_frames // 5, 8, True, "guessed 8 mirrored angles"
        return num_frames, 1, False, "guessed 1 angle"

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


# --------------------------------------------------------------------------- rendering (worker processes)

_STATE: dict = {}


def _init(palette) -> None:
    _STATE["quant"] = Quantiser(palette)
    _STATE["units"] = {}


def _render(job) -> tuple[int, bytes, int]:
    slp_id, unit_key, action, frames, angles, mirrored = job
    units = _STATE["units"]
    if unit_key not in units:
        units[unit_key] = ROSTER[unit_key]()
    out = render_frames(units[unit_key], action, frames, angles, mirrored, _STATE["quant"])
    return slp_id, slp.encode(out), len(out)


# --------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Age of Minecraft mod from your own AoE2 install.")
    ap.add_argument("--game", required=True, type=Path, help="your Age of Empires II folder")
    ap.add_argument("--mode", choices=("upmod", "direct"), default="upmod",
                    help="upmod: separate UserPatch mod (default); direct: patch Data\\graphics.drs (with backup)")
    ap.add_argument("--only", help="comma-separated unit keys (see docs/UNITS.md), e.g. militia,archer,villager")
    ap.add_argument("--jobs", type=int, default=max(1, (mp.cpu_count() or 2) - 1))
    ap.add_argument("--dry-run", action="store_true", help="plan and report only, write nothing")
    ap.add_argument("--restore", action="store_true", help="undo --mode direct from the backups")
    ap.add_argument("--no-exe", action="store_true", help="do not run UserPatch's SetupAoC.exe to create the mod exe")
    args = ap.parse_args(argv)

    report: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        report.append(msg)

    game_root = args.game.expanduser()
    if args.restore:
        return restore(game_root)
    game = Game(game_root, log)
    log(f"palette: {len(game.palette)} colours")

    only = set(args.only.split(",")) if args.only else None
    if only and not only <= set(ROSTER):
        raise SystemExit(f"unknown units: {', '.join(sorted(only - set(ROSTER)))}")
    targets = [t for t in TARGETS if only is None or t.unit in only]

    jobs, skipped, planned = [], [], []
    for t in targets:
        data = game.original(t.slp)
        if data is None:
            skipped.append((t, "not in your game files"))
            continue
        try:
            info = slp.info(data)
        except ValueError as exc:
            skipped.append((t, str(exc)))
            continue
        frames, angles, mirrored, source = game.layout(t.slp, info.num_frames)
        jobs.append((t.slp, t.unit, t.action, frames, angles, mirrored))
        planned.append((t, info.num_frames, frames, angles, mirrored, source))

    target_slps = {j[0] for j in jobs}
    blanks = {} if only else {s: why for s, why in BLANK}
    if not only:
        blanks.update(game.delta_blanks(target_slps))
    blanks = {s: why for s, why in blanks.items() if s not in target_slps and game.original(s) is not None}

    log(f"plan: {len(jobs)} sprites to render, {len(blanks)} layers to blank, {len(skipped)} skipped")
    if args.dry_run:
        write_report(game, planned, skipped, blanks, report, Path.cwd() / "aom_report.txt")
        return 0

    started = time.time()
    rendered: dict[int, bytes] = {}
    jobs.sort(key=lambda j: -j[3] * (j[4] // 2 + 1))  # big animations first
    with mp.Pool(args.jobs, initializer=_init, initargs=(game.palette,)) as pool:
        for n, (slp_id, data, count) in enumerate(pool.imap_unordered(_render, jobs), 1):
            rendered[slp_id] = data
            if n % 20 == 0 or n == len(jobs):
                print(f"  rendered {n}/{len(jobs)} sprites ({time.time() - started:.0f}s)")
    for s in blanks:
        rendered[s] = blank(slp.info(game.original(s)).num_frames)

    for slp_id, data in rendered.items():  # never ship a sprite whose frame count differs from the original
        want = slp.info(game.original(slp_id)).num_frames
        got = slp.info(data).num_frames
        if want != got:
            raise SystemExit(f"internal error: SLP {slp_id} has {got} frames, the game expects {want}")

    try:
        out_dir = write_outputs(game, args.mode, rendered, log)
    except PermissionError as exc:
        raise SystemExit(f"Windows would not let us write {exc.filename}.\n"
                         "Your game is probably under Program Files: run the command prompt as administrator "
                         "(right-click > Run as administrator) and try again.")
    if args.mode == "upmod" and not args.no_exe:
        make_exe(game.root, log)
    write_report(game, planned, skipped, blanks, report, out_dir / "aom_report.txt")
    log(f"done in {time.time() - started:.0f}s")
    return 0


def make_exe(root: Path, log) -> None:
    """UserPatch starts a data mod through its own exe: SetupAoC.exe -g:<mod> creates age2_x1\\<mod>.exe."""
    setup = pick(root, "SetupAoC.exe")
    exe = root / "age2_x1" / f"{MOD}.exe"
    manual = f'In your game folder run:  SetupAoC.exe -g:{MOD}   then start  age2_x1\\{MOD}.exe'
    if setup is None or os.name != "nt":
        log("To play: " + manual)
        return
    try:
        subprocess.run([str(setup), f"-g:{MOD}"], cwd=root, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"Could not run SetupAoC.exe ({exc}). " + manual)
        return
    log(f"To play: start {exe}" if exe.exists() else "SetupAoC.exe ran but no mod exe appeared. " + manual)


def write_outputs(game: Game, mode: str, rendered: dict[int, bytes], log) -> Path:
    in_patch = {s for s in rendered if game.patch is not None and s in game.patch.ids()}
    if mode == "upmod":
        games = pick(game.root, "Games") or (game.root / "Games")
        mod_data = games / MOD / "Data"
        mod_data.mkdir(parents=True, exist_ok=True)
        targets = [(game.graphics, mod_data / "graphics.drs", set(rendered) - in_patch)]
        if in_patch:
            targets.append((game.patch, mod_data / "gamedata_x1_p1.drs", in_patch))
        for base, path, ids in targets:
            for s in ids:
                base.put(s, rendered[s])
            base.write(path)
            log(f"wrote {path}")
        (games / f"{MOD}.xml").write_bytes(mod_xml())
        log(f"wrote {games / (MOD + '.xml')}")
        return games / MOD
    # direct: patch the game's own files, keeping the originals once
    for base, ids in ((game.graphics, set(rendered) - in_patch), (game.patch, in_patch)):
        if not ids:
            continue
        live = Path(base.path)
        if live.name.endswith(BACKUP):
            live = live.with_name(live.name[:-len(BACKUP)])
        backup = live.with_name(live.name + BACKUP)
        if not backup.exists():
            shutil.copy2(live, backup)
            log(f"backed up {live.name} -> {backup.name}")
        for s in ids:
            base.put(s, rendered[s])
        tmp = live.with_name(live.name + ".tmp")
        base.write(tmp)
        tmp.replace(live)
        log(f"patched {live}")
    return game.data


def restore(root: Path) -> int:
    data = pick(root, "Data")
    restored = 0
    for p in data.iterdir() if data else []:
        if p.name.endswith(BACKUP):
            live = p.with_name(p.name[:-len(BACKUP)])
            shutil.copy2(p, live)
            p.unlink()
            restored += 1
            print(f"restored {live}")
    print("nothing to restore" if not restored else "original files are back")
    return 0


def write_report(game: Game, planned, skipped, blanks, header: list[str], path: Path) -> None:
    lines = ["Age of Minecraft build report", "=" * 30, *header, "", "REPLACED (slp, unit, action, frames x angles)"]
    for t, n, frames, angles, mirrored, source in sorted(planned, key=lambda p: p[0].slp):
        m = " mirrored" if mirrored else ""
        lines.append(f"  {t.slp:6d}  {t.unit:24s} {t.action:7s} {n:4d} frames = {frames} x {angles} angles{m}"
                     f"  [{source}] {t.note}")
    lines += ["", "BLANKED LAYERS"] + [f"  {s:6d}  {why}" for s, why in sorted(blanks.items())]
    lines += ["", "SKIPPED"] + [f"  {t.slp:6d}  {t.unit:24s} {t.action:7s} {why}" for t, why in skipped]
    covered = {p[0].unit for p in planned}
    lines += ["", "UNITS WITHOUT SPRITES YET: " + ", ".join(sorted(set(ROSTER) - covered))]
    if game.graphics_table:
        lines += ["", "GRAPHICS TABLE (id, name, slp, frames, angles, mirror, deltas)"]
        for gid, g in sorted(game.graphics_table.items()):
            deltas = ",".join(str(d.graphic_id) for d in g.deltas)
            lines.append(f"  {gid:5d} {g.name:22s} {g.slp:6d} {g.frame_count:4d} {g.angle_count:3d} {g.mirroring:2d}"
                         f"  {deltas}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"report: {path}")


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
