"""Buildings: block-built structures at the same scale as the units.

A unit is 2 blocks tall (32 Minecraft pixels), just like in Minecraft, and
one AoE2 tile works out to about 2.8 blocks at our render scale, so a 2x2
tile House is a 5x5 block cottage and a 4x4 Town Center an 11x11 hall.

Blocks are placed on an integer grid (x, y, z) with 16 pixels per block.
Buildings are drawn from one fixed angle, with their +x and +y walls facing
the camera (south-west and south-east on screen).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geometry import Part, cuboid
from .textures import FACES, PC, Painter, parse

BLOCK = 16
BUILDING_HEADING = -45.0  # puts the model's +x wall at screen south-west, +y at south-east


# --------------------------------------------------------------------------- block textures

def _planks(p: Painter, light: str, dark: str, seam: str) -> np.ndarray:
    tex = p.fill(16, 16, light, 0.05)
    for r in (3, 7, 11, 15):
        tex[r] = parse(dark)
    for r0, c in ((0, 5), (4, 12), (8, 2), (12, 9)):  # staggered plank ends
        tex[r0:r0 + 3, c] = parse(seam)
    return p.jitter(tex, 0.03)


def _log_side(p: Painter, bark: str, groove: str) -> np.ndarray:
    tex = p.fill(16, 16, bark, 0.06)
    for c in (2, 6, 7, 11, 14):
        tex[:, c] = parse(groove)
    return p.jitter(tex, 0.04)


def _log_top(p: Painter, bark: str, ring: str, core: str) -> np.ndarray:
    yy, xx = np.mgrid[0:16, 0:16]
    d = np.maximum(np.abs(xx - 7.5), np.abs(yy - 7.5))
    tex = p.fill(16, 16, core, 0.04)
    tex[(d > 2) & (d < 3.5)] = parse(ring)
    tex[(d > 4.5) & (d < 6)] = parse(ring)
    tex[d >= 7] = parse(bark)
    return tex


def _stones(p: Painter, base: str, light: str, mortar: str) -> np.ndarray:
    """Cobblestone: random rounded stones in dark mortar."""
    tex = p.fill(16, 16, mortar, 0.05)
    yy, xx = np.mgrid[0:16, 0:16]
    for _ in range(9):
        cx, cy = p.rng.uniform(0, 16, 2)
        rx, ry = p.rng.uniform(2.2, 4.2, 2)
        m = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 < 1
        tex[m] = parse(base)
        tex[m & (yy < cy - ry * 0.3)] = parse(light)
    return p.jitter(tex, 0.06)


def _bricks(p: Painter, face: str, mortar: str, light: str) -> np.ndarray:
    tex = p.fill(16, 16, face, 0.05)
    for r in (0, 8):
        tex[r] = parse(mortar)
    tex[1:8, 0] = parse(mortar)
    tex[9:16, 8] = parse(mortar)
    tex[1, 1:8] = parse(light)
    tex[9, 9:16] = parse(light)
    return tex


def _glass(p: Painter) -> np.ndarray:
    tex = p.fill(16, 16, "#9fc3cf", 0.03)
    for i in range(3, 8):
        tex[i, 11 - i] = parse("#e4f3f7")
        tex[i + 5, 14 - i] = parse("#e4f3f7")
    tex[0, :] = tex[-1, :] = tex[:, 0] = tex[:, -1] = parse("#6f5a3a")  # frame
    return tex


def _door(p: Painter, top: bool) -> np.ndarray:
    tex = _planks(p, "#9c7a45", "#7a5d31", "#6a5029")
    tex[:, 0] = tex[:, -1] = parse("#5c4524")
    if top:
        tex[3:9, 3:7] = parse("#2b2b2b")  # small windows
        tex[3:9, 9:13] = parse("#2b2b2b")
    else:
        tex[5:7, 11:13] = parse("#b0b0b0")  # handle
    return tex


def _wool(p: Painter, spec) -> np.ndarray:
    tex = p.fill(16, 16, spec, 0.06)
    mask = p.rng.random((16, 16)) < 0.25
    tex[mask, :3] *= 0.9
    return tex


@dataclass
class BlockType:
    faces: dict[str, np.ndarray]

    @classmethod
    def uniform(cls, tex: np.ndarray) -> "BlockType":
        return cls({f: tex for f in FACES})

    @classmethod
    def pillar(cls, side: np.ndarray, end: np.ndarray) -> "BlockType":
        return cls({"front": side, "back": side, "right": side, "left": side, "top": end, "bottom": end})


def block_types(seed: str = "blocks") -> dict[str, BlockType]:
    p = Painter(seed)
    oak = _planks(p, "#b18d54", "#8a6a3a", "#7a5c30")
    spruce = _planks(p, "#7a5a35", "#5c4225", "#4d371e")
    dark_oak = _planks(p, "#4f3720", "#3a2715", "#301f10")
    return {
        "oak": BlockType.uniform(oak),
        "spruce": BlockType.uniform(spruce),
        "dark_oak": BlockType.uniform(dark_oak),
        "log": BlockType.pillar(_log_side(p, "#6b5132", "#4e3a22"), _log_top(p, "#6b5132", "#9c7c4c", "#b8955e")),
        "cobble": BlockType.uniform(_stones(p, "#8a8a8a", "#a8a8a8", "#555555")),
        "stone_bricks": BlockType.uniform(_bricks(p, "#8c8c8c", "#5f5f5f", "#a5a5a5")),
        "glass": BlockType.uniform(_glass(p)),
        "door_lower": BlockType.uniform(_door(p, top=False)),
        "door_upper": BlockType.uniform(_door(p, top=True)),
        "wool": BlockType.uniform(_wool(p, PC(0.6))),
        "white_wool": BlockType.uniform(_wool(p, "#e9ecec")),
        "hay": BlockType.pillar(p.speckle("#c8a43a", ("#a88422", 0.3), ("#e0c257", 0.15))(16, 16),
                                p.speckle("#b89530", ("#8e7020", 0.3))(16, 16)),
    }


# --------------------------------------------------------------------------- shapes

def _crop(faces: dict[str, np.ndarray], lo, hi) -> dict[str, np.ndarray]:
    """Cut the part of each face texture that a sub-block box (in 0..16 pixels) shows."""
    (x0, y0, z0), (x1, y1, z1) = (np.round(lo).astype(int), np.round(hi).astype(int))
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


# Sub-boxes of each shape, in pixels inside the 16^3 block.
def _shape_boxes(shape: str) -> list[tuple[tuple, tuple]]:
    full = ((0, 0, 0), (16, 16, 16))
    if shape == "full":
        return [full]
    if shape == "slab":
        return [((0, 0, 0), (16, 16, 8))]
    if shape == "top_slab":
        return [((0, 0, 8), (16, 16, 16))]
    if shape.startswith("stair"):  # stair_+y: low step toward +y, the high back toward -y
        axis, sign = shape[-1], shape[-2]
        back = {("y", "+"): ((0, 0, 8), (16, 8, 16)), ("y", "-"): ((0, 8, 8), (16, 16, 16)),
                ("x", "+"): ((0, 0, 8), (8, 16, 16)), ("x", "-"): ((8, 0, 8), (16, 16, 16))}[(axis, sign)]
        return [((0, 0, 0), (16, 16, 8)), back]
    if shape in ("pane_x", "pane_y"):  # thin pane along the named axis, centred in the block
        return [((0, 7, 0), (16, 9, 16))] if shape == "pane_x" else [((7, 0, 0), (9, 16, 16))]
    if shape in ("panel_x", "panel_y"):  # door leaf, 3 px thick
        return [((0, 6.5, 0), (16, 9.5, 16))] if shape == "panel_x" else [((6.5, 0, 0), (9.5, 16, 16))]
    if shape == "post":
        return [((6, 6, 0), (10, 10, 16))]
    raise ValueError(shape)


@dataclass
class Structure:
    """A block grid; `origin` is the block coordinate that lands on the building's hotspot."""

    name: str
    replaces: str
    tiles: int  # footprint in AoE2 tiles (square)
    origin: tuple[float, float] = (0.0, 0.0)
    blocks: dict[tuple[int, int, int], tuple[str, str]] = field(default_factory=dict)
    extras: list = field(default_factory=list)  # hand-placed boxes (banners, bells...), in pixels

    def set(self, x: int, y: int, z: int, block: str, shape: str = "full") -> None:
        self.blocks[(x, y, z)] = (block, shape)

    def fill(self, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int, block: str, shape: str = "full") -> None:
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    self.set(x, y, z, block, shape)

    def part(self, types: dict[str, BlockType]) -> Part:
        ox, oy = self.origin
        boxes = []
        for (x, y, z), (block, shape) in self.blocks.items():
            for lo, hi in _shape_boxes(shape):
                lo, hi = np.asarray(lo, float), np.asarray(hi, float)
                base = np.array([(x - ox) * BLOCK, (y - oy) * BLOCK, z * BLOCK], float)
                boxes.append(cuboid(base + lo, hi - lo, _crop(types[block].faces, lo, hi)))
        return Part(self.name, boxes=boxes + self.extras)


def banner(p: Painter, at, facing: str = "+y", width: float = 12, height: float = 22) -> list:
    """A team-coloured wall banner on a stick; `at` is the top centre, in pixels."""
    x, y, z = at
    cloth = p.grid(["DDDDDDDDDDDD"] + ["PPPPPPPPPPPP"] * 3 + ["PPPPPDDPPPPP", "PPPPDLLDPPPP", "PPPDLLLLDPPP",
                    "PPPPDLLDPPPP", "PPPPPDDPPPPP"] + ["PPPPPPPPPPPP"] * 11 + ["PDPPDPPDPPDP", "DPDDPDDPDDPD"],
                   {"P": PC(0.6), "D": PC(0.35), "L": PC(0.85)})
    stick = {f: parse("#6b4a2a")[None, None].copy() for f in FACES}
    faces = {f: cloth if f in ("front", "back", "right", "left") else cloth[:1] for f in FACES}
    if facing == "+y":
        return [cuboid((x - width / 2 - 1, y, z - 1.5), (width + 2, 1.5, 1.5), stick),
                cuboid((x - width / 2, y, z - 1.5 - height), (width, 1, height), faces)]
    return [cuboid((x, y - width / 2 - 1, z - 1.5), (1.5, width + 2, 1.5), stick),
            cuboid((x, y - width / 2, z - 1.5 - height), (1, width, height), faces)]


# --------------------------------------------------------------------------- buildings

def house() -> Structure:
    """AoE2 House (2x2 tiles): a 5x5 plains-village cottage."""
    s = Structure("house", "House", tiles=2, origin=(2.5, 2.5))
    s.fill(0, 0, 0, 4, 4, 0, "cobble")
    s.fill(0, 0, 1, 4, 4, 2, "oak")  # solid: the inside is never seen
    for x, y in ((0, 0), (0, 4), (4, 0), (4, 4)):
        s.fill(x, y, 1, x, y, 2, "log")
    # windows on both visible walls, door on the south-east (+y) wall
    s.set(4, 2, 2, "glass", "pane_y")
    s.set(1, 4, 2, "glass", "pane_x")
    s.set(3, 4, 2, "glass", "pane_x")
    s.set(2, 4, 1, "door_lower", "panel_x")
    s.set(2, 4, 2, "door_upper", "panel_x")
    _gable_roof(s, x0=-1, x1=5, y0=0, y1=4, z=3, roof="spruce", gable="oak")
    s.extras += banner(Painter("house"), at=(2.5 * BLOCK, -1 * BLOCK, 3 * BLOCK - 2), facing="+x")
    return s


def _gable_roof(s: Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str, gable: str) -> None:
    """Stair roof sloping down toward -y and +y, ridge along x, topped with a team-coloured wool ridge."""
    lo, hi, level = y0, y1, z
    while hi - lo >= 2:
        for x in range(x0, x1 + 1):
            s.set(x, lo, level, roof, "stair_-y")
            s.set(x, hi, level, roof, "stair_+y")
        s.fill(x0 + 1, lo + 1, level, x1 - 1, hi - 1, level, gable)  # gable ends + attic
        lo, hi, level = lo + 1, hi - 1, level + 1
    for x in range(x0, x1 + 1):
        s.set(x, (y0 + y1) // 2, level, "wool", "slab")


def town_center() -> Structure:
    """AoE2 Town Center (4x4 tiles): an 11x11 village hall with a bell tower."""
    s = Structure("town_center", "Town Center", tiles=4, origin=(5.5, 5.5))
    s.fill(0, 0, 0, 10, 10, 0, "cobble")
    # ground floor: stone bricks with log corners
    s.fill(0, 0, 1, 10, 10, 2, "stone_bricks")
    for x, y in ((0, 0), (0, 10), (10, 0), (10, 10)):
        s.fill(x, y, 1, x, y, 4, "log")
    # entrance on the south-east (+y) side: log frame and a triple door
    for x in (3, 7):
        s.fill(x, 10, 1, x, 10, 2, "log")
    for x in (4, 5, 6):
        s.set(x, 10, 1, "door_lower", "panel_x")
        s.set(x, 10, 2, "door_upper", "panel_x")
    for y in (2, 5, 8):
        s.set(10, y, 2, "glass", "pane_y")
    for x in (1, 9):
        s.set(x, 10, 2, "glass", "pane_x")
    # timber upper floor with a row of windows
    s.fill(0, 0, 3, 10, 10, 4, "oak")
    for x, y in ((0, 0), (0, 10), (10, 0), (10, 10), (5, 10), (10, 5)):
        s.fill(x, y, 3, x, y, 4, "log")
    s.fill(0, 10, 3, 10, 10, 3, "spruce")  # floor beam
    s.fill(10, 0, 3, 10, 10, 3, "spruce")
    for y in (2, 3, 7, 8):
        s.set(10, y, 4, "glass", "pane_y")
    for x in (2, 3, 7, 8):
        s.set(x, 10, 4, "glass", "pane_x")
    _gable_roof(s, x0=-1, x1=11, y0=0, y1=10, z=5, roof="dark_oak", gable="oak")
    # bell tower on the ridge
    top = 5 + 5 + 1  # first free level above the ridge
    s.fill(4, 4, 8, 6, 6, top - 1, "oak")
    for x, y in ((4, 4), (4, 6), (6, 4), (6, 6)):
        s.fill(x, y, top, x, y, top + 2, "log", "post")
    s.fill(4, 4, top + 3, 6, 6, top + 3, "spruce", "slab")
    s.set(5, 5, top + 3, "spruce")
    s.set(5, 5, top + 4, "wool", "slab")
    p = Painter("town_center")
    bell = {f: p.fill(8, 8, "#e8b923", 0.08) for f in FACES}
    chain = {f: parse("#3a3a3a")[None, None].copy() for f in FACES}
    c = np.array([(5 - 5.5) * BLOCK + 8, (5 - 5.5) * BLOCK + 8, (top + 1) * BLOCK + 12])  # bell top
    s.extras += [cuboid(c + (-4, -4, -8), (8, 8, 8), bell), cuboid(c + (-5, -5, -9), (10, 10, 2), bell),
                 cuboid(c + (-1, -1, 0), (2, 2, 2 * BLOCK - 12), chain)]
    s.extras += banner(p, at=(5.5 * BLOCK, -3 * BLOCK + 8, 3 * BLOCK - 2), facing="+x", height=26)
    s.extras += banner(p, at=(5.5 * BLOCK, 2 * BLOCK + 8, 3 * BLOCK - 2), facing="+x", height=26)
    s.extras += banner(p, at=(-3 * BLOCK + 8, 5.5 * BLOCK, 5 * BLOCK - 2), facing="+y", height=26)
    s.extras += banner(p, at=(3 * BLOCK - 8, 5.5 * BLOCK, 5 * BLOCK - 2), facing="+y", height=26)
    return s


BUILDINGS = {"house": house, "town_center": town_center}
