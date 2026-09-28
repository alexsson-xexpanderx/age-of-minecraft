"""Block structures: Minecraft builds on an integer grid, turned into box models.

A `Structure` stores blocks at integer (x, y, z) positions (16 Minecraft
pixels per block, z up) with a shape: full cubes, slabs, stairs, fences,
walls, panes, carpets, crossed plants... `part()` turns it into boxes for
the renderer, skipping blocks buried inside solid mass.

Buildings are drawn with their +x and +y walls facing the camera (screen
south-west and south-east), so decorations go on those two sides.
`origin` is the block coordinate that lands on the sprite's hotspot, i.e.
the centre of the building's footprint on the ground.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from .blocks import BlockType, blocks
from .geometry import Box, Part, cuboid
from .textures import FACES, PC, Painter, parse

BLOCK = 16
TILE = 96 / (1.5 * 2 ** 0.5)  # one AoE2 tile in Minecraft pixels (about 2.83 blocks)
BUILDING_HEADING = -45.0  # model +x -> screen south-west, +y -> screen south-east

FULL = ((0, 0, 0), (16, 16, 16))
SIDES = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}


def tiles_to_blocks(tiles: float) -> float:
    return tiles * TILE / BLOCK


# --------------------------------------------------------------------------- shapes

def _stair(direction: str, upside_down: bool = False) -> list:
    """Low step toward `direction`; the tall back is on the opposite side."""
    low, high = ((0, 0, 0), (16, 16, 8)), None
    backs = {"+y": ((0, 0, 8), (16, 8, 16)), "-y": ((0, 8, 8), (16, 16, 16)),
             "+x": ((0, 0, 8), (8, 16, 16)), "-x": ((8, 0, 8), (16, 16, 16))}
    high = backs[direction]
    if upside_down:
        low = ((0, 0, 8), (16, 16, 16))
        (x0, y0, _), (x1, y1, _) = high
        high = ((x0, y0, 0), (x1, y1, 8))
    return [low, high]


def shape_boxes(shape: str, neighbours: Callable[[str], bool] = lambda d: False) -> list:
    """Sub-boxes of a block shape in 0..16 pixels; `neighbours(dir)` says if a connectable block is there."""
    if shape == "full":
        return [FULL]
    if shape == "slab":
        return [((0, 0, 0), (16, 16, 8))]
    if shape == "top_slab":
        return [((0, 0, 8), (16, 16, 16))]
    if shape == "carpet":
        return [((0, 0, 0), (16, 16, 1))]
    if shape == "layer":
        return [((0, 0, 0), (16, 16, 3))]
    if shape.startswith("ustair_"):
        return _stair(shape[7:], upside_down=True)
    if shape.startswith("stair_"):
        return _stair(shape[6:])
    if shape in ("pane_x", "pane_y"):  # thin pane along the named axis
        return [((0, 7, 0), (16, 9, 16))] if shape == "pane_x" else [((7, 0, 0), (9, 16, 16))]
    if shape in ("panel_x", "panel_y"):  # door leaf, 3 px thick
        return [((0, 6.5, 0), (16, 9.5, 16))] if shape == "panel_x" else [((6.5, 0, 0), (9.5, 16, 16))]
    if shape == "post":
        return [((6, 6, 0), (10, 10, 16))]
    if shape == "thin_post":
        return [((7, 7, 0), (9, 9, 16))]
    if shape == "fence":
        out = [((6, 6, 0), (10, 10, 16))]
        arms = {"+x": ((10, 7, 0), (16, 9, 0)), "-x": ((0, 7, 0), (6, 9, 0)),
                "+y": ((7, 10, 0), (9, 16, 0)), "-y": ((7, 0, 0), (9, 6, 0))}
        for d, ((x0, y0, _), (x1, y1, _)) in arms.items():
            if neighbours(d):
                out += [((x0, y0, 6), (x1, y1, 9)), ((x0, y0, 12), (x1, y1, 15))]
        return out
    if shape == "wall":  # cobblestone wall: a thick post with lower connecting walls
        out = [((4, 4, 0), (12, 12, 16))]
        arms = {"+x": ((12, 5, 0), (16, 11, 14)), "-x": ((0, 5, 0), (4, 11, 14)),
                "+y": ((5, 12, 0), (11, 16, 14)), "-y": ((5, 0, 0), (11, 4, 14))}
        out += [arms[d] for d in arms if neighbours(d)]
        return out
    if shape == "bars":  # iron bars / glass pane that connect to neighbours
        out = [((7, 7, 0), (9, 9, 16))]
        arms = {"+x": ((9, 7, 0), (16, 9, 16)), "-x": ((0, 7, 0), (7, 9, 16)),
                "+y": ((7, 9, 0), (9, 16, 16)), "-y": ((7, 0, 0), (9, 7, 16))}
        out += [arms[d] for d in arms if neighbours(d)]
        return out
    if shape == "torch":
        return [((7, 7, 0), (9, 9, 10))]
    if shape == "lantern":
        return [((5, 5, 0), (11, 11, 7)), ((6, 6, 7), (10, 10, 9))]
    if shape == "cube_small":  # e.g. a flower pot, a skull
        return [((4, 4, 0), (12, 12, 8))]
    raise ValueError(shape)


CONNECTS = {"fence", "wall", "bars", "full", "slab", "top_slab", "post"}


def crop_faces(faces: dict[str, np.ndarray], lo, hi) -> dict[str, np.ndarray]:
    """The part of each 16x16 face texture that a sub-block box (in 0..16 pixels) shows."""
    (x0, y0, z0), (x1, y1, z1) = (np.floor(np.asarray(lo)).astype(int), np.ceil(np.asarray(hi)).astype(int))
    x0, y0, z0 = (max(0, v) for v in (x0, y0, z0))
    x1, y1, z1 = (min(16, v) for v in (x1, y1, z1))
    rows_z = slice(16 - z1, 16 - z0)
    windows = {
        "front": (rows_z, slice(16 - x1, 16 - x0)),
        "back": (rows_z, slice(x0, x1)),
        "right": (rows_z, slice(y0, y1)),
        "left": (rows_z, slice(16 - y1, 16 - y0)),
        "top": (slice(y0, y1), slice(16 - x1, 16 - x0)),
        "bottom": (slice(16 - y1, 16 - y0), slice(16 - x1, 16 - x0)),
    }
    out = {}
    for f, (rs, cs) in windows.items():
        t = faces[f][rs, cs]
        out[f] = t if t.size else faces[f][:1, :1]
    return out


# --------------------------------------------------------------------------- the structure

@dataclass
class Structure:
    name: str
    origin: tuple[float, float] = (0.0, 0.0)
    blocks: dict[tuple[int, int, int], tuple[str, str]] = field(default_factory=dict)
    extras: list[Box] = field(default_factory=list)  # hand-placed boxes, in pixels relative to the origin
    parts: list[Part] = field(default_factory=list)  # rotated or animated sub-models, same frame
    plants: list[tuple[tuple[float, float, float], np.ndarray, float]] = field(default_factory=list)

    # ---- editing
    def set(self, x: int, y: int, z: int, block: str, shape: str = "full") -> None:
        self.blocks[(int(x), int(y), int(z))] = (block, shape)

    def get(self, x: int, y: int, z: int) -> Optional[tuple[str, str]]:
        return self.blocks.get((int(x), int(y), int(z)))

    def clear(self, x: int, y: int, z: int) -> None:
        self.blocks.pop((int(x), int(y), int(z)), None)

    def fill(self, x0, y0, z0, x1, y1, z1, block: str, shape: str = "full") -> None:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for z in range(min(z0, z1), max(z0, z1) + 1):
                    self.set(x, y, z, block, shape)

    def carve(self, x0, y0, z0, x1, y1, z1) -> None:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for z in range(min(z0, z1), max(z0, z1) + 1):
                    self.clear(x, y, z)

    def ring(self, x0, y0, x1, y1, z0, z1, block: str, shape: str = "full") -> None:
        """Hollow walls around a rectangle."""
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y0, z, block, shape)
                self.set(x, y1, z, block, shape)
            for y in range(y0, y1 + 1):
                self.set(x0, y, z, block, shape)
                self.set(x1, y, z, block, shape)

    def cylinder(self, cx: float, cy: float, r: float, z0: int, z1: int, block: str, hollow: bool = False) -> None:
        for x in range(int(np.floor(cx - r)) - 1, int(np.ceil(cx + r)) + 2):
            for y in range(int(np.floor(cy - r)) - 1, int(np.ceil(cy + r)) + 2):
                d = np.hypot(x + 0.5 - cx, y + 0.5 - cy)
                if d <= r and (not hollow or d > r - 1.2):
                    for z in range(z0, z1 + 1):
                        self.set(x, y, z, block)

    def dome(self, cx: float, cy: float, z0: int, r: float, block: str, squash: float = 1.0) -> None:
        for x in range(int(np.floor(cx - r)) - 1, int(np.ceil(cx + r)) + 2):
            for y in range(int(np.floor(cy - r)) - 1, int(np.ceil(cy + r)) + 2):
                for z in range(0, int(np.ceil(r * squash)) + 1):
                    d = np.sqrt((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 + ((z + 0.5) / squash) ** 2)
                    if d <= r:
                        self.set(x, y, z0 + z, block)

    def cone(self, cx: float, cy: float, z0: int, r: float, block: str, step: float = 1.0) -> None:
        z = z0
        while r > 0.4:
            self.cylinder(cx, cy, r, z, z, block)
            r -= step
            z += 1

    def shift(self, dx: int, dy: int, dz: int = 0) -> "Structure":
        self.blocks = {(x + dx, y + dy, z + dz): v for (x, y, z), v in self.blocks.items()}
        return self

    def merge(self, other: "Structure", dx: int = 0, dy: int = 0, dz: int = 0) -> None:
        for (x, y, z), v in other.blocks.items():
            self.blocks[(x + dx, y + dy, z + dz)] = v
        off = np.array([dx, dy, dz], float) * BLOCK
        for b in other.extras:
            self.extras.append(Box(b.lo + off, b.hi + off, b.faces))

    def plant(self, x: float, y: float, z: float, sprite: np.ndarray, size: float = 16.0) -> None:
        """A crossed-plane plant (flowers, saplings, wheat), `sprite` is an (h, w, 5) texture; x/y/z in blocks."""
        self.plants.append(((x, y, z), sprite, size))

    def height(self) -> int:
        return max((z for _, _, z in self.blocks), default=0) + 1

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        pts = np.array(list(self.blocks.keys()), float)
        return pts.min(axis=0), pts.max(axis=0) + 1

    # ---- turning into boxes
    def _opaque_full(self, key, types: dict[str, BlockType]) -> bool:
        v = self.blocks.get(key)
        return v is not None and v[1] == "full" and types[v[0]].opaque

    def part(self, types: dict[str, BlockType] = None) -> Part:
        types = types or blocks()
        ox, oy = self.origin
        boxes = []
        for (x, y, z), (name, shape) in self.blocks.items():
            if shape == "full" and all(self._opaque_full((x + dx, y + dy, z + dz), types)
                                       for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                                                          (0, 0, 1), (0, 0, -1))):
                continue  # buried: never seen and never casts a shadow of its own

            def neighbour(d, x=x, y=y, z=z):
                dx, dy = SIDES[d]
                v = self.blocks.get((x + dx, y + dy, z))
                return v is not None and v[1] in CONNECTS

            faces = types[name].faces
            base = np.array([(x - ox) * BLOCK, (y - oy) * BLOCK, z * BLOCK], float)
            for lo, hi in shape_boxes(shape, neighbour):
                lo, hi = np.asarray(lo, float), np.asarray(hi, float)
                boxes.append(cuboid(base + lo, hi - lo, crop_faces(faces, lo, hi)))
        root = Part(self.name, boxes=boxes + list(self.extras))
        for (x, y, z), sprite, size in self.plants:
            root.add(*cross_plant(f"{self.name}_plant", ((x - ox) * BLOCK, (y - oy) * BLOCK, z * BLOCK),
                                  sprite, size))
        for p in self.parts:
            root.add(p)
        return root


def cross_plant(name: str, at, sprite: np.ndarray, size: float = 16.0) -> list[Part]:
    """Two crossed quads, like Minecraft flowers and crops; `at` is the base centre in pixels."""
    h, w = sprite.shape[:2]
    height = size * h / w
    faces = {f: sprite for f in FACES}
    faces["top"] = faces["bottom"] = np.zeros((1, 1, 5), np.float32)
    x, y, z = at
    quad = cuboid((x - size / 2, y - 0.25, z), (size, 0.5, height), faces)
    return [Part(f"{name}_a", pivot=(x, y, z), rot=(0, 0, 45), boxes=[quad]),
            Part(f"{name}_b", pivot=(x, y, z), rot=(0, 0, -45), boxes=[quad])]


# --------------------------------------------------------------------------- building helpers

def gable_roof(s: Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str, gable: str,
               ridge: str = None, axis: str = "x", overhang: int = 1) -> int:
    """Stair roof with the ridge along `axis`; returns the level above the ridge."""
    if axis == "x":
        lo, hi, level = y0 - overhang, y1 + overhang, z
        while hi - lo >= 1:
            for x in range(x0 - overhang, x1 + overhang + 1):
                s.set(x, lo, level, roof, "stair_-y")
                s.set(x, hi, level, roof, "stair_+y")
            if hi - lo >= 2:
                s.fill(x0, lo + 1, level, x1, hi - 1, level, gable)
            lo, hi, level = lo + 1, hi - 1, level + 1
        if lo == hi:
            for x in range(x0 - overhang, x1 + overhang + 1):
                s.set(x, lo, level, ridge or roof, "slab")
            level += 1
        return level
    lo, hi, level = x0 - overhang, x1 + overhang, z
    while hi - lo >= 1:
        for y in range(y0 - overhang, y1 + overhang + 1):
            s.set(lo, y, level, roof, "stair_-x")
            s.set(hi, y, level, roof, "stair_+x")
        if hi - lo >= 2:
            s.fill(lo + 1, y0, level, hi - 1, y1, level, gable)
        lo, hi, level = lo + 1, hi - 1, level + 1
    if lo == hi:
        for y in range(y0 - overhang, y1 + overhang + 1):
            s.set(lo, y, level, ridge or roof, "slab")
        level += 1
    return level


def hip_roof(s: Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str, fill: str = None,
             overhang: int = 1, cap: str = None) -> int:
    """Pyramid/hip roof of stairs on all four sides; returns the level above the top."""
    x0, x1, y0, y1, level = x0 - overhang, x1 + overhang, y0 - overhang, y1 + overhang, z
    while x1 - x0 >= 1 and y1 - y0 >= 1:
        for x in range(x0, x1 + 1):
            s.set(x, y0, level, roof, "stair_-y")
            s.set(x, y1, level, roof, "stair_+y")
        for y in range(y0 + 1, y1):
            s.set(x0, y, level, roof, "stair_-x")
            s.set(x1, y, level, roof, "stair_+x")
        if x1 - x0 >= 2 and y1 - y0 >= 2:
            s.fill(x0 + 1, y0 + 1, level, x1 - 1, y1 - 1, level, fill or roof)
        x0, x1, y0, y1, level = x0 + 1, x1 - 1, y0 + 1, y1 - 1, level + 1
    if x1 >= x0 and y1 >= y0:
        s.fill(x0, y0, level, x1, y1, level, cap or roof, "slab")
        level += 1
    return level


def pagoda_roof(s: Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str, trim: str = None) -> None:
    """One flared eave ring: a stair skirt with upturned corners (Asian style)."""
    ox0, ox1, oy0, oy1 = x0 - 1, x1 + 1, y0 - 1, y1 + 1
    for x in range(ox0, ox1 + 1):
        s.set(x, oy0, z, roof, "stair_-y")
        s.set(x, oy1, z, roof, "stair_+y")
    for y in range(oy0 + 1, oy1):
        s.set(ox0, y, z, roof, "stair_-x")
        s.set(ox1, y, z, roof, "stair_+x")
    for x, y in ((ox0, oy0), (ox0, oy1), (ox1, oy0), (ox1, oy1)):  # upturned eave corners
        s.set(x, y, z, roof)
        s.set(x, y, z + 1, trim or roof, "slab")
    s.fill(x0, y0, z, x1, y1, z, roof, "slab")


def crenellate(s: Structure, x0: int, x1: int, y0: int, y1: int, z: int, block: str) -> None:
    """Battlements on top of a wall ring: every other block along the edge."""
    for x in range(x0, x1 + 1):
        if (x - x0) % 2 == 0:
            s.set(x, y0, z, block)
            s.set(x, y1, z, block)
    for y in range(y0, y1 + 1):
        if (y - y0) % 2 == 0:
            s.set(x0, y, z, block)
            s.set(x1, y, z, block)


def door(s: Structure, x: int, y: int, z: int, facing: str, wood: str = "oak", double: bool = False) -> None:
    """A door opening in a +x or +y wall (the camera-facing sides)."""
    shape = "panel_x" if facing == "+y" else "panel_y"
    xs = [(x, y), (x + 1, y)] if (double and facing == "+y") else [(x, y), (x, y + 1)] if double else [(x, y)]
    for xx, yy in xs:
        s.set(xx, yy, z, f"door_{wood}_lower", shape)
        s.set(xx, yy, z + 1, f"door_{wood}_upper", shape)


def window(s: Structure, x: int, y: int, z: int, facing: str, glass: str = "glass") -> None:
    s.set(x, y, z, glass, "pane_x" if facing == "+y" else "pane_y")


# --------------------------------------------------------------------------- decorations as boxes

def solid(colour) -> dict[str, np.ndarray]:
    t = parse(colour)[None, None].copy()
    return {f: t for f in FACES}


def banner(p: Painter, at, facing: str = "+y", width: float = 12, height: float = 22,
           pattern: str = "cross") -> list[Box]:
    """A team-coloured wall banner hanging from a stick; `at` is the top centre, in pixels."""
    x, y, z = at
    rows = ["DDDDDDDDDDDD"] + ["PPPPPPPPPPPP"] * 3
    if pattern == "cross":
        rows += ["PPPPPDDPPPPP", "PPPPDLLDPPPP", "PPPDLLLLDPPP", "PPPPDLLDPPPP", "PPPPPDDPPPPP"]
    elif pattern == "stripe":
        rows += ["PPPPPPPPPPPP", "LLLLLLLLLLLL", "LLLLLLLLLLLL", "PPPPPPPPPPPP", "PPPPPPPPPPPP"]
    else:
        rows += ["PPPPPPPPPPPP"] * 5
    rows += ["PPPPPPPPPPPP"] * 11 + ["PDPPDPPDPPDP", "DPDDPDDPDDPD"]
    cloth = p.grid(rows, {"P": PC(0.6), "D": PC(0.35), "L": PC(0.85)})
    stick = solid("#6b4a2a")
    faces = {f: cloth if f in ("front", "back", "right", "left") else cloth[:1] for f in FACES}
    if facing == "+y":
        return [cuboid((x - width / 2 - 1, y, z - 1.5), (width + 2, 1.5, 1.5), stick),
                cuboid((x - width / 2, y, z - 1.5 - height), (width, 1, height), faces)]
    return [cuboid((x, y - width / 2 - 1, z - 1.5), (1.5, width + 2, 1.5), stick),
            cuboid((x, y - width / 2, z - 1.5 - height), (1, width, height), faces)]


def flag_pole(p: Painter, at, height: float = 40, cloth_w: float = 16, cloth_h: float = 10,
              wave: float = 0.0) -> list[Box]:
    """A pole with a team-coloured flag; `at` is the pole foot in pixels; `wave` 0..1 animates."""
    x, y, z = at
    out = [cuboid((x - 1, y - 1, z), (2, 2, height), solid("#5a4028"))]
    cloth = p.grid(["PPPPPPPP", "PLLPPLLP", "PPPPPPPP", "PPPDDPPP"], {"P": PC(0.6), "L": PC(0.85), "D": PC(0.35)})
    segs = 4
    for i in range(segs):
        dz = np.sin(wave * 2 * np.pi + i * 1.3) * 1.2 * (i / segs)
        faces = {f: cloth for f in FACES}
        out.append(cuboid((x + 1 + i * cloth_w / segs, y - 0.5, z + height - cloth_h - 1 + dz),
                          (cloth_w / segs, 1, cloth_h), faces))
    return out


def torch_boxes(at, flame: float = 0.0) -> list[Box]:
    x, y, z = at
    f = 0.5 + 0.5 * np.sin(flame * 2 * np.pi)
    fire = solid("#ffd24a" if f > 0.5 else "#ffb02a")
    return [cuboid((x - 1, y - 1, z), (2, 2, 10), solid("#6b4a2a")),
            cuboid((x - 1.5, y - 1.5, z + 10), (3, 3, 2 + f), fire)]


def lantern_boxes(at) -> list[Box]:
    x, y, z = at
    return [cuboid((x - 3, y - 3, z), (6, 6, 7), {**solid("#3a3a3a"), "front": _lantern_face(),
                                                  "right": _lantern_face(), "left": _lantern_face(),
                                                  "back": _lantern_face()}),
            cuboid((x - 2, y - 2, z + 7), (4, 4, 2), solid("#2a2a2a"))]


def _lantern_face() -> np.ndarray:
    t = np.tile(parse("#3a3a3a"), (7, 6, 1))
    t[2:6, 1:5] = parse("#ffc45a")
    return t


def bell_boxes(at) -> list[Box]:
    x, y, z = at
    gold = {f: np.tile(parse("#e8b923"), (8, 8, 1)) for f in FACES}
    return [cuboid((x - 3, y - 3, z - 7), (6, 6, 7), gold), cuboid((x - 4, y - 4, z - 8), (8, 8, 2), gold)]


# --------------------------------------------------------------------------- door and misc textures

def register_extras(types: dict[str, BlockType]) -> dict[str, BlockType]:
    """Door textures for every wood (added lazily to the block registry)."""
    from .blocks import WOODS, planks
    p = Painter("doors")
    for wood, (plank, _, _) in list(WOODS.items()) + [("iron", ("#c8c8c8", "", ""))]:
        if f"door_{wood}_lower" in types:
            continue
        low = planks(p, plank) if wood != "iron" else p.fill(16, 16, "#c8c8c8", 0.03)
        up = low.copy()
        edge = parse("#4a3a28") if wood != "iron" else parse("#8a8a8a")
        low[:, 0] = low[:, -1] = up[:, 0] = up[:, -1] = edge
        up[3:9, 3:7] = parse("#2b2b2b")
        up[3:9, 9:13] = parse("#2b2b2b")
        low[5:7, 11:13] = parse("#b0b0b0")
        types[f"door_{wood}_lower"] = BlockType.uniform(low)
        types[f"door_{wood}_upper"] = BlockType.uniform(up)
    return types


def all_blocks() -> dict[str, BlockType]:
    return register_extras(blocks())
