"""Walls, gates, towers and the castle.

Wall graphics in the game hold five pieces, one per "angle". The game picks
the angle from the wall's line: frame 0 runs along the map's y axis (screen
"/"), frame 1 along its x axis (screen "\\"), frame 2 is the post used at
both ends of a line and at its corners, frame 3 runs diagonally across the
screen ("--") and frame 4 up and down it ("|"). Gates use the same order
(letters A to D, without the post). Our pieces, in that order:

    x     along model x (screen "/")    y  along model y (screen "\\")
    post  a pillar filling the tile     h  along x = -y (screen "--")
    v     along x = y (screen "|")

Straight pieces are one block thick and reach just past the tile's edges, so
neighbours join up; diagonal ones are Minecraft block staircases whose end
blocks meet the next tile's at the corner. The post fills its whole tile, so
a wall arriving from any side meets it.
"""
from __future__ import annotations

import zlib

import numpy as np

from . import voxel as V
from .geometry import Part
from .structures import flag, team_banner, torch
from .styles import Style, style_for

B = V.BLOCK
PIECES = ("x", "y", "post", "h", "v")  # the game's frame order


def _cell(name: str) -> V.Structure:
    return V.Structure(name, origin=(1.5, 1.5))


def _piece_cells(piece: str) -> list[tuple[int, int]]:
    return {"post": [(x, y) for x in range(3) for y in range(3)], "x": [(0, 1), (1, 1), (2, 1)], "y": [(1, 0), (1, 1), (1, 2)],
            "v": [(0, 0), (1, 1), (2, 2)], "h": [(2, 0), (1, 1), (0, 2)]}[piece]


# --------------------------------------------------------------------------- wall pieces

def wall_materials(kind: str, st: Style) -> tuple[str, str, int]:
    """(body, top, height) for palisade, stone and fortified walls."""
    if kind == "palisade":
        return "spruce_log", "spruce_log", 2
    if kind == "stone":
        body = {"W": "cobblestone", "E": "mossy_cobblestone", "M": "sandstone", "F": "stone_bricks",
                "X": "mossy_cobblestone"}.get(st.key, "cobblestone")
        return body, body, 3
    body = {"W": "stone_bricks", "E": "stone_bricks", "M": "cut_sandstone", "F": "stone_bricks",
            "X": "mossy_stone_bricks"}.get(st.key, "stone_bricks")
    top = {"W": "chiseled_stone_bricks", "E": "mossy_stone_bricks", "M": "chiseled_sandstone",
           "F": "red_terracotta", "X": "chiseled_stone_bricks"}.get(st.key, "stone_bricks")
    return body, top, 4


def wall_piece(kind: str, style: str, piece: str, damage: int = 0, progress: float = 1.0) -> V.Structure:
    """One wall tile. `damage` 0..3 knocks blocks out; `progress` < 1 is a wall being built."""
    st = style_for(style, 3 if kind == "fortified" else 2)
    body, top, height = wall_materials(kind, st)
    s = _cell(f"wall_{kind}_{piece}")
    cells = _piece_cells(piece)
    rng = np.random.default_rng(zlib.crc32(f"{kind} {style} {piece} {damage}".encode()))  # hash() changes every run
    built = max(1, int(np.ceil(height * progress))) if progress < 1 else height
    for (x, y) in cells:
        for z in range(built):
            if damage and z >= height - damage and rng.random() < 0.3 + 0.2 * damage:
                continue
            if kind == "palisade":
                s.set(x, y, z, body)
            elif z == 0 and kind == "fortified":
                s.set(x, y, z, st.base if st.key != "M" else "smooth_sandstone")
            else:
                s.set(x, y, z, body)
        if progress < 1:
            s.set(x, y, built, "scaffolding")
            continue
        if kind == "palisade":
            s.set(x, y, height, "spruce_log", "post")  # sharpened stakes
        elif piece == "post":
            continue  # the pillar gets its own top below
        elif kind == "stone":
            if not damage or rng.random() > 0.4:
                s.set(x, y, height, top, "wall")
        elif (x + y) % 2 == 0 and (not damage or rng.random() > 0.5):
            s.set(x, y, height, top)
    if piece == "post" and progress >= 1:
        if kind == "palisade":  # the middle stake stands a log taller
            s.set(1, 1, height, "spruce_log")
            s.set(1, 1, height + 1, "spruce_log", "post")
        else:  # a pillar one block taller than the wall, with a battlement on its corners
            for x in range(3):
                for y in range(3):
                    if not damage or rng.random() > 0.3 * damage:
                        s.set(x, y, height, body)
            for x, y in ((0, 0), (2, 0), (0, 2), (2, 2)):
                if not damage or rng.random() > 0.4:
                    s.set(x, y, height + 1, top, "wall" if kind == "stone" else "full")
    if damage >= 2:
        for (x, y) in cells:
            if rng.random() < 0.5:
                s.set(x + rng.integers(-1, 2), y + rng.integers(-1, 2), 0, "gravel", "layer")
    return s


# --------------------------------------------------------------------------- gates

GATE_DIRS = {"A": "x", "B": "y", "C": "h", "D": "v"}  # graphic letter -> our direction


def gate_section(style: str, age: int, direction: str, is_open: bool, half: float = None) -> Part:
    """The gate between its two towers, `half` blocks from the centre to a tower centre."""
    st = style_for(style, age)
    kind = "fortified" if age >= 3 else "stone"
    body, top, height = wall_materials(kind, st)
    diagonal = direction in ("h", "v")
    if half is None:
        half = V.tiles_to_blocks(1.5) * (2 ** 0.5 if diagonal else 1)
    length = max(3, int(round(2 * half - 2)))  # up to the towers (1.5 blocks each), overlapping a little
    s = V.Structure("gate", origin=(length / 2, 0.5))
    height += 1
    s.fill(0, 0, 0, length - 1, 0, height - 1, body)
    mid = length // 2
    w0, w1 = mid - 1, mid + (0 if length % 2 else 0)
    w1 = w0 + 2 if length >= 5 else w0 + 1
    s.carve(w0, 0, 0, w1, 0, 2)
    for x in range(length):
        if x % 2 == 0:
            s.set(x, 0, height, top)
    s.fill(w0, 0, 3, w1, 0, 3, st.stone2 if kind == "fortified" else body)
    if is_open:
        for x in range(w0, w1 + 1):
            s.set(x, 0, 2, "iron_bars", "bars")  # the portcullis, pulled up
    else:
        for x in range(w0, w1 + 1):
            for z in range(0, 3):
                s.set(x, 0, z, "iron_bars", "bars")
    s.set(w0 - 1, 0, 3, "player_wool") if length > 5 else None
    part = s.part(V.all_blocks())
    rz = {"x": 0.0, "y": 90.0, "h": -45.0, "v": 45.0}[direction]
    return Part("gate", rot=(0, 0, rz), children=[part])


def gate_tower(style: str, age: int) -> V.Structure:
    """The tower at each end of a gate."""
    st = style_for(style, age)
    kind = "fortified" if age >= 3 else "stone"
    body, top, height = wall_materials(kind, st)
    s = _cell("gate_tower")
    h = height + 3
    s.fill(0, 0, 0, 2, 2, h - 1, body)
    s.fill(0, 0, 0, 2, 2, 0, st.base if kind == "fortified" else body)
    V.crenellate(s, 0, 2, 0, 2, h, top)
    V.window(s, 2, 1, h - 2, "+x")
    V.window(s, 1, 2, h - 2, "+y")
    team_banner(s, 2.95, 1.5, h - 0.5, "+x", seed="gt", height=18)
    return s


# --------------------------------------------------------------------------- towers

def watch_tower(style: str, level: int) -> V.Structure:
    """Watch tower (1), guard tower (2), keep (3) or bombard tower (4), on one tile."""
    st = style_for(style, min(4, level + 1))
    s = _cell(f"tower{level}")
    if level == 1:
        wood = st.log
        for x, y in ((0, 0), (0, 2), (2, 0), (2, 2)):
            s.fill(x, y, 0, x, y, 5, wood)
        s.fill(0, 0, 0, 2, 2, 1, st.base)
        s.fill(0, 0, 2, 2, 2, 4, st.planks)
        V.window(s, 2, 1, 3, "+x")
        V.window(s, 1, 2, 3, "+y")
        s.fill(0, 0, 5, 2, 2, 5, st.planks)
        for x in range(0, 3):
            for y in range(0, 3):
                if x in (0, 2) or y in (0, 2):
                    s.set(x, y, 6, st.fence, "fence")
        if st.key == "F":
            V.pagoda_roof(s, 0, 2, 0, 2, 7, st.roof)
            s.set(1, 1, 8, st.roof)
        elif st.key in ("M", "X"):
            s.fill(0, 0, 7, 2, 2, 7, st.wall_hi, "slab")
        else:
            V.hip_roof(s, 0, 2, 0, 2, 7, st.roof)
        torch(s, 2.6, 2.6, 6)
        return s
    body = st.stone
    if level == 2:
        s.fill(0, 0, 0, 2, 2, 6, body)
        s.fill(0, 0, 0, 2, 2, 0, st.base)
        for z in (2, 5):
            V.window(s, 2, 1, z, "+x")
            V.window(s, 1, 2, z, "+y")
        V.crenellate(s, 0, 2, 0, 2, 7, st.stone2)
        flag(s, 1.5, 1.5, 7, height=24, seed="gt")
        return s
    if level == 3:
        s.fill(0, 0, 0, 2, 2, 7, body)
        s.fill(0, 0, 0, 2, 2, 0, st.base)
        s.fill(-1, -1, 8, 3, 3, 8, st.stone2)
        for x, y in ((-1, 3), (3, -1), (3, 3)):
            s.set(x, y, 7, st.stone2, "ustair_" + ("+y" if y == 3 and x != 3 else "+x"))
        V.crenellate(s, -1, 3, -1, 3, 9, body)
        for z in (2, 5):
            V.window(s, 2, 1, z, "+x")
            V.window(s, 1, 2, z, "+y")
        if st.key == "F":
            V.pagoda_roof(s, 0, 2, 0, 2, 10, st.roof)
        elif st.key == "M":
            s.dome(1.5, 1.5, 9, 1.6, st.dome)
        else:
            s.cone(1.5, 1.5, 9, 1.6, st.roof, step=0.5)
        team_banner(s, 3.95, 1.5, 7.5, "+x", seed="kp", height=20)
        return s
    # bombard tower: squat and thick, a dispenser cannon on top
    s.fill(-1, -1, 0, 3, 3, 4, "deepslate_bricks" if st.key != "M" else "cut_sandstone")
    s.fill(-1, -1, 0, 3, 3, 0, st.base)
    for x, y in ((-1, -1), (-1, 3), (3, -1), (3, 3)):
        s.clear(x, y, 4)
    V.crenellate(s, -1, 3, -1, 3, 5, st.stone2)
    s.set(1, 1, 5, "dispenser")
    s.set(2, 2, 5, "tnt")
    s.set(3, 1, 2, "dispenser")
    s.set(1, 3, 2, "dispenser")
    team_banner(s, 3.95, 0, 4.5, "+x", seed="bt", height=18)
    return s


def outpost() -> V.Structure:
    """Outpost: a lookout post with a torch."""
    s = _cell("outpost")
    for x, y in ((0, 0), (0, 2), (2, 0), (2, 2)):
        s.fill(x, y, 0, x, y, 2, "oak_planks", "fence")
    s.fill(0, 0, 3, 2, 2, 3, "oak_planks", "slab")
    s.set(1, 1, 0, "oak_log")
    s.set(1, 1, 1, "oak_log")
    s.set(1, 1, 2, "oak_log")
    torch(s, 1.5, 1.5, 3.5)
    team_banner(s, 2.95, 1.5, 2.8, "+x", seed="op", height=14)
    return s


# --------------------------------------------------------------------------- castle

def castle(style: str, age: int = 3) -> V.Structure:
    """Castle (4x4): curtain walls, four corner towers, a gatehouse and a central keep."""
    st = style_for(style, max(3, age))
    s = V.Structure("castle", origin=(5.5, 5.5))
    stone, detail = st.stone, st.stone2
    s.fill(0, 0, 0, 10, 10, 0, st.base)
    # curtain walls
    s.ring(0, 0, 10, 10, 1, 5, stone)
    V.crenellate(s, 0, 10, 0, 10, 6, detail)
    # corner towers
    for x, y in ((0, 0), (0, 8), (8, 0), (8, 8)):
        s.fill(x, y, 0, x + 2, y + 2, 8, stone)
        V.crenellate(s, x, x + 2, y, y + 2, 9, detail)
        if st.key == "F":
            V.pagoda_roof(s, x, x + 2, y, y + 2, 9, st.roof)
        elif st.key == "M":
            s.dome(x + 1.5, y + 1.5, 9, 1.5, st.dome)
        elif st.key in ("W", "E"):
            s.cone(x + 1.5, y + 1.5, 10, 1.6, st.roof, step=0.45)
        V.window(s, x + 2, y + 1, 6, "+x")
        V.window(s, x + 1, y + 2, 6, "+y")
    # keep
    k0, k1 = 3, 7
    s.fill(k0, k0, 1, k1, k1, 9, stone)
    for z in (4, 7):
        V.window(s, k1, 5, z, "+x")
        V.window(s, 5, k1, z, "+y")
    if st.key == "X":  # a stepped temple keep
        s.fill(k0 + 1, k0 + 1, 10, k1 - 1, k1 - 1, 11, detail)
        s.set(5, 5, 12, "gold_block")
    elif st.key == "F":
        V.pagoda_roof(s, k0, k1, k0, k1, 10, st.roof)
        V.pagoda_roof(s, k0 + 1, k1 - 1, k0 + 1, k1 - 1, 12, st.roof)
        s.set(5, 5, 14, "gold_block")
    elif st.key == "M":
        V.crenellate(s, k0, k1, k0, k1, 10, detail)
        s.dome(5.5, 5.5, 10, 2.2, st.dome)
    else:
        V.crenellate(s, k0, k1, k0, k1, 10, detail)
        s.fill(k0 + 1, k0 + 1, 10, k1 - 1, k1 - 1, 11, stone)
        V.hip_roof(s, k0 + 1, k1 - 1, k0 + 1, k1 - 1, 12, st.roof, overhang=0)
    # gatehouse on the +y side
    s.fill(4, 10, 0, 6, 11, 7, stone)
    s.carve(5, 10, 1, 5, 11, 3)
    s.fill(5, 11, 1, 5, 11, 3, "iron_bars", "bars")
    V.crenellate(s, 4, 6, 10, 11, 8, detail)
    for x in (4, 6):
        torch(s, x + 0.5, 12.1, 2)
    team_banner(s, 10.95, 3, 5.5, "+x", seed="c1", height=28)
    team_banner(s, 10.95, 7.5, 5.5, "+x", seed="c2", height=28)
    team_banner(s, 2.5, 10.95, 5.5, "+y", seed="c3", height=28)
    team_banner(s, 8.5, 10.95, 5.5, "+y", seed="c4", height=28)
    flag(s, 5.5, 5.5, s.height(), height=30, seed="ck")
    return s
