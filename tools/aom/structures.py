"""The economic and military buildings, in every style and age.

Every building is one design parameterised by a `Style` (see styles.py);
the age picks the style's materials. Footprints follow the game (one AoE2
tile is about 2.83 blocks): 1x1 -> 3 blocks, 2x2 -> 5, 3x3 -> 8, 4x4 -> 11,
5x5 -> 14. The origin is the footprint centre, which lands on the sprite's
hotspot.
"""
from __future__ import annotations

import numpy as np

from . import voxel as V
from .geometry import Part, cuboid
from .styles import Style, style_for
from .textures import FACES, Painter, parse

B = V.BLOCK


def _s(name: str, blocks: int) -> V.Structure:
    return V.Structure(name, origin=(blocks / 2, blocks / 2))


# --------------------------------------------------------------------------- shared pieces

def walls(s: V.Structure, st: Style, x0, y0, x1, y1, z0, z1, wall: str = None, base: bool = True,
          corners: bool = True) -> None:
    """A box of walls with a foundation course and corner pillars."""
    s.fill(x0, y0, z0, x1, y1, z1, wall or st.wall)
    if base:
        s.fill(x0, y0, z0, x1, y1, z0, st.base)
    if corners:
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            s.fill(x, y, z0 + (1 if base else 0), x, y, z1, st.trim)


def windows_x(s: V.Structure, x0: int, x1: int, y: int, z: int, glass: str = "glass", every: int = 2) -> None:
    """Windows along a +y facing wall (runs along x)."""
    for x in range(x0, x1 + 1, every):
        V.window(s, x, y, z, "+y", glass)


def windows_y(s: V.Structure, y0: int, y1: int, x: int, z: int, glass: str = "glass", every: int = 2) -> None:
    for y in range(y0, y1 + 1, every):
        V.window(s, x, y, z, "+x", glass)


def roof(s: V.Structure, st: Style, x0, y0, x1, y1, z, axis: str = "x") -> int:
    """The style's roof over a rectangle of walls; returns the level above it."""
    if st.roof_type == "gable":
        return V.gable_roof(s, x0, x1, y0, y1, z, st.roof, st.wall_hi, st.roof_cap, axis=axis)
    if st.roof_type == "hip":
        return V.hip_roof(s, x0, x1, y0, y1, z, st.roof)
    if st.roof_type == "pagoda":
        V.pagoda_roof(s, x0, x1, y0, y1, z, st.roof, st.trim)
        return V.hip_roof(s, x0, x1, y0, y1, z + 1, st.roof, overhang=0)
    # flat: slab roof with a parapet
    s.fill(x0, y0, z, x1, y1, z, st.wall_hi)
    for x in range(x0, x1 + 1):
        for y in (y0, y1):
            if (x + y) % 2 == 0:
                s.set(x, y, z + 1, st.base)
    for y in range(y0, y1 + 1):
        for x in (x0, x1):
            if (x + y) % 2 == 0:
                s.set(x, y, z + 1, st.base)
    return z + 1


def awning(s: V.Structure, x0: int, x1: int, y: int, z: int, cloth: str, facing: str = "+y") -> None:
    for i, x in enumerate(range(x0, x1 + 1)):
        c = cloth if i % 2 == 0 else "white_wool"
        if facing == "+y":
            s.set(x, y, z, c, "slab")
        else:
            s.set(y, x, z, c, "slab")


def team_banner(s: V.Structure, bx: float, by: float, z: float, facing: str = "+y", seed: str = "b",
                height: float = 22, pattern: str = "cross") -> None:
    """A banner on the outside of a +x / +y wall at block position (bx, by), top at block height z."""
    ox, oy = s.origin
    p = Painter(f"banner-{seed}")
    if facing == "+y":
        at = ((bx - ox) * B, (by - oy) * B + 0.2, z * B - 1)
    else:
        at = ((bx - ox) * B + 0.2, (by - oy) * B, z * B - 1)
    s.extras += V.banner(p, at, facing=facing, height=height, pattern=pattern)


def flag(s: V.Structure, bx: float, by: float, z: float, height: float = 28, seed: str = "f", t: float = 0.0):
    ox, oy = s.origin
    s.extras += V.flag_pole(Painter(f"flag-{seed}"), ((bx - ox) * B, (by - oy) * B, z * B), height=height, wave=t)


def torch(s: V.Structure, bx: float, by: float, z: float) -> None:
    ox, oy = s.origin
    s.extras += V.torch_boxes(((bx - ox) * B, (by - oy) * B, z * B))


def lantern(s: V.Structure, bx: float, by: float, z: float) -> None:
    ox, oy = s.origin
    s.extras += V.lantern_boxes(((bx - ox) * B, (by - oy) * B, z * B))


def chimney(s: V.Structure, x: int, y: int, z0: int, z1: int, block: str = "bricks") -> None:
    s.fill(x, y, z0, x, y, z1, block)
    s.set(x, y, z1 + 1, "cobblestone", "wall")


def log_pile(s: V.Structure, x: int, y: int, z: int, n: int, wood: str = "oak", axis: str = "x") -> None:
    """Logs lying on their side (a timber stack)."""
    for i in range(n):
        s.set(x + (i if axis == "x" else 0), y + (i if axis == "y" else 0), z, f"{wood}_wood")


# --------------------------------------------------------------------------- houses

def house(style: str, age: int, variant: int = 0) -> V.Structure:
    """House (2x2): a 5x5 cottage. Three variants, like the three house frames in the game."""
    st = style_for(style, age)
    s = _s("house", 5)
    v = variant % 3
    if st.key == "M":
        walls(s, st, 0, 0, 4, 4, 0, 2, corners=False)
        s.fill(0, 0, 3, 4, 4, 3, st.wall_hi)
        for x in range(0, 5):
            for y in range(0, 5):
                if x in (0, 4) or y in (0, 4):
                    if (x + y) % 2 == 0:
                        s.set(x, y, 4, st.base, "slab")
        V.door(s, 2, 4, 1, "+y", "acacia")
        V.window(s, 4, 2, 2, "+x")
        s.set(1, 4, 2, "orange_terracotta")
        s.set(3, 4, 2, "orange_terracotta")
        if v == 1:
            s.fill(3, 0, 4, 4, 1, 4, st.wall_hi)
            s.set(3, 1, 5, "white_wool", "carpet")
        if v == 2:
            s.set(4, 4, 4, "orange_wool", "slab")
            s.set(0, 4, 4, "orange_wool", "slab")
        team_banner(s, 4.95, 1, 3, "+x", seed=f"h{v}", height=16)
        return s
    if st.key == "X":
        walls(s, st, 0, 0, 4, 4, 0, 2, corners=False)
        s.fill(0, 0, 0, 4, 4, 0, st.base)
        V.door(s, 2, 4, 1, "+y", "jungle")
        V.window(s, 4, 2, 2, "+x")
        V.hip_roof(s, 0, 4, 0, 4, 3, "hay")
        s.set(2, 2, 6, "gold_block" if age >= 3 else "jungle_log")
        team_banner(s, 4.95, 1, 3, "+x", seed=f"h{v}", height=16)
        return s
    # G, W, E, F: a framed cottage with a gable or pagoda roof
    walls(s, st, 0, 0, 4, 4, 0, 2)
    V.door(s, 2 if v != 2 else 1, 4, 1, "+y", st.wood if st.key != "G" else "oak")
    V.window(s, 4, 2, 2, "+x")
    if v == 1:
        V.window(s, 4, 1, 1, "+x")
        V.window(s, 4, 3, 1, "+x")
    else:
        V.window(s, 3 if v != 2 else 3, 4, 2, "+y")
    top = roof(s, st, 0, 0, 4, 4, 3, axis="x" if v != 1 else "y")
    if v == 2 or st.key == "G":
        chimney(s, 1, 1, 3, top, "cobblestone" if st.key in ("G", "E") else "bricks")
    if st.key == "F":
        lantern(s, 4.6, 4.6, 0)
    team_banner(s, 4.95, 1, 3, "+x", seed=f"h{v}", height=16)
    return s


# --------------------------------------------------------------------------- town center

def town_center(style: str, age: int) -> V.Structure:
    """Town Center (4x4): an 11x11 village hall with a bell tower."""
    st = style_for(style, age)
    s = _s("town_center", 11)
    s.fill(0, 0, 0, 10, 10, 0, st.base)
    if st.key == "M":
        walls(s, st, 1, 1, 9, 9, 0, 4, corners=False)
        for y in (3, 5, 7):
            V.window(s, 9, y, 2, "+x")
        for x in (3, 7):
            V.window(s, x, 9, 2, "+y")
        V.door(s, 5, 9, 1, "+y", "acacia")
        s.fill(1, 1, 5, 9, 9, 5, st.wall_hi)
        for x in range(1, 10):
            for y in range(1, 10):
                if (x in (1, 9) or y in (1, 9)) and (x + y) % 2 == 0:
                    s.set(x, y, 6, st.base)
        s.dome(5.5, 5.5, 6, 3.2, st.dome, squash=1.1)
        s.set(5, 5, 10, st.accent)
        for x, y in ((1, 1), (9, 1), (1, 9), (9, 9)):
            s.fill(x, y, 5, x, y, 7, st.stone2)
        awning(s, 2, 8, 10, 3, "orange_wool")
        top = 11
    elif st.key == "X":
        s.fill(0, 0, 1, 10, 10, 1, st.base)
        s.fill(1, 1, 2, 9, 9, 2, st.wall)
        s.fill(2, 2, 3, 8, 8, 5, st.wall_hi)
        for y in (4, 6):
            V.window(s, 8, y, 4, "+x")
        V.door(s, 5, 8, 3, "+y", "jungle")
        for x in range(0, 11):
            s.set(x, 10, 1, st.wall, "stair_+y")
        V.hip_roof(s, 2, 8, 2, 8, 6, "hay")
        top = 11
        for x, y in ((1, 1), (9, 1), (1, 9), (9, 9)):
            torch(s, x + 0.5, y + 0.5, 3)
    else:
        # ground floor with a triple door on the +y side
        walls(s, st, 0, 0, 10, 10, 1, 3, wall=st.base if age >= 3 else st.wall)
        for x in (3, 7):
            s.fill(x, 10, 1, x, 10, 3, st.trim)
        V.door(s, 4, 10, 1, "+y", st.wood if st.key != "G" else "oak", double=True)
        V.door(s, 6, 10, 1, "+y", st.wood if st.key != "G" else "oak")
        for y in (2, 5, 8):
            V.window(s, 10, y, 2, "+x")
        for x in (1, 9):
            V.window(s, x, 10, 2, "+y")
        # upper floor
        walls(s, st, 0, 0, 10, 10, 4, 5, wall=st.wall_hi if age >= 3 else st.wall, base=False)
        for x, y in ((5, 10), (10, 5)):
            s.fill(x, y, 4, x, y, 5, st.trim)
        for y in (2, 3, 7, 8):
            V.window(s, 10, y, 5, "+x")
        for x in (2, 3, 7, 8):
            V.window(s, x, 10, 5, "+y")
        top = roof(s, st, 0, 0, 10, 10, 6, axis="x")
    # bell tower
    if st.key not in ("M", "X"):
        z0 = top - 3
        s.fill(4, 4, z0, 6, 6, top - 1, st.wall_hi)
        for x, y in ((4, 4), (4, 6), (6, 4), (6, 6)):
            s.fill(x, y, top, x, y, top + 2, st.trim if st.key != "G" else "oak_log", "post")
        s.fill(4, 4, top + 3, 6, 6, top + 3, st.roof if st.key != "G" else "spruce_planks", "slab")
        s.set(5, 5, top + 3, st.roof_cap if st.key != "G" else "spruce_planks")
        s.set(5, 5, top + 4, "player_wool", "slab")
        ox, oy = s.origin
        s.extras += V.bell_boxes(((5.5 - ox) * B, (5.5 - oy) * B, (top + 2) * B + 12))
    if age >= 4:
        for x, y in ((0, 0), (0, 10), (10, 0), (10, 10)):
            s.fill(x, y, 1, x, y, 7, st.stone)
            s.set(x, y, 8, st.accent)
    team_banner(s, 10.95, 2.5, 4, "+x", seed="tc1", height=26)
    team_banner(s, 10.95, 8.5, 4, "+x", seed="tc2", height=26)
    team_banner(s, 2.5, 10.95, 4, "+y", seed="tc3", height=26)
    team_banner(s, 8.5, 10.95, 4, "+y", seed="tc4", height=26)
    return s


# --------------------------------------------------------------------------- mill

def mill(style: str, age: int, t: float = 0.0, part: str = "all") -> V.Structure:
    """Mill (2x2): a windmill whose wool sails turn. `part`: all, body or sails."""
    st = style_for(style, age)
    s = _s("mill", 5)
    if age <= 1:
        # Dark Age: an open grinding hut with hay and a grindstone
        for x, y in ((0, 0), (0, 4), (4, 0), (4, 4)):
            s.fill(x, y, 0, x, y, 2, "oak_log")
        V.hip_roof(s, 0, 4, 0, 4, 3, "hay")
        s.set(2, 2, 0, "grindstone_block")
        s.set(1, 3, 0, "hay")
        s.set(3, 1, 0, "hay")
        s.set(3, 3, 0, "composter")
        return s
    if part in ("all", "body"):
        body = st.base if st.key in ("E", "W", "F") else st.wall
        s.cylinder(2.5, 2.5, 2.3, 0, 4, body)
        s.cylinder(2.5, 2.5, 2.0, 5, 6, st.wall_hi if st.key != "X" else st.wall)
        V.door(s, 2, 4, 0, "+y", st.wood)
        V.window(s, 4, 2, 3, "+x")
        s.cone(2.5, 2.5, 7, 2.2, st.roof if st.key not in ("M", "X") else st.dome, step=0.8)
        s.set(3, 4, 0, "hay")
        s.set(4, 3, 0, "hay")
        s.set(4, 4, 0, "composter")
        if age >= 3:
            s.fill(1, 1, 0, 1, 1, 1, "hay")
    if part in ("all", "sails"):
        s.parts.append(sails(s, st, t, hub=(2.5, 4.9, 5.5)))
    return s


def sails(s: V.Structure, st: Style, t: float, hub) -> Part:
    """Four wool sails on a hub in front of the +y wall, turning with t (0..1 = a quarter turn)."""
    ox, oy = s.origin
    hx, hy, hz = ((hub[0] - ox) * B, (hub[1] - oy) * B, hub[2] * B)
    p = Painter("sails")
    cloth = p.grid(["WWWWWW", "WSSSSW", "WSSSSW", "WWWWWW"], {"W": "#e9ecec", "S": "#d8d2c4"})
    wood = {f: np.tile(parse("#6b4a2a"), (4, 4, 1)) for f in FACES}
    cloth_f = {f: cloth for f in FACES}
    arms = []
    for k in range(4):
        arm = Part(f"sail{k}", pivot=(hx, hy, hz), rot=(0, k * 90 + t * 90, 0), boxes=[
            cuboid((hx - 1.5, hy, hz), (3, 2, 60), wood),
            cuboid((hx + 1.5, hy + 0.5, hz + 12), (14, 1, 46), cloth_f)])
        arms.append(arm)
    hub_part = Part("sails", boxes=[cuboid((hx - 2.5, hy - 1, hz - 2.5), (5, 3, 5), wood)])
    # the sails face the +y side; the arms spin in the x-z plane
    for a in arms:
        hub_part.add(a)
    return hub_part


# --------------------------------------------------------------------------- resource camps

def lumber_camp(style: str, age: int = 2) -> V.Structure:
    """Lumber camp (2x2): an open shed with stacked logs and a chopping block."""
    st = style_for(style, max(2, age))
    s = _s("lumber_camp", 5)
    s.fill(0, 0, 0, 4, 1, 0, st.floor if st.floor not in ("sand", "gravel") else "coarse_dirt")
    for x, y in ((0, 0), (4, 0), (0, 2), (4, 2)):
        s.fill(x, y, 0, x, y, 2, st.log)
    s.fill(0, 0, 3, 4, 2, 3, st.planks, "slab")
    s.fill(1, 0, 0, 3, 0, 2, st.planks)
    s.carve(1, 0, 1, 3, 0, 2)
    log_pile(s, 1, 1, 0, 3, "oak")
    log_pile(s, 0, 3, 0, 3, "birch")
    log_pile(s, 0, 4, 0, 2, "spruce")
    log_pile(s, 0, 3, 1, 2, "oak")
    s.set(3, 4, 0, "oak_log")  # chopping block
    s.set(4, 3, 0, "crafting_table")
    ox, oy = s.origin
    axe_head = {f: np.tile(parse("#b8b8b8"), (4, 4, 1)) for f in FACES}
    handle = {f: np.tile(parse("#6b4a2a"), (2, 2, 1)) for f in FACES}
    s.extras += [cuboid(((3.5 - ox) * B - 1, (4.5 - oy) * B - 1, B), (2, 2, 12), handle),
                 cuboid(((3.5 - ox) * B - 1, (4.5 - oy) * B - 4, B + 8), (2, 6, 5), axe_head)]
    team_banner(s, 4.95, 1, 2.8, "+x", seed="lc", height=14)
    return s


def mining_camp(style: str, age: int = 2) -> V.Structure:
    """Mining camp (2x2): a shed over a minecart on rails, with ore blocks and a pickaxe."""
    st = style_for(style, max(2, age))
    s = _s("mining_camp", 5)
    for x, y in ((0, 0), (4, 0), (0, 2), (4, 2)):
        s.fill(x, y, 0, x, y, 2, st.log)
    s.fill(0, 0, 3, 4, 2, 3, st.planks, "slab")
    s.fill(1, 0, 0, 3, 0, 1, "cobblestone")
    s.set(1, 1, 0, "gold_ore")
    s.set(3, 1, 0, "stone")
    s.set(2, 1, 0, "iron_ore")
    ox, oy = s.origin
    rail = {f: np.tile(parse("#7a7a7a"), (2, 2, 1)) for f in FACES}
    ties = {f: np.tile(parse("#6b4a2a"), (2, 2, 1)) for f in FACES}
    for i in range(10):
        s.extras.append(cuboid(((-ox + 0.2) * B + i * 7.5, (3.2 - oy) * B, 0), (3, 16, 1), ties))
    for dy in (3.4, 4.3):
        s.extras.append(cuboid(((-ox + 0.2) * B, (dy - oy) * B, 1), (74, 1.5, 1), rail))
    cart = {f: np.tile(parse("#6a6a6a"), (4, 4, 1)) for f in FACES}
    gold = {f: np.tile(parse("#f5d84a"), (4, 4, 1)) for f in FACES}
    cx, cy = (1.2 - ox) * B, (3.3 - oy) * B
    s.extras += [cuboid((cx, cy, 2), (20, 16, 2), cart), cuboid((cx, cy, 2), (2, 16, 10), cart),
                 cuboid((cx + 18, cy, 2), (2, 16, 10), cart), cuboid((cx, cy, 2), (20, 2, 10), cart),
                 cuboid((cx, cy + 14, 2), (20, 2, 10), cart), cuboid((cx + 3, cy + 3, 4), (14, 10, 8), gold)]
    pick_head = {f: np.tile(parse("#8a8a8a"), (3, 3, 1)) for f in FACES}
    handle = {f: np.tile(parse("#6b4a2a"), (2, 2, 1)) for f in FACES}
    px, py = (4.3 - ox) * B, (1.5 - oy) * B
    s.extras += [cuboid((px, py, 0), (2, 2, 18), handle), cuboid((px, py - 6, 15), (2, 14, 3), pick_head)]
    team_banner(s, 4.95, 1, 2.8, "+x", seed="mc", height=14)
    return s


# --------------------------------------------------------------------------- military production

def barracks(style: str, age: int) -> V.Structure:
    """Barracks (3x3): a long hall with a fenced training yard and armour stands."""
    st = style_for(style, age)
    s = _s("barracks", 8)
    walls(s, st, 0, 0, 7, 4, 0, 3 if age >= 3 else 2)
    z = 4 if age >= 3 else 3
    V.door(s, 3, 4, 1, "+y", st.wood, double=True)
    windows_x(s, 1, 6, 4, 2, every=5)
    windows_y(s, 1, 3, 7, 2)
    roof(s, st, 0, 0, 7, 4, z, axis="x")
    # training yard in front (+y)
    for x in range(0, 8):
        s.set(x, 7, 0, st.fence, "fence")
    for y in range(5, 8):
        s.set(0, y, 0, st.fence, "fence")
        s.set(7, y, 0, st.fence, "fence")
    s.clear(3, 7, 0)
    s.clear(4, 7, 0)
    for x in (2, 5):  # armour stands: iron chestplate on a post with a helmet
        s.set(x, 6, 0, "oak_planks", "post")
        s.set(x, 6, 1, "iron_block", "cube_small")
    s.set(6, 5, 0, "hay")
    if age >= 3:
        s.fill(0, 0, 4, 0, 0, z + 2, st.stone)
        s.fill(7, 0, 4, 7, 0, z + 2, st.stone)
    team_banner(s, 7.95, 1.5, z - 0.2, "+x", seed="br1", height=22)
    team_banner(s, 1.5, 4.95, z - 0.2, "+y", seed="br2", height=22)
    return s


def archery_range(style: str, age: int) -> V.Structure:
    """Archery range (3x3): a hall with targets on hay bales and a fletching table."""
    st = style_for(style, age)
    s = _s("archery_range", 8)
    walls(s, st, 0, 0, 4, 7, 0, 2 if age <= 2 else 3)
    z = 3 if age <= 2 else 4
    V.door(s, 4, 3, 1, "+x", st.wood, double=True)
    windows_y(s, 1, 6, 4, 2, every=5)
    windows_x(s, 1, 3, 7, 2)
    roof(s, st, 0, 0, 4, 7, z, axis="y")
    for y in (1, 4):  # targets
        s.set(7, y, 0, "hay")
        s.set(7, y, 1, "target")
    s.set(6, 6, 0, "fletching_table")
    for y in range(0, 8):
        if y not in (2, 3, 5, 6):
            continue
    ox, oy = s.origin
    arrow = {f: np.tile(parse("#6b4a2a"), (1, 1, 1)) for f in FACES}
    feather = {f: np.tile(parse("#f2f2f2"), (2, 2, 1)) for f in FACES}
    for y, dz in ((1.3, 22), (1.7, 25), (4.4, 21)):
        s.extras += [cuboid(((6.2 - ox) * B, (y - oy) * B, dz), (12, 1, 1), arrow),
                     cuboid(((6.2 - ox) * B, (y - oy) * B - 0.5, dz - 0.5), (3, 2, 2), feather)]
    team_banner(s, 4.95, 1.5, z - 0.2, "+x", seed="ar1", height=20)
    team_banner(s, 2, 7.95, z - 0.2, "+y", seed="ar2", height=20)
    return s


def stable(style: str, age: int) -> V.Structure:
    """Stable (3x3): a barn with hay bales, a water trough and a fenced paddock."""
    st = style_for(style, age)
    s = _s("stable", 8)
    walls(s, st, 0, 0, 7, 4, 0, 3)
    s.carve(2, 4, 1, 5, 4, 2)  # wide barn door opening
    s.fill(2, 4, 3, 5, 4, 3, st.trim)
    s.fill(2, 3, 1, 5, 3, 1, "hay")
    s.set(3, 3, 2, "hay")
    windows_y(s, 1, 3, 7, 2)
    roof(s, st, 0, 0, 7, 4, 4, axis="x")
    for x in range(0, 8):
        s.set(x, 7, 0, st.fence, "fence")
    for y in range(5, 8):
        s.set(7, y, 0, st.fence, "fence")
    s.set(0, 6, 0, "cauldron")
    s.set(1, 6, 0, "cauldron")
    s.set(6, 5, 0, "hay")
    s.set(5, 6, 0, "hay")
    team_banner(s, 7.95, 1.5, 3.8, "+x", seed="st1", height=22)
    team_banner(s, 6.5, 4.95, 3.8, "+y", seed="st2", height=22, pattern="stripe")
    return s


def blacksmith(style: str, age: int, t: float = 0.0, part: str = "all") -> V.Structure:
    """Blacksmith (3x3): a stone forge with a chimney, anvil and blast furnace. `part` smoke = the smoke only."""
    st = style_for(style, age)
    s = _s("blacksmith", 8)
    if part in ("all", "body"):
        walls(s, st, 0, 0, 5, 5, 0, 2, wall=st.base if st.key != "M" else st.wall)
        V.door(s, 2, 5, 1, "+y", st.wood)
        V.window(s, 5, 2, 2, "+x")
        s.set(5, 4, 1, "blast_furnace")
        top = roof(s, st, 0, 0, 5, 5, 3, axis="x")
        chimney(s, 1, 1, 3, top + 1, "bricks" if st.key != "M" else "cut_sandstone")
        # open-air forge in front
        s.fill(6, 1, 0, 7, 4, 0, "smooth_stone", "slab")
        s.set(6, 2, 0, "furnace")
        s.set(7, 3, 0, "anvil_block", "cube_small")
        s.set(6, 4, 0, "smithing_table")
        s.set(7, 1, 0, "lava", "slab")
        s.set(3, 7, 0, "grindstone_block", "cube_small")
        s.set(1, 7, 0, "barrel")
        for x, y in ((7, 0), (7, 5)):
            s.fill(x, y, 0, x, y, 2, st.log)
        s.fill(6, 0, 3, 7, 5, 3, st.planks, "slab")
        team_banner(s, 5.95, 1, 2.8, "+x", seed="bs", height=18)
    if part in ("all", "smoke"):
        ox, oy = s.origin
        top_z = (s.height() if part == "all" else 9) * B
        for k in range(4):
            ph = (t + k / 4) % 1.0
            size = 5 + ph * 7
            grey = 0.55 + 0.3 * ph
            col = f"#{int(grey * 255):02x}{int(grey * 255):02x}{int(grey * 255):02x}"
            x = (1.5 - ox) * B + np.sin(ph * 5 + k) * 4 + ph * 10
            y = (1.5 - oy) * B + ph * 6
            s.extras.append(cuboid((x - size / 2, y - size / 2, top_z + ph * 40), (size, size, size),
                                   {f: np.tile(parse(col), (4, 4, 1)) for f in FACES}))
    return s


# --------------------------------------------------------------------------- trade and learning

def market(style: str, age: int) -> V.Structure:
    """Market (4x4): stalls with striped wool awnings, barrels, chests and an emerald trading post."""
    st = style_for(style, age)
    s = _s("market", 11)
    s.fill(0, 0, 0, 10, 10, 0, st.floor if st.floor != "podzol" else "gravel", "carpet")
    walls(s, st, 0, 0, 5, 4, 0, 2)
    V.door(s, 2, 4, 1, "+y", st.wood)
    V.window(s, 5, 2, 2, "+x")
    roof(s, st, 0, 0, 5, 4, 3, axis="x")
    # stalls
    colours = [st.cloth, "yellow_wool", "blue_wool", "lime_wool"]
    stalls = [(7, 1), (7, 5), (1, 7), (5, 8)]
    for k, (x, y) in enumerate(stalls):
        for dx, dy in ((0, 0), (2, 0), (0, 2), (2, 2)):
            s.fill(x + dx, y + dy, 0, x + dx, y + dy, 1, st.fence, "fence")
        for dx in range(0, 3):
            for dy in range(0, 3):
                c = colours[k % 4] if (dx + dy) % 2 == 0 else "white_wool"
                s.set(x + dx, y + dy, 2, c, "slab")
        s.set(x + 1, y + 1, 0, ["barrel", "chest", "melon", "pumpkin"][k % 4])
        s.set(x, y + 1, 0, "barrel" if k % 2 else "hay")
    s.set(9, 9, 0, "emerald_block")
    s.set(5, 6, 0, "composter")
    flag(s, 10.2, 10.2, 0, height=40, seed="mk")
    team_banner(s, 5.95, 1, 2.8, "+x", seed="mk1", height=18)
    return s


def monastery(style: str, age: int = 3) -> V.Structure:
    """Monastery (3x3): a chapel with stained glass and a bell tower."""
    st = style_for(style, age)
    s = _s("monastery", 8)
    wall = st.wall_hi if st.key in ("W", "F") else st.wall
    walls(s, st, 1, 0, 6, 7, 0, 4, wall=wall)
    V.door(s, 3, 7, 1, "+y", st.wood, double=True)
    for y in (1, 3, 5):
        s.set(6, y, 2, "yellow_stained_glass" if y == 3 else "blue_stained_glass")
        s.set(6, y, 3, "red_stained_glass")
    s.set(3, 7, 4, "purple_stained_glass")
    s.set(4, 7, 4, "purple_stained_glass")
    if st.key == "M":
        s.fill(1, 0, 5, 6, 7, 5, st.wall_hi)
        s.dome(3.5, 3.5, 6, 2.6, st.dome)
        s.fill(0, 6, 0, 0, 6, 9, st.stone2)
        s.set(0, 6, 10, st.accent)
    elif st.key == "X":
        V.hip_roof(s, 1, 6, 0, 7, 5, st.stone2, overhang=0)
    else:
        roof(s, st, 1, 0, 6, 7, 5, axis="y")
    if st.key != "M":
        s.fill(0, 0, 0, 1, 1, 8, st.stone)  # bell tower on the back corner
        s.fill(0, 0, 9, 1, 1, 9, st.roof if st.key != "X" else st.stone2, "slab")
        ox, oy = s.origin
        s.extras += V.bell_boxes(((1 - ox) * B, (1 - oy) * B, 8.6 * B))
        s.carve(0, 1, 7, 1, 1, 8)
        s.carve(1, 0, 7, 1, 1, 8)
    s.set(7, 3, 0, "cauldron")  # the cleric's brewing corner
    s.set(7, 5, 0, "red_mushroom_block", "cube_small")
    team_banner(s, 6.95, 6, 3.8, "+x", seed="mo", height=22, pattern="stripe")
    return s


def university(style: str, age: int, t: float = 0.0, part: str = "all") -> V.Structure:
    """University (3x3): a library of bookshelves under a dome or tower, with an enchanting table."""
    st = style_for(style, age)
    s = _s("university", 8)
    if part in ("all", "body"):
        walls(s, st, 0, 0, 7, 7, 0, 3, wall=st.wall_hi if st.key != "X" else st.wall)
        for y in (1, 2, 5, 6):
            s.set(7, y, 1, "bookshelf")
            s.set(7, y, 2, "bookshelf")
        for x in (1, 2, 5, 6):
            s.set(x, 7, 1, "bookshelf")
            s.set(x, 7, 2, "bookshelf")
        V.door(s, 3, 7, 1, "+y", st.wood, double=True)
        V.door(s, 7, 3, 1, "+x", st.wood, double=True)
        s.fill(0, 0, 4, 7, 7, 4, st.base)
        if st.key == "M" or (age >= 4 and st.key not in ("F", "X")):
            s.dome(4.0, 4.0, 5, 2.8, st.dome)
            s.set(3, 3, 8, "enchanting_table")
        else:
            roof(s, st, 1, 1, 6, 6, 5, axis="x")
        s.set(0, 7, 5, "lectern_top")
        team_banner(s, 7.95, 4, 3.8, "+x", seed="un", height=18)
    if part in ("all", "flag"):
        flag(s, 7.5, 7.5, 5, height=26, seed="un", t=t)
    return s


# --------------------------------------------------------------------------- siege and sea

def siege_workshop(style: str, age: int = 3) -> V.Structure:
    """Siege workshop (4x4): an open workshop full of TNT, dispensers and pistons."""
    st = style_for(style, age)
    s = _s("siege_workshop", 11)
    walls(s, st, 0, 0, 10, 4, 0, 3)
    s.carve(2, 4, 1, 8, 4, 3)
    for x in (2, 5, 8):
        s.fill(x, 4, 1, x, 4, 3, st.trim)
    roof(s, st, 0, 0, 10, 4, 4, axis="x")
    for x in (3, 6):
        s.set(x, 3, 1, "piston")
        s.set(x + 1, 3, 1, "dispenser")
    s.fill(1, 6, 0, 2, 7, 0, "tnt")
    s.set(1, 6, 1, "tnt")
    s.set(9, 6, 0, "crafting_table")
    s.set(9, 8, 0, "smithing_table")
    log_pile(s, 4, 9, 0, 4, "spruce")
    log_pile(s, 5, 8, 0, 3, "oak")
    s.set(6, 6, 0, "redstone_block", "slab")
    ox, oy = s.origin
    wheel = {f: np.tile(parse("#5a4028"), (4, 4, 1)) for f in FACES}
    for wx, wy in ((7.2, 6.4), (8.4, 6.4)):
        s.extras.append(cuboid(((wx - ox) * B, (wy - oy) * B, 0), (3, 14, 14), wheel))
    team_banner(s, 10.95, 1.5, 3.8, "+x", seed="sw1", height=22)
    team_banner(s, 1, 4.95, 3.8, "+y", seed="sw2", height=22)
    return s


def dock(style: str, age: int) -> V.Structure:
    """Dock (3x3): a plank pier on log posts with a boathouse, barrels and a crane."""
    st = style_for(style, age)
    s = _s("dock", 8)
    s.fill(0, 0, 0, 7, 7, 0, st.planks, "slab")
    for x in range(0, 8, 3):
        for y in range(0, 8, 3):
            s.set(x, y, 0, st.log)
    walls(s, st, 0, 0, 3, 3, 1, 3, base=False)
    V.door(s, 1, 3, 1, "+y", st.wood)
    V.window(s, 3, 1, 2, "+x")
    roof(s, st, 0, 0, 3, 3, 4, axis="x")
    s.set(6, 1, 1, "barrel")
    s.set(6, 2, 1, "barrel")
    s.set(5, 1, 1, "chest")
    for x in range(0, 8):
        s.set(x, 7, 1, st.fence, "fence")
    s.clear(4, 7, 1)
    s.fill(7, 5, 1, 7, 5, 4, st.log)  # crane
    s.fill(7, 3, 5, 7, 5, 5, st.planks, "slab")
    ox, oy = s.origin
    rope = {f: np.tile(parse("#8a7a5a"), (1, 1, 1)) for f in FACES}
    s.extras += [cuboid(((7.5 - ox) * B, (3.5 - oy) * B, 2.5 * B), (1, 1, 2.5 * B), rope),
                 cuboid(((7.5 - ox) * B - 5, (3.5 - oy) * B - 5, 2 * B), (10, 10, 8),
                        {f: np.tile(parse("#6b4a2a"), (4, 4, 1)) for f in FACES})]
    if age >= 3:
        lantern(s, 3.6, 7.6, 1.5)
        s.set(1, 5, 1, "barrel")
    team_banner(s, 3.95, 1.5, 3.8, "+x", seed="dk", height=18)
    return s


# --------------------------------------------------------------------------- fields

WHEAT_STAGES = 8


def wheat_sprite(stage: int) -> np.ndarray:
    """Wheat crop texture at a growth stage (0 seedlings .. 7 ripe), like Minecraft's."""
    p = Painter(f"wheat{stage}")
    h = 4 + stage * 1.7
    tex = np.zeros((16, 16, 5), np.float32)
    ripe = stage >= 7
    for c in range(1, 16, 3):
        top = int(16 - h + p.rng.integers(0, 2))
        stem = parse("#6a9a2a" if not ripe else "#b0a040")
        tex[top:, c] = stem
        if stage >= 5:
            head = parse("#c9a83a" if ripe else "#8aa83a")
            tex[max(0, top):top + 3, max(0, c - 1):c + 2] = head
    return tex


def farm(stage: float = 1.0) -> V.Structure:
    """Farm (3x3): farmland around a water channel with wheat; `stage` 1 = ripe .. 0 = bare soil."""
    s = _s("farm", 8)
    s.fill(0, 0, 0, 7, 7, 0, "farmland", "layer")
    for y in range(0, 8):
        s.set(4, y, 0, "water", "layer")
    for x in (0, 7):
        for y in (0, 7):
            s.set(x, y, 0, "oak_planks", "post")
    level = int(round(stage * (WHEAT_STAGES - 1)))
    if stage > 0.02:
        sprite = wheat_sprite(level)
        rng = np.random.default_rng(7)
        for x in range(0, 8):
            if x == 4:
                continue
            for y in range(0, 8):
                if (x in (0, 7) and y in (0, 7)) or rng.random() > 0.2 + 0.8 * stage:
                    continue
                s.plant(x + 0.5, y + 0.5, 3 / 16, sprite, 14)
    return s


def fish_trap(stage: float = 1.0) -> V.Structure:
    """Fish trap (3x3): a ring of fences and nets in the water with fish inside."""
    s = _s("fish_trap", 8)
    for x in range(1, 7):
        for y in (1, 6):
            s.set(x, y, 0, "oak_planks", "fence")
    for y in range(1, 7):
        for x in (1, 6):
            s.set(x, y, 0, "oak_planks", "fence")
    for x, y in ((1, 1), (1, 6), (6, 1), (6, 6)):
        s.fill(x, y, 0, x, y, 1, "oak_log", "post")
    ox, oy = s.origin
    rng = np.random.default_rng(11)
    fish = int(round(stage * 6))
    for k in range(fish):
        fx, fy = rng.uniform(2, 5.5, 2)
        col = ["#c8a064", "#a83a2a", "#f09a3a"][k % 3]
        s.extras.append(cuboid(((fx - ox) * B, (fy - oy) * B, 1), (7, 3, 2),
                               {f: np.tile(parse(col), (2, 2, 1)) for f in FACES}))
    net = {f: np.tile(parse("#d8d0b8"), (1, 1, 1)) for f in FACES}
    for x in np.linspace(1.5, 6.5, 6):
        s.extras.append(cuboid(((x - ox) * B, (1.5 - oy) * B, 0), (0.6, 5 * B, 1.2), net))
    return s


# --------------------------------------------------------------------------- building sites and ruins

def construction(tiles: float, variant: int = 0, progress: float = 0.5) -> V.Structure:
    """A building site: a foundation outline and scaffolding, sized to the footprint."""
    n = max(2, int(round(V.tiles_to_blocks(tiles))))
    s = _s("construction", n)
    rng = np.random.default_rng(100 + variant)
    for x in range(n):
        for y in range(n):
            if x in (0, n - 1) or y in (0, n - 1):
                s.set(x, y, 0, "cobblestone" if (x + y + variant) % 3 else "oak_planks", "slab")
    h = max(1, int(round((1 + variant) * max(1, n // 3) * 0.7)))
    for x in range(0, n, max(2, n // 3)):
        for y in (0, n - 1):
            s.fill(x, y, 0, x, y, h, "scaffolding")
    for y in range(0, n, max(2, n // 3)):
        for x in (0, n - 1):
            s.fill(x, y, 0, x, y, h, "scaffolding")
    for _ in range(n):
        x, y = rng.integers(1, n - 1, 2)
        s.set(x, y, 0, ["oak_planks", "cobblestone", "stone_bricks", "oak_log"][rng.integers(0, 4)],
              "slab" if rng.random() < 0.5 else "full")
    s.set(n - 2, n - 2, 1 if n > 3 else 0, "crafting_table")
    return s


def rubble(tiles: float, variant: int = 0) -> V.Structure:
    """What is left of a building: scattered cobblestone, gravel and broken planks."""
    n = max(2, int(round(V.tiles_to_blocks(tiles))))
    s = _s("rubble", n)
    rng = np.random.default_rng(200 + variant)
    for x in range(n):
        for y in range(n):
            r = rng.random()
            if r < 0.35:
                s.set(x, y, 0, "gravel", "layer")
            elif r < 0.6:
                s.set(x, y, 0, "cobblestone", "slab")
            elif r < 0.75:
                s.set(x, y, 0, "mossy_cobblestone" if variant % 2 else "cracked_stone_bricks")
            elif r < 0.85:
                s.set(x, y, 0, "oak_planks", "slab")
            elif r < 0.9:
                s.set(x, y, 0, "coal_ore", "slab")
    for _ in range(max(1, n // 3)):
        x, y = rng.integers(0, n, 2)
        s.set(x, y, 1, "cobblestone", "slab")
    return s
