"""Trees, resources and plants.

Trees are generated to a requested height, so each variant in a forest
sprite can match the size of the original tree it replaces (forests keep
their density and silhouette). Gold and stone mines become piles of ore
blocks, berry bushes become sweet berry bushes, and so on.
"""
from __future__ import annotations

import zlib

import numpy as np

from . import voxel as V
from .geometry import cuboid
from .textures import FACES, parse

B = V.BLOCK
PX_PER_BLOCK_UP = B * 1.5 * np.cos(np.radians(30))  # screen pixels per block of height


def blocks_for_height(px: float) -> int:
    return max(2, int(round(px / PX_PER_BLOCK_UP)))


def _s(name: str, n: int = 3) -> V.Structure:
    return V.Structure(name, origin=(n / 2, n / 2))


def _blob(s: V.Structure, cx: int, cy: int, z: int, r: int, leaf: str, rng, fullness: float = 0.85) -> None:
    for x in range(cx - r, cx + r + 1):
        for y in range(cy - r, cy + r + 1):
            corner = abs(x - cx) == r and abs(y - cy) == r
            if corner and rng.random() > 0.35:
                continue
            if rng.random() < fullness or (x == cx and y == cy):
                s.set(x, y, z, leaf)


# --------------------------------------------------------------------------- trees

TREE_KINDS = ("oak", "birch", "spruce", "snowy_spruce", "jungle", "palm", "bamboo", "dark_oak", "acacia",
              "dead", "cherry", "azalea")


def tree(kind: str, height_px: float = 110.0, seed: int = 0, part: str = "all") -> V.Structure:
    """A tree about `height_px` screen pixels tall. `part`: all, trunk (bottom half) or crown (top half)."""
    rng = np.random.default_rng(seed * 7919 + zlib.crc32(kind.encode()) % 1000)  # hash() changes every run
    h = blocks_for_height(height_px)
    s = _s(f"tree_{kind}")
    c = 1
    if kind in ("spruce", "snowy_spruce"):
        s.fill(c, c, 0, c, c, h - 1, "spruce_log")
        leaf = "snowy_spruce_leaves" if kind == "snowy_spruce" else "spruce_leaves"
        z0 = 1 if h < 6 else 2
        layers = max(2, h - z0)
        for i in range(layers):  # a cone: wide at the bottom, alternating skirts
            frac = i / max(1, layers - 1)
            r = int(round(2.3 * (1 - frac)))
            if i % 2 == 1 and r > 0:
                r -= 1
            for x in range(c - r, c + r + 1):
                for y in range(c - r, c + r + 1):
                    if abs(x - c) + abs(y - c) <= r + (1 if r >= 2 else 0):
                        s.set(x, y, z0 + i, leaf)
        s.set(c, c, h, leaf)
        s.set(c, c, h + 1, leaf, "slab")
    elif kind == "palm":
        trunk = max(3, h - 2)
        lean = rng.choice([-1, 1])
        for z in range(trunk):
            dx = lean if z > trunk * 0.6 else 0
            s.set(c + dx, c, z, "jungle_log")
        top = (c + lean, c, trunk)
        tx, ty, tz = top
        s.set(tx, ty, tz, "jungle_leaves")
        s.set(tx, ty, tz + 1, "jungle_leaves")
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):  # four drooping fronds
            s.set(tx + dx, ty + dy, tz, "jungle_leaves")
            s.set(tx + 2 * dx, ty + 2 * dy, tz, "jungle_leaves")
            s.set(tx + 3 * dx, ty + 3 * dy, tz - 1, "jungle_leaves")
        for dx, dy in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            s.set(tx + dx, ty + dy, tz, "jungle_leaves", "slab")
        s.set(tx + 1, ty + 1, tz - 1, "jungle_wood", "cube_small")  # coconuts
    elif kind == "bamboo":
        ox, oy = s.origin
        stalk = {f: np.tile(parse("#7a9a2a"), (16, 3, 1)) for f in FACES}
        for f in ("front", "back", "right", "left"):
            stalk[f] = stalk[f].copy()
            stalk[f][::5] = parse("#5a7a1a")
        leaf = {f: np.tile(parse("#5a8a22"), (4, 4, 1)) for f in FACES}
        for k in range(5 + seed % 3):
            bx, by = rng.uniform(0.3, 2.7, 2)
            hh = h * B * rng.uniform(0.7, 1.05)
            x, y = (bx - ox) * B, (by - oy) * B
            s.extras.append(cuboid((x - 1.5, y - 1.5, 0), (3, 3, hh), stalk))
            for z in np.arange(hh * 0.45, hh, 9):
                s.extras.append(cuboid((x + rng.uniform(-6, 2), y + rng.uniform(-6, 2), z), (6, 6, 1.5), leaf))
    elif kind == "dead":
        s.fill(c, c, 0, c, c, max(2, h - 2), "oak_log")
        for z in range(2, h - 1, 2):
            d = [(1, 0), (0, 1), (-1, 0), (0, -1)][rng.integers(0, 4)]
            s.set(c + d[0], c + d[1], z, "oak_log", "post")
            s.set(c + 2 * d[0], c + 2 * d[1], z + 1, "oak_log", "post")
    elif kind == "jungle":
        s.fill(c, c, 0, c, c, h - 2, "jungle_log")
        for z in (h - 3, h - 2):
            _blob(s, c, c, z, 2, "jungle_leaves", rng, 0.8)
        _blob(s, c, c, h - 1, 1, "jungle_leaves", rng, 0.9)
        for z in range(1, h - 3):
            if rng.random() < 0.5:
                s.set(c + 1, c, z, "jungle_leaves", "pane_y")  # vines
    else:
        log, leaf = {"oak": ("oak_log", "oak_leaves"), "birch": ("birch_log", "birch_leaves"),
                     "dark_oak": ("dark_oak_log", "dark_oak_leaves"), "acacia": ("acacia_log", "acacia_leaves"),
                     "cherry": ("cherry_log", "cherry_leaves"),
                     "azalea": ("oak_log", "flowering_azalea_leaves")}[kind]
        trunk = max(1, h - 3)
        s.fill(c, c, 0, c, c, trunk, log)
        if kind == "acacia":
            s.set(c + 1, c, trunk, log)
            _blob(s, c + 1, c, trunk + 1, 2, leaf, rng, 0.8)
            _blob(s, c + 1, c, trunk + 2, 1, leaf, rng, 0.9)
        else:
            wide = 2 if h >= 6 or kind == "dark_oak" else 1
            _blob(s, c, c, trunk - 1, wide, leaf, rng, 0.8)
            _blob(s, c, c, trunk, wide, leaf, rng, 0.85)
            _blob(s, c, c, trunk + 1, 1, leaf, rng, 0.95)
            s.set(c, c, trunk + 2, leaf)
            if rng.random() < 0.5:
                s.set(c + 1, c, trunk + 2, leaf)
        if kind == "dark_oak":
            s.set(c + 1, c, 0, log)
            s.set(c, c + 1, 0, log)
    if part != "all":
        cut = s.height() // 2
        keep = (lambda z: z < cut) if part == "trunk" else (lambda z: z >= cut)
        s.blocks = {k: v for k, v in s.blocks.items() if keep(k[2])}
        s.extras = [b for b in s.extras if keep(b.lo[2] / B)]
    return s


def stump(kind: str = "oak", variant: int = 0, felled: bool = True) -> V.Structure:
    """A chopped tree: a short stump and, while there is wood left, the felled trunk beside it."""
    rng = np.random.default_rng(variant + 17)
    log = {"oak": "oak_log", "spruce": "spruce_log", "palm": "jungle_log", "jungle": "jungle_log",
           "bamboo": "bamboo_block", "birch": "birch_log"}.get(kind, "oak_log")
    s = _s("stump")
    s.set(1, 1, 0, log, "slab")
    if felled:
        axis = variant % 2
        for k in range(2 + variant % 2):
            s.set(1 + k if axis == 0 else 0, 0 if axis == 0 else 1 + k, 0, log.replace("_log", "_wood")
                  if "_log" in log else log)
        s.set(2, 2, 0, "oak_leaves" if kind != "spruce" else "spruce_leaves", "slab")
    if rng.random() < 0.5:
        s.set(0, 2, 0, "oak_leaves", "carpet")
    return s


# --------------------------------------------------------------------------- resources

def ore_pile(kind: str, size_px: float = 90.0, variant: int = 0) -> V.Structure:
    """A gold or stone mine: a heap of ore blocks about `size_px` pixels wide."""
    rng = np.random.default_rng(variant * 31 + (1 if kind == "gold" else 2))
    n = int(np.clip(round(size_px / 34.0), 2, 4))
    s = _s(f"{kind}_mine", n)
    if kind == "gold":
        mix = [("gold_ore", 0.5), ("raw_gold_block", 0.2), ("gold_block", 0.08), ("stone", 0.22)]
    else:
        mix = [("stone", 0.35), ("cobblestone", 0.25), ("andesite", 0.2), ("gravel", 0.05), ("diorite", 0.15)]
    names, probs = zip(*mix)
    probs = np.array(probs) / sum(probs)
    for x in range(n):
        for y in range(n):
            h = 1 + int(rng.random() < 0.7) + int(rng.random() < 0.35 and 0 < x < n and 0 < y < n)
            if (x in (0, n - 1) and y in (0, n - 1)) and rng.random() < 0.5:
                h = max(0, h - 1)
            for z in range(h):
                s.set(x, y, z, names[rng.choice(len(names), p=probs)],
                      "full" if z < h - 1 or rng.random() < 0.6 else "slab")
    if kind == "gold":  # a few nuggets on top
        s.set(n // 2, n // 2, s.height(), "gold_block", "cube_small")
    return s


def berry_bush(variant: int = 0, berries: float = 1.0) -> V.Structure:
    """A sweet berry bush with red berries."""
    rng = np.random.default_rng(variant + 5)
    s = _s("berry_bush", 2)
    for x in range(2):
        for y in range(2):
            if rng.random() < 0.85 or (x, y) == (1, 1):
                s.set(x, y, 0, "sweet_berry_leaves")
    if rng.random() < 0.6:
        s.set(rng.integers(0, 2), rng.integers(0, 2), 1, "sweet_berry_leaves", "slab")
    ox, oy = s.origin
    red = {f: np.tile(parse("#c8102e"), (2, 2, 1)) for f in FACES}
    for _ in range(int(14 * berries)):
        x, y = rng.uniform(0, 2, 2)
        z = rng.uniform(2, 15)
        side = rng.integers(0, 2)
        px = ((x - ox) * B, 2 * B - oy * B + 0.2) if side else (2 * B - ox * B + 0.2, (y - oy) * B)
        if side:
            s.extras.append(cuboid((px[0], px[1], z), (2, 1, 2), red))
        else:
            s.extras.append(cuboid((px[0], px[1], z), (1, 2, 2), red))
    return s


def boulder(variant: int = 0, size_px: float = 60.0, stone: str = None) -> V.Structure:
    rng = np.random.default_rng(variant + 40)
    n = int(np.clip(round(size_px / 34.0), 1, 3))
    s = _s("rock", n)
    kinds = [stone] if stone else ["stone", "andesite", "cobblestone", "granite", "mossy_cobblestone", "diorite"]
    main = kinds[variant % len(kinds)]
    for x in range(n):
        for y in range(n):
            if rng.random() < 0.8 or n == 1:
                s.set(x, y, 0, main)
                if rng.random() < 0.4:
                    s.set(x, y, 1, main, "slab")
    return s


FLOWERS = {  # name: (petals, centre)
    "poppy": ("#d1161f", "#2a1a10"), "dandelion": ("#f5d428", "#d9a51a"), "cornflower": ("#4a6ad9", "#2a3a8a"),
    "allium": ("#b86ad9", "#8a3ab0"), "oxeye": ("#f2f2f2", "#e8c228"), "tulip": ("#f07a28", "#b04a18"),
}


def flower_sprite(name: str) -> np.ndarray:
    petal, centre = FLOWERS[name]
    tex = np.zeros((16, 16, 5), np.float32)
    tex[7:16, 7:9] = parse("#3a7a2a")
    tex[10, 5:7] = parse("#3a7a2a")
    tex[12, 9:11] = parse("#3a7a2a")
    for (y, x) in ((3, 6), (3, 9), (2, 7), (2, 8), (4, 7), (4, 8), (5, 6), (5, 9), (6, 7), (6, 8)):
        tex[y, x] = parse(petal)
    tex[4:6, 7:9] = parse(centre)
    return tex


def grass_sprite(fern: bool = False) -> np.ndarray:
    tex = np.zeros((16, 16, 5), np.float32)
    rng = np.random.default_rng(3 if fern else 4)
    col = "#4a8a2a" if not fern else "#3a7a2a"
    for c in range(0, 16, 2 if not fern else 3):
        top = rng.integers(3, 9)
        tex[top:, c] = parse(col)
        if fern:
            for y in range(top, 16, 3):
                tex[y, max(0, c - 1):c + 2] = parse(col)
    return tex


def plants(variant: int = 0, flowers: bool = False, count: int = 5) -> V.Structure:
    """A patch of grass, ferns and flowers."""
    rng = np.random.default_rng(variant + 60)
    s = _s("plants", 3)
    names = list(FLOWERS)
    for k in range(count):
        x, y = rng.uniform(0.3, 2.7, 2)
        if flowers or rng.random() < 0.3:
            sprite = flower_sprite(names[(variant + k) % len(names)])
        else:
            sprite = grass_sprite(fern=rng.random() < 0.4)
        s.plant(x, y, 0, sprite, 12)
    if not flowers and variant % 3 == 0:
        s.set(1, 1, 0, "azalea_leaves" if variant % 2 else "oak_leaves")
    return s


def cactus(variant: int = 0) -> V.Structure:
    rng = np.random.default_rng(variant + 70)
    s = _s("cactus", 1)
    h = 1 + variant % 3
    s.fill(0, 0, 0, 0, 0, h - 1, "cactus")
    if rng.random() < 0.3:
        s.plant(0.5, 0.5, h, flower_sprite("poppy"), 8)
    return s


def haystack(variant: int = 0) -> V.Structure:
    s = _s("haystack", 2)
    s.fill(0, 0, 0, 1, 1, 0, "hay")
    s.set(variant % 2, (variant // 2) % 2, 1, "hay")
    if variant == 2:
        s.set(1, 0, 1, "hay")
    return s
