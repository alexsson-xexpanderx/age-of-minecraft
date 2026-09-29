"""Tests for the in-game export: SLP and DRS round trips, the .dat graphics
reader, and a full build against a fake game folder.

    python tools/tests/test_export.py        (or: python -m pytest tools/tests)
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_mod  # noqa: E402
from aom import langdll, slp  # noqa: E402
from aom.datfile import read_graphics, read_terrains  # noqa: E402
from aom.drs import Drs  # noqa: E402
from aom.export import render_frames  # noqa: E402
from aom.palette import Quantiser, parse_jasc  # noqa: E402
from aom.roster import ROSTER  # noqa: E402


# --------------------------------------------------------------------------- fixtures

def fake_palette() -> bytes:
    rng = np.random.default_rng(1)
    cols = []
    for i in range(256):
        k, j = divmod(i, 16)
        if 1 <= k <= 8 and j < 8:  # team colour ramps
            base = np.array([[40, 60, 255], [255, 30, 30], [30, 200, 30], [255, 255, 0], [0, 230, 230],
                             [230, 0, 230], [180, 180, 180], [255, 140, 0]][k - 1])
            cols.append(tuple(int(v) for v in base * (0.3 + 0.1 * j)))
        else:
            cols.append(tuple(int(v) for v in rng.integers(0, 256, 3)))
    cols[0], cols[255] = (0, 0, 0), (255, 255, 255)
    body = "\r\n".join(f"{r} {g} {b}" for r, g, b in cols)
    return f"JASC-PAL\r\n0100\r\n256\r\n{body}\r\n".encode()


def _unit_bytes(uid: int, utype: int, name: str, standing: int = -1, dead: int = -1) -> bytes:
    """One unit record in the Conquerors layout (mirrors aom.datunits)."""
    nb = name.encode()
    b = bytearray(struct.pack("<bHhHHh", utype, len(nb), uid, 5000 + uid, 6000 + uid, 10 if uid == 860 else 0))
    b += struct.pack("<hhhhbhfb", standing, -1, -1, -1, 0, 30, 4.0, 0)
    b += struct.pack("<fffhhhbbhbhbb", 0.2, 0.2, 2.0, -1, -1, dead, 0, 0, 159 if uid == 860 else 1, 0, -1, 0, 0)
    b += struct.pack("<hhhhffbbhbhfbbbbbfb", -1, -1, -1, -1, 0.5, 0.5, 0, 0, 1 if uid == 860 else 7,  # no beaches
                     0, 0, 0.0, 0, 0, 0, 0, 0, 0.0, 0)
    b += struct.pack("<iiibbbbbbbBbhbBfff", 105000 + uid, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)
    b += bytes(21) + struct.pack("<B", 0) + struct.pack("<hhbb", -1, -1, 0, 0) + nb + struct.pack("<hh", uid, uid)
    if utype >= 20:
        b += struct.pack("<f", 1.0)
    if utype >= 30:
        b += struct.pack("<hhfbhbfbfffff", -1, -1, 0.0, 0, -1, 0, 0.0, 0, 0, 0, 0, 0, 0)
    if utype >= 40:
        b += struct.pack("<hffhhbhhb", -1, 0, 0, -1, -1, 0, -1, -1, 0)
    if utype >= 50:
        b += struct.pack("<hHHhfffhhbhfffbffhhhff", 0, 0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0)
    if utype >= 70:
        b += struct.pack("<hhhhhhhhhhhbffbbifbfffiibh", 0, 25, 1, 3, 25, 1, 4, 1, 0, 20, -1, 0, 0, 0, 2, 0, -1, 0, 0,
                         0, 0, 0, -1, -1, 0, 0)
    if utype == 80:
        b += struct.pack("<hhbhbhhhhb", -1, -1, 0, 0, 0, -1, -1, -1, -1, 0) + bytes(40)
        b += struct.pack("<hhhhbffh", -1, -1, -1, -1, 0, 0, 0, -1) + bytes(6)
    return bytes(b)


def fake_civs(civs: int = 2, slots: int = 900, monkey_graphic: int = 0, boar_graphic: int = 0) -> bytes:
    """Civilisations with unit tables: filler units, the Wonder (276), Furious the Monkey Boy (860), and the
    Javelina (822) borrowing the Wild Boar's sprites, with its carcass (823) and the boar's (356).

    Before them, the units' task lists: the Militia (74) can attack and board a Transport Ship, the Monkey Boy
    (860) can only attack."""
    from aom.datunits import TASK
    attack = (1, 0, 0, 7, -1, -1, -1, -1, -1, -1, -1, 0.0, 0.0, 0.0, 0, 0.0, 0, 0, 0, 0, 5, 0, 0, -1, -1, -1, -1, -1, -1)
    board = (1, 1, 0, 3, 20, -1, -1, -1, -1, -1, -1, 0.0, 0.0, 1.0, 0, 0.0, 0, 0, 0, 0, 4, 0, 0, -1, -1, -1, -1, -1, -1)
    out = bytearray(struct.pack("<I", slots))
    for u in range(slots):
        tasks = [attack, board] if u == 74 else [attack] if u == 860 else []
        out += struct.pack("<bH", 1, len(tasks)) + b"".join(TASK.pack(*t) for t in tasks) if u % 2 == 0 or u in (
            276, 860, 823) else b"\0"
    out += struct.pack("<H", civs)
    rng = np.random.default_rng(5)
    for c in range(civs):
        out += struct.pack("<b20sHhh", 1, [b"Gaia", b"British", b"French"][c % 3], 4, 1, 1)
        out += struct.pack("<4f", 1, 2, 3, 4) + struct.pack("<bH", 0, slots)
        present = [u for u in range(slots) if u % 2 == 0 or u in (276, 860, 823)]
        # like the original game's file, a pointer is a memory address (0 = no unit)
        out += struct.pack(f"<{slots}i", *[int(rng.integers(0x400000, 0x7fffffff)) if u in present else 0
                                           for u in range(slots)])
        for u in present:
            if u == 276:
                out += _unit_bytes(u, 80, "WNDR")
            elif u == 860:
                out += _unit_bytes(u, 70, "mkyby", monkey_graphic)
            elif u == 822:
                out += _unit_bytes(u, 70, "BOARJ", boar_graphic, dead=356)
            elif u in (356, 823):
                out += _unit_bytes(u, 30, "BOARX_D" if u == 356 else "BOARJ_D", boar_graphic)
            else:
                out += _unit_bytes(u, 10, f"U{u}")
    return bytes(out)


FAKE_TERRAINS = {0: ("Grass", 15000), 7: ("Farm", 15004), 8: ("Farm (dead)", 15005), 29: ("Farm 1", 15021),
                 30: ("Farm 2", 15040), 31: ("Farm 3", 15023)}  # Farm 2 on another id: it must come from the .dat


def fake_terrains(terrains: dict[int, tuple[str, int]]) -> bytes:
    """The terrain block after the graphics: map sizes, 19 tile sizes, padding, 42 terrains (mirrors aom.datfile)."""
    b = bytearray(struct.pack("<6i", 0, 0, 0, 0, 0, 0))
    b += struct.pack("<57h", *([97, 49, 0] * 19)) + bytes(2)
    for i in range(42):
        name, slp_id = terrains.get(i, ("", -1))
        rec = bytearray(struct.pack("<bb13s13si", 1 if name else 0, 0, name.encode(), f"t{i}".encode(), slp_id))
        rec += bytes(192 - len(rec)) + struct.pack("<hhh", -1, 3 if 29 <= i <= 31 else 6, 3 if 29 <= i <= 31 else 6)
        b += rec + bytes(436 - len(rec))
    return bytes(b)


def fake_dat(graphics: list[dict], civs: bytes = b"", ground: dict = None) -> bytes:
    """A minimal empires2_x1_p1.dat: header sections plus the given graphics (and terrains and unit tables)."""
    b = bytearray(b"VER 5.7\0")
    restrictions, terrains = 2, 3
    b += struct.pack("<HH", restrictions, terrains)
    b += struct.pack(f"<{2 * restrictions}i", *([1] * 2 * restrictions))
    for _ in range(restrictions):
        b += struct.pack(f"<{terrains}f", *([1.0] * terrains)) + bytes(16 * terrains)
    b += struct.pack("<H", 2) + bytes(36 * 2)
    b += struct.pack("<H", 1) + struct.pack("<hhHi", 0, 0, 2, 300000)  # one sound, with two files
    b += struct.pack("<13sihhh", b"a.wav", 5001, 50, -1, -1) + struct.pack("<13sihhh", b"b.wav", 15501, 50, -1, -1)
    b += struct.pack("<H", len(graphics)) + struct.pack(f"<{len(graphics)}I", *([1] * len(graphics)))
    for gid, g in enumerate(graphics):
        b += struct.pack("<21s13si", g["name"].encode(), b"file", g["slp"])
        b += struct.pack("<bbbbbB", 0, 0, 20, -1, 0, 0) + bytes(8)
        b += struct.pack("<Hh", len(g.get("deltas", [])), -1)
        b += struct.pack("<BHH", 0, g["frames"], g["angles"])
        b += struct.pack("<fff", 1.0, 0.1, 0.0)
        b += struct.pack("<bhbb", 0, gid, g.get("mirror", 1), 0)
        for d in g.get("deltas", []):
            b += struct.pack("<hhihhhh", d, 0, 0, 0, 0, -1, 0)
    if ground is not None:
        b += fake_terrains(ground)
    b += civs
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(bytes(b)) + c.flush()


def diamond(fill: int = 60) -> slp.SlpFrame:
    """A terrain tile: a 97x49 diamond, as in terrain.drs."""
    px = np.full((49, 97), slp.TRANSPARENT, np.int16)
    for r in range(49):
        k = 24 - abs(r - 24)
        px[r, 48 - 2 * k:48 + 2 * k + 1] = fill
    return slp.SlpFrame(px, (0, 0))


def fake_panel(w: int, h: int, icons: list[tuple[int, int]]) -> bytes:
    """An in-game panel picture: a carved top bar with resource icons, and a bottom panel with parchment and a
    dark minimap area; the game view between them is transparent."""
    pal = parse_jasc(fake_palette())
    lum = pal @ [0.299, 0.587, 0.114] / 255
    allowed = [i for i in range(256) if not (16 <= i < 144 and i % 16 < 8)]  # not the team colours
    light, dark = max(allowed, key=lambda i: lum[i]), min(allowed, key=lambda i: lum[i])
    frame = min(allowed, key=lambda i: abs(lum[i] - 0.35))
    px = np.full((h, w), slp.TRANSPARENT, np.int16)
    px[:32] = frame
    rng = np.random.default_rng(4)
    for k, (x, y) in enumerate(icons):
        px[y:y + 17, x:x + 26] = rng.choice(allowed[100:140], (17, 26))
    top = h - 218
    px[top:] = frame
    px[top + 24:h - 14, w // 4:w * 2 // 3] = light
    px[top + 24:h - 14, w * 2 // 3 + 30:w - 20] = dark
    return slp.encode([slp.SlpFrame(px, (0, 0))])


def fake_game(root: Path) -> Path:
    data = root / "Data"
    data.mkdir(parents=True)
    interfac = Drs()
    interfac.put(50500, fake_palette(), "bina")
    boxes = [(8, 10), (85, 10), (162, 10), (239, 10), (316, 10)]
    interfac.put(51141, fake_panel(1280, 1024, boxes))  # a civilisation's panels at 1280x1024
    big = slp.decode(interfac.get(51141))[0].pixels
    mid = slp.decode(fake_panel(1024, 768, []))[0]
    for x, y in boxes:  # at 1024x768 the same icons sit elsewhere
        mid.pixels[y - 4:y + 13, x + 3:x + 29] = big[y:y + 17, x:x + 26]
    interfac.put(51121, slp.encode([mid]))
    interfac.put(51101, fake_panel(800, 600, []))  # its icons can't be found
    icon = slp.SlpFrame(np.full((36, 36), 77, np.int16), (0, 0))
    interfac.put(50730, slp.encode([icon] * 170))  # the unit icon sheet
    interfac.write(data / "interfac.drs")
    # the language files: Furious the Monkey Boy's name (5860), button (6860) and help (26860) texts
    monkey = {5860: "Furious the Monkey Boy", 6860: "Create <b>Furious the Monkey Boy<b> (<cost>)",
              26860: "Create <b>Furious the Monkey Boy<b> (<cost>)\nA very fast cheat unit.", 5861: "Next unit"}
    (root / "language_x1_p1.dll").write_bytes(langdll.build_dll({5860: monkey[5860], 9999: "UserPatch"}))
    (root / "language_x1.dll").write_bytes(langdll.build_dll(monkey))
    (root / "language.dll").write_bytes(langdll.build_dll({5079: "Militia"}))
    graphics = Drs()
    table = []
    # militia (5 sprites), archer (5), a battering ram with a separate swinging head and wheels
    for s, frames, angles in [(987, 10, 8), (990, 10, 8), (993, 6, 8), (994, 5, 8), (997, 10, 8),
                              (2, 10, 8), (5, 10, 8), (8, 6, 8), (9, 5, 8), (12, 10, 8)]:
        extra = 2 if s == 8 else 0  # like the real archer: two frames more than the .dat uses
        graphics.put(s, build_mod.blank(frames * 5 + extra))
        table.append({"name": f"UNIT_{s}", "slp": s, "frames": frames, "angles": angles})
    # battering ram as in the real .dat: each action is [layer 0, own sprite, layer 1]
    for s in (171, 172, 173, 176, 180, 181, 182, 183):
        graphics.put(s, build_mod.blank(5 * 5))
    table += [{"name": "BTRAM_A0", "slp": 171, "frames": 5, "angles": 8},
              {"name": "BTRAM_A1", "slp": 172, "frames": 5, "angles": 8},
              {"name": "BTRAM_W0", "slp": 181, "frames": 5, "angles": 8},
              {"name": "BTRAM_W1", "slp": 182, "frames": 5, "angles": 8}]
    a0 = len(table) - 4
    table += [{"name": "BTRAM_AN", "slp": 173, "frames": 5, "angles": 8, "deltas": [a0, -1, a0 + 1]},
              {"name": "BTRAM_WN", "slp": 183, "frames": 5, "angles": 8, "deltas": [a0 + 2, -1, a0 + 3]},
              {"name": "BTRAM_DN", "slp": 176, "frames": 5, "angles": 8},
              {"name": "BTRAM_SN", "slp": 180, "frames": 5, "angles": 8}]
    for s, name in ((9000, "HALBD_AN"), (9003, "HALBD_DN"), (9100, "PETARD_DN"), (9101, "BLAST_NN")):
        graphics.put(s, build_mod.blank(10 * 5))
        table.append({"name": name, "slp": s if s != 9101 else 9100, "frames": 10, "angles": 8})
    # buildings and scenery, found by their names: a barracks with its shadow and flag layers, a stone
    # wall with its five pieces, an oak forest, a gold mine, and a flag sprite shared with a ship
    for s, frames in ((130, 1), (122, 1), (126, 1), (2098, 5), (2090, 5), (4652, 14), (2296, 14), (2561, 7),
                      (4479, 7), (2219, 1)):
        pieces = []
        for k in range(frames):
            px = np.full((40 + 6 * k, 30 + 8 * (k % 5)), 60, np.int16)
            pieces.append(slp.SlpFrame(px, (px.shape[1] // 2, px.shape[0] - 4)))
        graphics.put(s, slp.encode(pieces))
    base = len(table)
    table += [{"name": "BRKS2N0E", "slp": 122, "frames": 1, "angles": 1, "mirror": 0},
              {"name": "BRKS2N1E", "slp": 126, "frames": 1, "angles": 1, "mirror": 0},
              {"name": "BRKS2NNE", "slp": 130, "frames": 1, "angles": 1, "mirror": 0, "deltas": [base, -1, base + 1]},
              {"name": "WALL2N0E", "slp": 2090, "frames": 1, "angles": 5, "mirror": 0},
              {"name": "WALL2NNE", "slp": 2098, "frames": 1, "angles": 5, "mirror": 0, "deltas": [-1, base + 3]},
              {"name": "FOAK_N0", "slp": 2296, "frames": 1, "angles": 14, "mirror": 0},
              {"name": "FOAK_NN", "slp": 4652, "frames": 1, "angles": 14, "mirror": 0, "deltas": [base + 5, -1]},
              {"name": "GOLDM_N0", "slp": 4479, "frames": 1, "angles": 7, "mirror": 0},
              {"name": "GOLDM_NN", "slp": 2561, "frames": 1, "angles": 7, "mirror": 0, "deltas": [base + 7, -1]},
              {"name": "BLAC2N1E", "slp": 2219, "frames": 23, "angles": 1, "mirror": 0},
              {"name": "ABGAL_ANE", "slp": 2219, "frames": 1, "angles": 16, "mirror": 0}]
    monkey = len(table)
    table.append({"name": "mkyby_FN", "slp": 5299, "frames": 15, "angles": 8})
    graphics.put(5299, build_mod.blank(15 * 5))
    graphics.put(40000, b"not a sprite we touch")
    graphics.write(data / "graphics.drs")
    extra = Drs()  # some sprites only exist in gamedata_x1.drs
    extra.put(5157, build_mod.blank(17 * 5))
    extra.write(data / "gamedata_x1.drs")
    terrain = Drs()  # grass, and the farms: 6x6 tiles for the farm and the dead farm, 3x3 for the stages
    for slp_id, tiles in ((15000, 100), (15004, 36), (15005, 36), (15021, 9), (15040, 9), (15023, 9)):
        terrain.put(slp_id, slp.encode([diamond(60 + k % 7) for k in range(tiles)]))
    terrain.write(data / "terrain.drs")
    patch = Drs()  # UserPatch's own archive, already holding a sound
    patch.put(15500, b"RIFF a sound", "wav")
    patch.write(data / "gamedata_x1_p1.drs")
    boar = len(table)
    table.append({"name": "BOARX_FN", "slp": 2557, "frames": 10, "angles": 8})
    for name, slp_id, frames in (("BOARJ_AN", 5157, 17), ("BOARJ_DN", 5158, 11), ("BOARJ_FN", 5159, 10),
                                 ("BOARJ_RN", 5160, 10), ("BOARJ_SN", 5161, 5), ("BOARJ_WN", 5162, 10)):
        table.append({"name": name, "slp": slp_id, "frames": frames, "angles": 8})  # only 5157 has a file
    (data / "empires2_x1_p1.dat").write_bytes(fake_dat(table, fake_civs(monkey_graphic=monkey, boar_graphic=boar),
                                                       FAKE_TERRAINS))
    return root


# --------------------------------------------------------------------------- tests

def test_slp_round_trip():
    rng = np.random.default_rng(3)
    frames = []
    for h, w in ((1, 1), (7, 5), (40, 90), (3, 300)):
        codes = rng.choice([slp.TRANSPARENT, slp.SHADOW, slp.OBSTRUCTION, 5, 77, 200, slp.PLAYER, slp.PLAYER + 7],
                           size=(h, w)).astype(np.int16)
        codes[0, :] = slp.TRANSPARENT  # an empty row
        frames.append(slp.SlpFrame(codes, (w // 2, h - 1)))
    data = slp.encode(frames)
    assert slp.info(data).num_frames == len(frames)
    for a, b in zip(frames, slp.decode(data)):
        assert np.array_equal(a.pixels, b.pixels) and a.hotspot == b.hotspot


def test_drs_round_trip(tmp: Path):
    d = Drs()
    d.put(50500, b"palette", "bina")
    for i in (30, 10, 20):
        d.put(i, bytes([i]) * i)
    d.write(tmp / "a.drs")
    e = Drs(tmp / "a.drs")
    assert e.ids() == {10, 20, 30} and e.get(20) == bytes([20]) * 20 and e.get(50500, "bina") == b"palette"
    e.put(20, b"new")
    e.write(tmp / "b.drs")
    f = Drs(tmp / "b.drs")
    assert f.get(20) == b"new" and f.get(30) == bytes([30]) * 30


def test_dat_reader():
    table = [{"name": "ARCHER_FIRE", "slp": 2, "frames": 10, "angles": 8},
             {"name": "RAM", "slp": -1, "frames": 5, "angles": 8, "deltas": [0], "mirror": 0}]
    g = read_graphics(fake_dat(table))
    assert g[0].name == "ARCHER_FIRE" and g[0].slp == 2 and g[0].stored_angles == 5
    assert g[1].deltas[0].graphic_id == 0 and g[1].stored_angles == 8
    terrains = read_terrains(fake_dat(table, ground=FAKE_TERRAINS))
    assert len(terrains) == 42 and terrains[7].name == "Farm" and terrains[30].slp == 15040
    assert (terrains[29].rows, terrains[29].cols) == (3, 3) and not terrains[5].enabled
    from aom import farmland
    assert {s for s, _, _ in farmland.farm_slps(terrains)} == {15004, 15005, 15021, 15040, 15023}
    assert {s for s, _, _ in farmland.farm_slps([])} == set(farmland.FARM_SLPS)  # no table: the original ids


def test_renders_are_reproducible():
    """Trees and damaged walls come out the same in every run (Python's hash() of a string changes per process)."""
    code = ("import sys, hashlib; sys.path.insert(0, %r); "
            "from aom import nature, fortifications as FT; from aom.voxel import all_blocks; "
            "from aom.render import fit_camera, render; "
            "roots = [nature.tree(k, 110, 1).part(all_blocks()) for k in ('oak', 'palm', 'jungle', 'bamboo')]; "
            "roots.append(FT.wall_piece('stone', 'W', FT.PIECES[3], 3).part(all_blocks())); "
            "print(hashlib.md5(b''.join(render(r, -45.0, camera=fit_camera(r, -45.0)).kind.tobytes() "
            "for r in roots)).hexdigest())") % str(Path(__file__).resolve().parents[1])
    runs = {subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": seed},
                           capture_output=True, text=True, check=True).stdout for seed in ("1", "2")}
    assert len(runs) == 1, runs


def test_rendered_sprite_matches_layout():
    quant = Quantiser(parse_jasc(fake_palette()))
    frames = render_frames(ROSTER["knight"](), "walk", 6, 8, True, quant)
    assert len(frames) == 30
    data = slp.encode(frames)
    back = slp.decode(data)
    assert all(np.array_equal(a.pixels, b.pixels) for a, b in zip(frames, back))
    px = back[0].pixels
    assert (px >= slp.PLAYER).any() and (px == slp.SHADOW).any() and (px == slp.OBSTRUCTION).any()


def test_full_build(tmp: Path):
    game = fake_game(tmp / "aoe2")
    assert build_mod.main(["--game", str(game), "--jobs", "2"]) == 0
    mod = game / "Games" / "AgeOfMinecraft"
    xml = (game / "Games" / "AgeOfMinecraft.xml").read_bytes()
    assert xml.startswith(b"\xef\xbb\xbf") and b"<path>AgeOfMinecraft</path>" in xml and b'id="18" name="korean"' in xml
    out = Drs(mod / "Data" / "graphics.drs")
    orig = Drs(game / "Data" / "graphics.drs")
    assert out.get(40000) == orig.get(40000)  # untouched files are copied as they were
    for s in (987, 993, 2, 8, 173, 183, 176):
        assert slp.info(out.get(s)).num_frames == slp.info(orig.get(s)).num_frames
        assert out.get(s) != orig.get(s)
    for s in (171, 172, 181, 182):  # the ram's extra layers are blanked, same frame count
        frames = slp.decode(out.get(s))
        assert len(frames) == 25 and all((f.pixels == slp.TRANSPARENT).all() for f in frames)
    assert out.get(9000) != orig.get(9000) and out.get(9003) != orig.get(9003)  # halberdier found by name
    assert out.get(9100) == orig.get(9100)  # shared explosion is left alone
    report = (mod / "aom_report.txt").read_text()
    assert "REPLACED" in report and "BTRAM_AN" in report and "found by name HALBD_AN" in report
    # buildings and scenery
    for s in (130, 2098, 4652, 2561):
        assert out.get(s) != orig.get(s)
        assert slp.info(out.get(s)).num_frames == slp.info(orig.get(s)).num_frames
    for s in (122, 126, 2090, 2296, 4479):  # their shadow and flag layers are hidden
        assert all((f.pixels == slp.TRANSPARENT).all() for f in slp.decode(out.get(s)))
    assert out.get(2219) == orig.get(2219)  # shared with a ship: left alone
    wall = slp.decode(out.get(2098))
    assert len({f.pixels.tobytes() for f in wall}) == 5  # five different wall pieces
    w = [f.pixels.shape[1] for f in wall]  # in the game's order: "/", "\", the post, "--", "|"
    assert w[3] > 1.5 * w[4] and w[2] > w[0] > w[4]
    assert "BUILDINGS AND SCENERY" in report and "BRKS2NNE" in report and "FOAK_NN" in report
    # Pac-Man can be trained at the Wonder, and has his own icon
    from aom import datunits
    units = datunits.read_units(datunits.decompress((mod / "Data" / "empires2_x1_p1.dat").read_bytes()))
    for civ in units.units:
        pac = civ[860]
        assert pac.values["enabled"] == 1 and pac.values["train_location"] == 276 and pac.values["button"] == 1
        assert pac.values["cost"] == (0, 500, 1, 3, 500, 1, 4, 1, 0)  # 500 food, 500 gold, 1 population
        assert pac.values["speed"] == 5.0  # faster than any unit
        assert civ[4].values["enabled"] == 0  # nothing else changes
        assert pac.values["icon"] == 170  # his own icon, added to the sheet
        assert pac.values["class"] == 6  # infantry, not a predator animal: ships take him
        assert pac.values["terrain_restriction"] == 7  # the Militia's: he may stand on the beach ships unload onto
    heads = datunits.read_unit_headers(datunits.decompress((mod / "Data" / "empires2_x1_p1.dat").read_bytes()), units)
    assert [(t[1], t[3], t[4]) for t in heads.tasks[860]] == [(0, 7, -1), (1, 3, 20)]  # the Militia's boarding task
    assert len(heads.tasks[74]) == 2 and heads.tasks[861] is None
    assert "boarding task added" in report
    icons_before = slp.decode(Drs(game / "Data" / "interfac.drs").get(50730))
    icons_after = slp.decode(Drs(mod / "Data" / "interfac.drs").get(50730))
    assert len(icons_after) == len(icons_before) + 1
    assert all(np.array_equal(a.pixels, b.pixels) for a, b in zip(icons_after, icons_before))
    assert icons_after[170].pixels.shape == (36, 36) and len(np.unique(icons_after[170].pixels)) >= 4
    assert "trainable at the Wonder" in report and "Pac-Man is icon 170 (36x36)" in report
    # his name: the mod has its own language_x1_p1.dll; the game's files are untouched
    p1 = (mod / "Data" / "language_x1_p1.dll").read_bytes()
    assert langdll.read_string(p1, 5860) == "Pac-Man" and langdll.read_string(p1, 9999) == "UserPatch"
    assert langdll.read_string((game / "language_x1_p1.dll").read_bytes(), 5860) == "Furious the Monkey Boy"
    assert not (mod / "Data" / "language_x1.dll").exists()
    assert "'Furious the Monkey Boy' is now 'Pac-Man'" in report
    # his sounds: six new sounds in the .dat, their WAV files in the patch archive (on free ids)
    from aom.datfile import sound_table
    dat = datunits.decompress((mod / "Data" / "empires2_x1_p1.dat").read_bytes())
    assert sound_table(dat).count == 7
    pac = units.units[1][860]
    assert (pac.values["selection_sound"], pac.values["move_sound"], pac.values["attack_sound"],
            pac.values["train_sound"]) == (1, 2, 3, 4)
    p1 = Drs(mod / "Data" / "gamedata_x1_p1.drs")
    assert p1.ids("wav") == {15500} | set(range(15502, 15511))  # 15501 is a sound the .dat already uses
    assert all(p1.get(i, "wav")[:4] == b"RIFF" and p1.get(i, "wav")[8:12] == b"WAVE" for i in range(15502, 15511))
    assert "Pac-Man's sounds: select, move, attack, train, chomp, death" in report
    # the Javelina gets its own sprites: the missing files are created, the unit points at them
    table = read_graphics((game / "Data" / "empires2_x1_p1.dat").read_bytes())
    gid = {g.name: k for k, g in table.items()}
    for civ in units.units:
        jav, carcass = civ[822], civ[823]
        assert jav.values["standing"] == (gid["BOARJ_FN"], -1) and jav.values["walking"] == (gid["BOARJ_WN"],
                                                                                              gid["BOARJ_RN"])
        assert jav.values["dead_unit"] == 823 and carcass.values["standing"] == (gid["BOARJ_SN"], -1)
        assert carcass.id == 823 and carcass.name == "BOARJ_D" and civ[356].values["standing"][0] == gid["BOARX_FN"]
    for slp_id, frames in ((5158, 11 * 5), (5159, 10 * 5), (5161, 5 * 5), (5162, 10 * 5)):
        assert slp.info(out.get(slp_id)).num_frames == frames
    x1 = Drs(mod / "Data" / "gamedata_x1.drs")  # the javelina lives in gamedata_x1.drs: replaced there
    assert slp.info(x1.get(5157)).num_frames == 85
    assert x1.get(5157) != Drs(game / "Data" / "gamedata_x1.drs").get(5157)
    assert "6 x 8 angles mirrored  [dat, plus 2 unused frames]" in report
    # farms are terrain: their textures in terrain.drs become Minecraft farmland, in the same tile shapes
    ground, ground_before = Drs(mod / "Data" / "terrain.drs"), Drs(game / "Data" / "terrain.drs")
    assert ground.get(15000) == ground_before.get(15000)  # grass stays
    for slp_id in (15004, 15005, 15021, 15040, 15023):
        new, old = slp.decode(ground.get(slp_id)), slp.decode(ground_before.get(slp_id))
        assert len(new) == len(old)
        for a, b in zip(new, old):
            assert np.array_equal(a.pixels >= 0, b.pixels >= 0) and a.hotspot == b.hotspot
            assert a.pixels.max() < slp.PLAYER and not np.array_equal(a.pixels, b.pixels)
    ripe = slp.decode(ground.get(15004))[0].pixels
    overlap = (ripe[24:, 48:] >= 0) & (ripe[:25, :49] >= 0)  # the tile to the lower right lies over this corner
    assert np.array_equal(ripe[24:, 48:][overlap], ripe[:25, :49][overlap])  # so the tiles join up
    assert "FARMS" in report and "terrain 30 'Farm 2'" in report and "TERRAIN TABLE" in report
    # the panels: planks, inventory grey and slots, with Minecraft resource icons; the game view stays open
    ui, ui_before = Drs(mod / "Data" / "interfac.drs"), Drs(game / "Data" / "interfac.drs")
    quant = Quantiser(parse_jasc(fake_palette()))
    new, old = slp.decode(ui.get(51141))[0].pixels, slp.decode(ui_before.get(51141))[0].pixels
    assert new.shape == old.shape and np.array_equal(new < 0, old < 0)
    assert new[900, 600] == quant.indices(np.array([[198, 198, 198]]))[0]  # parchment -> inventory grey
    assert new[900, 1100] == quant.indices(np.array([[139, 139, 139]]))[0]  # the minimap's dark -> a slot
    assert not np.array_equal(new[10:27, 8:34], old[10:27, 8:34])  # a Minecraft log for wood
    new, old = slp.decode(ui.get(51121))[0].pixels, slp.decode(ui_before.get(51121))[0].pixels
    assert np.array_equal(new < 0, old < 0) and not np.array_equal(new[6:23, 11:37], old[6:23, 11:37])
    assert ui.get(51101) == ui_before.get(51101)  # no icons found: it keeps its look
    assert "INTERFACE PANELS" in report and "Minecraft style" in report and "were not found" in report
    assert not (game / "Data" / ("graphics.drs" + build_mod.BACKUP)).exists()


def test_find_game(tmp: Path):
    game = fake_game(tmp / "Age of Empires II")
    unpacked = game / "age-of-minecraft" / "tools" / "build_mod.py"  # mod unzipped inside the game folder
    unpacked.parent.mkdir(parents=True)
    assert build_mod.find_game(unpacked) == game
    assert build_mod.is_game(game) and not build_mod.is_game(tmp)
    build_mod.SEARCH_FOLDERS.append(str(tmp))  # e.g. C:\\Games\\Age Of Empires II Gold Edition
    try:
        assert build_mod.find_game(tmp / "elsewhere" / "build_mod.py") == game
    finally:
        build_mod.SEARCH_FOLDERS.pop()


def test_direct_mode_and_restore(tmp: Path):
    game = fake_game(tmp / "aoe2")
    before = (game / "Data" / "graphics.drs").read_bytes()
    dat_before = (game / "Data" / "empires2_x1_p1.dat").read_bytes()
    lang_before = {n: (game / n).read_bytes() for n in langdll.FILES}
    ground_before = (game / "Data" / "terrain.drs").read_bytes()
    panel_before = Drs(game / "Data" / "interfac.drs").get(51141)
    for _ in range(2):  # building twice starts from the originals again
        assert build_mod.main(["--game", str(game), "--mode", "direct", "--only", "militia,pacman,farms,interface",
                               "--jobs", "1"]) == 0
    assert (game / "Data" / "graphics.drs").read_bytes() != before
    assert (game / "Data" / ("graphics.drs" + build_mod.BACKUP)).read_bytes() == before
    assert (game / "Data" / "terrain.drs").read_bytes() != ground_before
    assert (game / "Data" / ("terrain.drs" + build_mod.BACKUP)).read_bytes() == ground_before
    assert (game / "Data" / "empires2_x1_p1.dat").read_bytes() != dat_before
    x1 = (game / "language_x1.dll").read_bytes()
    assert [langdll.read_string(x1, i) for i in (5860, 6860, 26860, 5861)] == [
        "Pac-Man", "Create <b>Pac-Man<b> (<cost>)", "Create <b>Pac-Man<b> (<cost>)\nA very fast cheat unit.",
        "Next unit"]
    assert langdll.read_string((game / "language_x1_p1.dll").read_bytes(), 5860) == "Pac-Man"
    assert (game / "language.dll").read_bytes() == lang_before["language.dll"]  # nothing of his in it
    icons = slp.decode(Drs(game / "Data" / "interfac.drs").get(50730))
    assert len(icons) == 171  # one icon added, not one per build
    assert Drs(game / "Data" / "interfac.drs").get(51141) != panel_before  # the panel too, in the same file
    assert Drs(game / "Data" / "gamedata_x1_p1.drs").ids("wav") == {15500} | set(range(15502, 15511))
    assert build_mod.main(["--game", str(game), "--restore"]) == 0
    assert (game / "Data" / "graphics.drs").read_bytes() == before
    assert (game / "Data" / "terrain.drs").read_bytes() == ground_before
    assert (game / "Data" / "empires2_x1_p1.dat").read_bytes() == dat_before
    assert {n: (game / n).read_bytes() for n in langdll.FILES} == lang_before
    assert not list(game.glob("*" + build_mod.BACKUP))


def test_pacman_sounds():
    from aom import gameplay, sounds
    from aom.datfile import Graphic
    waves = sounds.pacman_sounds()
    assert set(waves) == set(gameplay.SOUND_USES)
    for variants in waves.values():
        for x in variants:
            w = sounds.wav(x)
            assert w[:4] == b"RIFF" and struct.unpack_from("<I", w, 4)[0] == len(w) - 8
            assert struct.unpack_from("<HHI", w, 20) == (1, 1, 22050) and 0.1 < len(x) / 22050 < 3
            assert 0.5 < np.abs(x).max() <= 0.8
    # an attack animation whose sound plays on a frame of each angle: ours replaces it, the timing stays
    data = bytearray(struct.pack("<h", -1) + struct.pack("<6h", 3, 77, -1, -1, -1, -1) * 2)
    g = Graphic(1, "mkyby_AN", "", 1, 0, 10, 2, 0.1, 0, 0, [], -1, 0, 2)
    gameplay._graphic_sound(data, g, 600)
    assert struct.unpack_from("<h", data, 0)[0] == -1
    assert struct.unpack_from("<12h", data, 2) == (3, 600, -1, -1, -1, -1) * 2
    silent = bytearray(struct.pack("<h", -1))  # an animation with no sound gets ours as its own
    gameplay._graphic_sound(silent, Graphic(2, "mkyby_DN", "", 2, 0, 10, 2, 0.1, 0, 0, [], -1, 0, -1), 601)
    assert struct.unpack("<h", silent)[0] == 601


def test_language_files():
    from aom import gameplay
    x1 = langdll.build_dll({5860: "Furious the Monkey Boy", 6860: "Create Furious the Monkey Boy", 5861: "Next"})
    p1 = langdll.build_dll({100: "UserPatch"})  # does not have him: the game falls back to language_x1.dll
    changed, notes = gameplay.rename_pacman({"language_x1_p1.dll": p1, "language_x1.dll": x1},
                                            {"name": 5860, "creation": 6860, "help": 26860})
    assert list(changed) == ["language_x1.dll"] and len(changed["language_x1.dll"]) == len(x1)
    assert langdll.read_string(changed["language_x1.dll"], 6860) == "Create Pac-Man"
    assert langdll.read_string(changed["language_x1.dll"], 5861) == "Next"
    short = langdll.build_dll({5860: "Mono"})  # a name shorter than "Pac-Man" cannot grow in place
    changed, notes = gameplay.rename_pacman({"language_x1.dll": short}, {"name": 5860})
    assert not changed and "does not fit" in notes[-1]
    changed, notes = gameplay.rename_pacman({"language_x1.dll": p1}, {"name": 5860})
    assert not changed and "in none of the language files" in notes[0]


def main() -> None:
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    for name, fn in tests:
        with tempfile.TemporaryDirectory() as d:
            if "tmp" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                fn(Path(d))
            else:
                fn()
        print(f"ok  {name}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
