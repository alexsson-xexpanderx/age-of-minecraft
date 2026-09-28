"""Tests for the in-game export: SLP and DRS round trips, the .dat graphics
reader, and a full build against a fake game folder.

    python tools/tests/test_export.py        (or: python -m pytest tools/tests)
"""
from __future__ import annotations

import struct
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_mod  # noqa: E402
from aom import slp  # noqa: E402
from aom.datfile import read_graphics  # noqa: E402
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


def _unit_bytes(uid: int, utype: int, name: str, standing: int = -1) -> bytes:
    """One unit record in the Conquerors layout (mirrors aom.datunits)."""
    nb = name.encode()
    b = bytearray(struct.pack("<bHhHHh", utype, len(nb), uid, 5000 + uid, 6000 + uid, 0))
    b += struct.pack("<hhhhbhfb", standing, -1, -1, -1, 0, 30, 4.0, 0)
    b += struct.pack("<fffhhhbbhbhbb", 0.2, 0.2, 2.0, -1, -1, -1, 0, 0, 159 if uid == 860 else 1, 0, -1, 0, 0)
    b += struct.pack("<hhhhffbbhbhfbbbbbfb", -1, -1, -1, -1, 0.5, 0.5, 0, 0, 0, 0, 0, 0.0, 0, 0, 0, 0, 0, 0.0, 0)
    b += struct.pack("<iiibbbbbbbBbhbBfff", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)
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


def fake_civs(civs: int = 2, slots: int = 900, monkey_graphic: int = 0) -> bytes:
    """Civilisations with unit tables: filler units, the Wonder (276) and Furious the Monkey Boy (860)."""
    out = bytearray()
    for c in range(civs):
        out += struct.pack("<b20sHhh", 1, f"civ{c}".encode(), 4, 1, 1) + struct.pack("<4f", 1, 2, 3, 4)
        out += struct.pack("<bH", 0, slots)
        present = [u for u in range(slots) if u % 2 == 0 or u in (276, 860)]
        out += struct.pack(f"<{slots}i", *[1 if u in present else 0 for u in range(slots)])
        for u in present:
            if u == 276:
                out += _unit_bytes(u, 80, "WNDR")
            elif u == 860:
                out += _unit_bytes(u, 70, "mkyby", monkey_graphic)
            else:
                out += _unit_bytes(u, 10, f"U{u}")
    return bytes(out)


def fake_dat(graphics: list[dict], civs: bytes = b"") -> bytes:
    """A minimal empires2_x1_p1.dat: header sections plus the given graphics (and unit tables)."""
    b = bytearray(b"VER 5.7\0")
    restrictions, terrains = 2, 3
    b += struct.pack("<HH", restrictions, terrains)
    b += struct.pack(f"<{2 * restrictions}i", *([1] * 2 * restrictions))
    for _ in range(restrictions):
        b += struct.pack(f"<{terrains}f", *([1.0] * terrains)) + bytes(16 * terrains)
    b += struct.pack("<H", 2) + bytes(36 * 2)
    b += struct.pack("<H", 1) + struct.pack("<hhHi", 5, 0, 2, 300000) + bytes(23 * 2)
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
    b += civs
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(bytes(b)) + c.flush()


def fake_game(root: Path) -> Path:
    data = root / "Data"
    data.mkdir(parents=True)
    interfac = Drs()
    interfac.put(50500, fake_palette(), "bina")
    icon = slp.SlpFrame(np.full((36, 36), 77, np.int16), (0, 0))
    interfac.put(50730, slp.encode([icon] * 170))  # the unit icon sheet
    interfac.write(data / "interfac.drs")
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
    table.append({"name": "mkyby_FN", "slp": 5299, "frames": 15, "angles": 8})
    graphics.put(5299, build_mod.blank(15 * 5))
    graphics.put(40000, b"not a sprite we touch")
    graphics.write(data / "graphics.drs")
    (data / "empires2_x1_p1.dat").write_bytes(fake_dat(table, fake_civs(monkey_graphic=len(table) - 1)))
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
    assert "BUILDINGS AND SCENERY" in report and "BRKS2NNE" in report and "FOAK_NN" in report
    # Pac-Man can be trained at the Wonder, and has his own icon
    from aom import datunits
    units = datunits.read_units(datunits.decompress((mod / "Data" / "empires2_x1_p1.dat").read_bytes()))
    for civ in units.units:
        pac = civ[860]
        assert pac.values["enabled"] == 1 and pac.values["train_location"] == 276 and pac.values["button"] == 1
        assert pac.values["cost"][:2] == (0, 200) and civ[4].values["enabled"] == 0  # nothing else changes
    icons_before = slp.decode(Drs(game / "Data" / "interfac.drs").get(50730))
    icons_after = slp.decode(Drs(mod / "Data" / "interfac.drs").get(50730))
    assert len(icons_after) == len(icons_before)
    assert np.array_equal(icons_after[0].pixels, icons_before[0].pixels)
    assert not np.array_equal(icons_after[159].pixels, icons_before[159].pixels)
    assert "trainable at the Wonder" in report
    assert "6 x 8 angles mirrored  [dat, plus 2 unused frames]" in report
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
    assert build_mod.main(["--game", str(game), "--mode", "direct", "--only", "militia,pacman", "--jobs", "1"]) == 0
    assert (game / "Data" / "graphics.drs").read_bytes() != before
    assert (game / "Data" / ("graphics.drs" + build_mod.BACKUP)).read_bytes() == before
    assert (game / "Data" / "empires2_x1_p1.dat").read_bytes() != dat_before
    assert build_mod.main(["--game", str(game), "--restore"]) == 0
    assert (game / "Data" / "graphics.drs").read_bytes() == before
    assert (game / "Data" / "empires2_x1_p1.dat").read_bytes() == dat_before


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
