"""Farms. In The Conquerors a farm is terrain, not a sprite.

A Farm changes the ground under it. While a villager builds it, its tiles go
through three farm terrains (Farm 1, 2 and 3: terrains 29, 30 and 31). A
finished farm is terrain 7 and an exhausted one terrain 8, the dead farm.
Their textures are SLPs in terrain.drs, with one diamond-shaped frame per
tile (97x49), picked by the tile's map position: 6x6 frames for the farm and
the dead farm, 3x3 for the stages.

Each texture becomes Minecraft farmland, 3 blocks to a tile (a tile is really
2.83 blocks), with wheat that grows through the stages. The pattern repeats
every tile, so the tiles join up whichever frame the game picks. Wheat that
stands up into the tile behind is drawn in that tile too. Each new frame
fills exactly the pixels of the original frame, so its diamond and the
blending with the ground around the farm stay as they were.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import slp
from . import voxel as V
from .geometry import cuboid
from .palette import Quantiser
from .render import Frame, fit_camera, render
from .textures import FACES, Painter, parse

# the farm terrains in the .dat, and what each becomes
FARM_TERRAINS = {29: "tilled", 30: "sprouts", 31: "growing", 7: "ripe", 8: "dead"}
# their textures in the original terrain.drs (openage doc/media/terrain.md), if the .dat's terrain table can't be read
FARM_SLPS = {15021: "tilled", 15022: "sprouts", 15023: "growing", 15004: "ripe", 15005: "dead"}
STAGES = {"tilled": "farm being built, first third", "sprouts": "farm being built, second third",
          "growing": "farm being built, last third", "ripe": "farm", "dead": "exhausted farm"}
WHEAT = {"sprouts": 1, "growing": 4, "ripe": 7}  # Minecraft's growth stages, 0..7
PER_TILE = 3  # blocks along a tile's side
SCALE = 2 ** 0.5  # screen pixels per Minecraft pixel that make PER_TILE blocks one 96x48 tile


def farm_slps(terrains) -> list[tuple[int, str, str]]:
    """(SLP id, stage, where it came from) of each farm texture: from the .dat's terrain table if it was read."""
    found = []
    for t in terrains or []:
        if t.id in FARM_TERRAINS and t.slp > 0:
            found.append((t.slp, FARM_TERRAINS[t.id], f"terrain {t.id} {t.name!r}"))
    if found:
        return found
    return [(s, stage, "the original game's id") for s, stage in FARM_SLPS.items()]


def wheat(level: int, variant: int = 0) -> np.ndarray:
    """A 16x16 wheat crop texture at a growth stage (0 seedlings .. 7 ripe), like Minecraft's."""
    p = Painter(f"farm_wheat{level}_{variant}")
    tex = np.zeros((16, 16, 5), np.float32)
    ripe = level >= 7
    stem = ("#8a9a36", "#a89a44") if ripe else ("#3f7a1e", "#5a9a2a")
    head = ("#d8b850", "#b08a30", "#7a5a1c") if ripe else ("#7aa83a", "#5f8f2a", "#46701e")
    top = 16 - int(round(3 + level * 1.6))  # how far up the tallest stalks reach
    for c in range(16):
        if p.rng.random() < 0.3:
            continue  # gaps between the stalks
        t = min(15, top + int(p.rng.integers(0, 4)))
        tex[t:, c] = parse(stem[int(p.rng.integers(0, 2))])
        if level >= 5:  # the ears: grains in two shades with a dark husk line
            ear = min(16 - t, 3 + level - 5)
            for r in range(t, t + ear):
                tex[r, c] = parse(head[(r + c) % 2])
            tex[t + ear - 1, c] = parse(head[2])
        elif level >= 1 and t + 2 < 16 and c + 1 < 16 and p.rng.random() < 0.5:
            tex[t + 1, c + 1] = parse(stem[1])  # a leaf
    return tex


def crop(s: V.Structure, x: int, y: int, sprite: np.ndarray) -> None:
    """Minecraft's crop model on block (x, y): four upright planes in a # pattern, standing on the ground."""
    ox, oy = s.origin
    B = V.BLOCK
    x0, y0 = (x - ox) * B, (y - oy) * B
    faces = {f: sprite for f in FACES}
    faces["top"] = faces["bottom"] = np.zeros((1, 1, 5), np.float32)
    for at in (4, 12):
        s.extras.append(cuboid((x0 + at - 0.25, y0, 0), (0.5, B, B), faces))
        s.extras.append(cuboid((x0, y0 + at - 0.25, 0), (B, 0.5, B), faces))


def field(stage: str, reach: int = 2) -> V.Structure:
    """Farmland around one tile, `reach` tiles each way; the tile's centre is the origin."""
    n = PER_TILE
    s = V.Structure(f"farmland_{stage}", origin=(n / 2, n / 2))
    block = "dry_farmland" if stage == "dead" else "farmland"
    level = WHEAT.get(stage)
    sprites = {}
    for x in range(-reach * n, (reach + 1) * n):
        for y in range(-reach * n, (reach + 1) * n):
            s.set(x, y, -1, block)  # the top is the ground
            if level is not None:
                k = (x % n) * n + y % n  # the same nine plants in every tile
                grown = level - 1 if level < 7 and k % 4 == 1 else level  # two a stage behind
                if (grown, k) not in sprites:
                    sprites[grown, k] = wheat(grown, k)
                crop(s, x, y, sprites[grown, k])
    return s


@lru_cache(maxsize=None)
def texture(stage: str) -> tuple[Frame, tuple[int, int]]:
    """The farm rendered from the game's camera, and the screen position of the centre tile's centre."""
    root = field(stage).part(V.all_blocks())
    cam = fit_camera(root, V.BUILDING_HEADING, scale=SCALE, pad=2)
    frame = render(root, V.BUILDING_HEADING, camera=cam, shadow=False, outline=False)
    return frame, (int(cam.origin[0]), int(cam.origin[1]))


def tiles(stage: str, original: bytes, quant: Quantiser) -> list[slp.SlpFrame]:
    """Every frame of an original farm texture, redrawn in the same pixels."""
    frame, (ox, oy) = texture(stage)
    codes = quant.frame_codes(frame, obstruction=False)
    out = []
    for f in slp.decode(original):
        ys, xs = np.nonzero(f.pixels != slp.TRANSPARENT)
        if not len(ys):
            out.append(f)
            continue
        cx, cy = (xs.min() + xs.max()) // 2, (ys.min() + ys.max()) // 2  # the tile's centre
        px = np.full(f.pixels.shape, slp.TRANSPARENT, np.int16)
        px[ys, xs] = codes[oy + ys - cy, ox + xs - cx]
        if (px[ys, xs] < 0).any():
            raise ValueError(f"farm texture '{stage}' does not cover a {f.pixels.shape[1]}x{f.pixels.shape[0]} tile")
        out.append(slp.SlpFrame(px, f.hotspot))
    return out


def encode(stage: str, original: bytes, quant: Quantiser) -> bytes:
    return slp.encode(tiles(stage, original, quant), props=slp.frame_props(original))


def preview(stage: str, size: int = 3) -> np.ndarray:
    """RGBA of a size x size tile farm as it lies on the map, its centre in the middle of the image."""
    frame, (ox, oy) = texture(stage)
    rgba = frame.to_rgba()
    hw, hh = 48 * size, 24 * size
    yy, xx = np.mgrid[-hh:hh + 1, -hw:hw + 1]
    out = rgba[oy - hh:oy + hh + 1, ox - hw:ox + hw + 1].copy()
    out[np.abs(xx) / hw + np.abs(yy) / hh > 1] = 0
    return out
