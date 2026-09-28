"""Map decorations: yurts, tents, ruins, graves, statues, flags, torches, the relic..."""
from __future__ import annotations

import numpy as np

from . import voxel as V
from .geometry import Part, cuboid
from .structures import flag
from .textures import FACES, PC, Painter, parse

B = V.BLOCK


def _s(name: str, n: float = 3) -> V.Structure:
    return V.Structure(name, origin=(n / 2, n / 2))


def _solid(col, n=2):
    return {f: np.tile(parse(col), (n, n, 1)) for f in FACES}


def yurt(variant: int = 0) -> V.Structure:
    """A round felt yurt; thatched (hay) or canvas (wool) roof, door facing different ways."""
    canvas = variant >= 4
    s = _s("yurt", 7 if variant in (0, 7) else 5)
    n = 7 if variant in (0, 7) else 5
    c = n / 2
    s.cylinder(c, c, c - 0.3, 0, 1, "white_wool" if canvas else "brown_wool")
    s.cone(c, c, 2, c - 0.1, "white_wool" if canvas else "hay", step=0.9)
    s.set(int(c), int(c), s.height(), "spruce_planks", "slab")
    if variant % 4 != 2:
        side = variant % 2
        if side:
            V.door(s, int(c), n - 1, 0, "+y", "spruce")
        else:
            V.door(s, n - 1, int(c), 0, "+x", "spruce")
    if variant % 4 == 2:
        for k in range(3):
            s.set(k, n, 0, "oak_wood")
    return s


def pavilion(variant: int = 0) -> V.Structure:
    """A striped wool tent on fence posts."""
    cols = ["red_wool", "blue_wool", "yellow_wool"]
    s = _s("pavilion", 5)
    for x, y in ((0, 0), (0, 4), (4, 0), (4, 4)):
        s.fill(x, y, 0, x, y, 1, "oak_planks", "fence")
    for k, lo in enumerate(range(0, 3)):
        c = cols[variant % 3] if k % 2 == 0 else "white_wool"
        s.ring(lo, lo, 4 - lo, 4 - lo, 2 + k, 2 + k, c, "slab" if k == 2 else "full")
    s.set(2, 2, 5, cols[variant % 3], "fence")
    flag(s, 2.5, 2.5, 5, height=16, seed=f"pav{variant}")
    return s


def ruins(variant: int = 0) -> V.Structure:
    """Broken walls of mossy stone bricks."""
    rng = np.random.default_rng(variant + 90)
    n = 6
    s = _s("ruins", n)
    for x in range(n):
        for y in range(n):
            if x in (0, n - 1) or y in (0, n - 1):
                h = rng.integers(0, 4)
                for z in range(h):
                    s.set(x, y, z, ["mossy_stone_bricks", "cracked_stone_bricks", "stone_bricks"][rng.integers(0, 3)])
            elif rng.random() < 0.25:
                s.set(x, y, 0, "mossy_cobblestone", "slab")
    s.fill(1, 1, 0, 1, 1, 3, "chiseled_stone_bricks")  # a lone column
    return s


def stone_head(variant: int = 0) -> V.Structure:
    """A giant mossy stone head, half sunk in the ground."""
    s = _s("stone_head", 3)
    s.fill(0, 0, 0, 2, 2, 2, "mossy_stone_bricks" if variant % 2 else "stone")
    s.set(2, 0, 1, "coal_ore")
    s.set(2, 2, 1, "coal_ore")
    s.set(2, 1, 0, "cracked_stone_bricks", "slab")
    s.set(1, 1, 3, "moss_block", "carpet")
    return s


def statue() -> V.Structure:
    """A stone statue of Steve on a pedestal."""
    s = _s("statue", 3)
    s.fill(0, 0, 0, 2, 2, 0, "chiseled_stone_bricks")
    s.fill(1, 1, 1, 1, 1, 2, "smooth_stone")
    ox, oy = s.origin
    st = _solid("#a8a8a8", 4)
    cx, cy = (1.5 - ox) * B, (1.5 - oy) * B
    s.extras += [cuboid((cx - 4, cy - 2, 3 * B), (8, 4, 12), st), cuboid((cx - 4, cy - 4, 3 * B + 12), (8, 8, 8), st),
                 cuboid((cx - 8, cy - 2, 3 * B), (4, 4, 12), st), cuboid((cx + 4, cy - 2, 3 * B), (4, 4, 12), st)]
    return s


def graves(variant: int = 0) -> V.Structure:
    rng = np.random.default_rng(variant + 30)
    s = _s("graves", 3)
    for k in range(1 + variant % 3):
        x, y = k % 3, (k * 2) % 3
        s.set(x, y, 0, "cobblestone" if rng.random() < 0.5 else "mossy_cobblestone", "wall")  # headstone
        s.set(x, (y + 1) % 3, 0, "coarse_dirt", "layer")
    return s


def heads(variant: int = 0) -> V.Structure:
    """Mob heads on fence posts."""
    s = _s("heads", 1)
    s.fill(0, 0, 0, 0, 0, 1, "spruce_planks", "fence")
    ox, oy = s.origin
    col = ["#c8c8c8", "#4a7a3a", "#5aa84a", "#2a2a2a"][variant % 4]  # skeleton, zombie, creeper, wither
    face = np.tile(parse(col), (8, 8, 1))
    face[3:5, 1:3] = face[3:5, 5:7] = parse("#1a1a1a")
    if variant % 4 == 2:
        face[5:8, 3:5] = parse("#1a1a1a")
    s.extras.append(cuboid((-4, -4, 2 * B), (8, 8, 8), {**{f: face for f in FACES}}))
    return s


def signpost(angle: float = 0.0) -> Part:
    """An oak sign on a post, turned to `angle` degrees."""
    wood = _solid("#a8844e", 4)
    board = np.tile(parse("#b8945e"), (8, 16, 1))
    board[2, 2:14] = board[4, 2:10] = board[6, 2:12] = parse("#3a2a18")
    faces = {f: board for f in FACES}
    return Part("sign", rot=(0, 0, angle), boxes=[cuboid((-1, -1, 0), (2, 2, 16), wood),
                                                  cuboid((-8, -1, 14), (16, 2, 9), faces)])


def standing_torch(t: float = 0.0) -> V.Structure:
    s = _s("torch", 1)
    s.set(0, 0, 0, "oak_planks", "fence")
    s.extras += V.torch_boxes((0, 0, B), flame=t)
    return s


def banner_flag(variant: int = 0, t: float = 0.0) -> V.Structure:
    s = _s("flag", 1)
    if variant in (3, 4):  # a banner between two poles
        for x in (-1, 1):
            s.extras.append(cuboid((x * 12 - 1, -1, 0), (2, 2, 40), _solid("#5a4028")))
        p = Painter(f"bn{variant}")
        cloth = p.grid(["PPPPPPPP", "PLLPPLLP", "PPPPPPPP", "PDPDPDPD"], {"P": PC(0.6), "L": PC(0.85), "D": PC(0.35)})
        wave = np.sin(t * 2 * np.pi) * 1.5
        s.extras.append(cuboid((-11, -0.5 + wave, 18), (22, 1, 20), {f: cloth for f in FACES}))
        return s
    flag(s, 0.5, 0.5, 0, height=40, seed=f"fl{variant}", t=t)
    return s


def relic(glint: float = 0.0) -> V.Structure:
    """The relic: a small golden reliquary chest with an enchantment glint."""
    s = _s("relic", 1)
    g = np.tile(parse("#e8b923"), (8, 8, 1))
    g[3] = parse("#8a5a12")
    g[2:5, 3:5] = parse("#6a3ab0" if glint < 0.5 else "#a87ae0")
    s.extras.append(cuboid((-5, -4, 0), (10, 8, 8), {f: g for f in FACES}))
    return s


def skeleton(angle: float = 0.0) -> Part:
    """Bones lying on the ground."""
    bone = _solid("#e2dcc8", 2)
    return Part("skeleton", rot=(0, 0, angle), boxes=[
        cuboid((-2, -8, 0), (4, 16, 2), bone), cuboid((-6, -4, 0), (12, 2, 2), bone),
        cuboid((-5, 1, 0), (10, 2, 2), bone), cuboid((-3, 8, 0), (6, 6, 5), bone)])


def rug(variant: int = 0) -> V.Structure:
    cols = ["red_wool", "blue_wool", "yellow_wool", "purple_wool", "orange_wool", "cyan_wool"]
    s = _s("rug", 3)
    s.fill(0, 0, 0, 2, 2, 0, cols[variant % 6], "carpet")
    s.ring(0, 0, 2, 2, 0, 0, cols[(variant + 2) % 6], "carpet")
    return s


def broken_cart() -> V.Structure:
    s = _s("broken_cart", 3)
    s.fill(0, 1, 0, 2, 1, 0, "oak_planks", "slab")
    s.set(1, 0, 0, "oak_planks", "slab")
    ox, oy = s.origin
    s.extras.append(cuboid(((2.2 - ox) * B, (0.3 - oy) * B, 0), (3, 14, 14), _solid("#5a4028", 4)))
    return s


def crater(variant: int = 0) -> V.Structure:
    rng = np.random.default_rng(variant + 10)
    s = _s("crater", 3)
    for x in range(3):
        for y in range(3):
            s.set(x, y, 0, "coarse_dirt" if (x, y) != (1, 1) else "gravel", "layer")
    if rng.random() < 0.5:
        s.set(1, 1, 0, "coal_ore", "slab")
    return s


def sea_rock(variant: int = 0) -> V.Structure:
    s = _s("sea_rock", 3)
    s.fill(0, 0, 0, 2, 2, 0, "prismarine_bricks" if variant else "stone")
    s.fill(1, 0, 1, 2, 1, 1, "stone")
    s.set(1, 1, 2, "mossy_cobblestone", "slab")
    return s
