"""Farms. In The Conquerors a farm is terrain, not a sprite.

A Farm changes the ground under it. While a villager builds it, its tiles go
through three farm terrains (Farm 1, 2 and 3: terrains 29, 30 and 31). A
finished farm is terrain 7 and an exhausted one terrain 8, the dead farm.
Their textures are SLPs in terrain.drs, with one diamond-shaped frame per
tile (97x49), picked by the tile's map position: 6x6 frames for the farm and
the dead farm, 3x3 for the stages.

Each texture becomes Minecraft farmland, 2 blocks to a tile (a little bigger
than the units' blocks, a tile being 2.83 of those, so the wheat reads at game
size), with a row of wheat on every other row of blocks and bare farmland
between. The wheat has thick stalks and grows through the stages. The pattern
repeats every tile, so the tiles join up whichever frame the game picks. Wheat
that stands up into the tile behind is drawn in that tile too. Each new frame
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
from .textures import FACES, parse

# the farm terrains in the .dat, and what each becomes
FARM_TERRAINS = {29: "tilled", 30: "sprouts", 31: "growing", 7: "ripe", 8: "dead"}
# their textures in the original terrain.drs (openage doc/media/terrain.md), if the .dat's terrain table can't be read
FARM_SLPS = {15021: "tilled", 15022: "sprouts", 15023: "growing", 15004: "ripe", 15005: "dead"}
STAGES = {"tilled": "farm being built, first third", "sprouts": "farm being built, second third",
          "growing": "farm being built, last third", "ripe": "farm", "dead": "exhausted farm"}
WHEAT = {"sprouts": 1, "growing": 4, "ripe": 7}  # Minecraft's growth stages, 0..7
PER_TILE = 2  # blocks along a tile's side


def scale(per_tile: int) -> float:
    """Screen pixels per Minecraft pixel that make `per_tile` blocks one 96x48 tile."""
    return 48 / (per_tile * V.BLOCK * 0.5 ** 0.5)


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
    """A 16x16 wheat crop texture at a growth stage (0 seedlings .. 7 ripe): three stalks two texels thick, with
    leaves while young and big grain heads from stage 5, in flat colours so they stay clear at game size."""
    tex = np.zeros((16, 16, 5), np.float32)
    ripe = level >= 7
    stem = ("#7a7a2a", "#9a9a3a") if ripe else ("#3a7020", "#5c9a2c")
    grain = ("#e8c860", "#b8902e", "#7a5a1a") if ripe else ("#9ccf48", "#6fa42e", "#3f6a1a")
    tall = 3 + level * 1.6
    for i, c0 in enumerate((1, 6, 11)):
        c0 += variant % 2
        t = int(min(14, max(0, round(16 - tall + (i + variant) % 3 - 1))))
        tex[t:, c0], tex[t:, c0 + 1] = parse(stem[0]), parse(stem[1])
        if level >= 5:  # the head: kernels alternating left and right, a dark tip
            head = min(15 - t, 3 + level - 5)
            for r in range(t, t + head):
                tex[r, c0:c0 + 2] = parse(grain[0])
                side = c0 - 1 if (r - t) % 2 == 0 else c0 + 2
                if 0 <= side < 16:
                    tex[r, side] = parse(grain[1])
            tex[max(0, t - 1), c0:c0 + 2] = parse(grain[2])
        elif level >= 1:  # two leaves
            for r, c in ((t + 2, c0 + 2), (t + 1, c0 + 3), (t + 4, c0 - 1), (t + 3, c0 - 2)):
                if 0 <= r < 16 and 0 <= c < 16:
                    tex[r, c] = parse(stem[1])
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


def field(stage: str, reach: int = 2, per_tile: int = PER_TILE) -> V.Structure:
    """Farmland around one tile, `reach` tiles each way; the tile's centre is the origin."""
    n = per_tile
    s = V.Structure(f"farmland_{stage}", origin=(n / 2, n / 2))
    block = "dry_farmland" if stage == "dead" else "farmland"
    level = WHEAT.get(stage)
    for x in range(-reach * n, (reach + 1) * n):
        for y in range(-reach * n, (reach + 1) * n):
            s.set(x, y, -1, block)  # the top is the ground
            if level is not None and y % 2 == 0:  # a row of wheat, then a row of bare farmland
                crop(s, x, y, wheat(level, (x % n) * n + y % n))  # the same plants in every tile
    return s


@lru_cache(maxsize=None)
def texture(stage: str, per_tile: int = PER_TILE) -> tuple[Frame, tuple[int, int]]:
    """The farm rendered from the game's camera, and the screen position of the centre tile's centre."""
    root = field(stage, per_tile=per_tile).part(V.all_blocks())
    cam = fit_camera(root, V.BUILDING_HEADING, scale=scale(per_tile), pad=2)
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


def preview(stage: str, size: int = 3, per_tile: int = PER_TILE) -> np.ndarray:
    """RGBA of a size x size tile farm as it lies on the map, its centre in the middle of the image."""
    frame, (ox, oy) = texture(stage, per_tile)
    rgba = frame.to_rgba()
    hw, hh = 48 * size, 24 * size
    yy, xx = np.mgrid[-hh:hh + 1, -hw:hw + 1]
    out = rgba[oy - hh:oy + hh + 1, ox - hw:ox + hw + 1].copy()
    out[np.abs(xx) / hw + np.abs(yy) / hh > 1] = 0
    return out
