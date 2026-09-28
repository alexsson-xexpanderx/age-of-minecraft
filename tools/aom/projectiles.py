"""Projectiles: Minecraft arrows, bolts, thrown axes, snowballs and flying blocks.

A projectile is modelled around its own centre (the sprite's hotspot) and
points along +y, the way it flies. Arrow sprites store a direction per angle
and, over their frames, the pitch from climbing to diving.
"""
from __future__ import annotations

import numpy as np

from .blocks import blocks
from .geometry import Part, cuboid
from .textures import FACES, parse


def _solid(col: str, n: int = 2) -> dict:
    return {f: np.tile(parse(col), (n, n, 1)) for f in FACES}


def arrow(scale: float = 1.0, burning: bool = False) -> Part:
    """A Minecraft arrow: flint tip, wooden shaft, white fletching; `scale` 1.6 for scorpion bolts."""
    L = 14 * scale
    boxes = [cuboid((-0.5 * scale, -L / 2, -0.5 * scale), (1 * scale, L, 1 * scale), _solid("#6b4a2a")),
             cuboid((-1 * scale, L / 2 - 1, -1 * scale), (2 * scale, 3 * scale, 2 * scale), _solid("#5a5a5a")),
             cuboid((-0.25, -L / 2, -2 * scale), (0.5, 4 * scale, 4 * scale), _solid("#eeeeee")),
             cuboid((-2 * scale, -L / 2, -0.25), (4 * scale, 4 * scale, 0.5), _solid("#dcdcdc"))]
    if burning:
        boxes.append(cuboid((-1.5 * scale, L / 2 - 2, -1.5 * scale), (3 * scale, 4 * scale, 3 * scale),
                            _solid("#ffb02a")))
    return Part("arrow", boxes=boxes)


def thrown(kind: str = "axe") -> Part:
    """A spinning throwing axe (or a scimitar)."""
    if kind == "sword":
        return Part("sword", boxes=[cuboid((-0.5, -2, -1), (1, 4, 2), _solid("#6b4a2a")),
                                    cuboid((-0.5, 2, -1.5), (1, 11, 3), _solid("#dcdcdc")),
                                    cuboid((-0.6, 1, -3), (1.2, 1.5, 6), _solid("#e8b923"))])
    return Part("axe", boxes=[cuboid((-0.5, -6, -0.5), (1, 12, 1), _solid("#6b4a2a")),
                              cuboid((-0.6, 3, -0.5), (1.2, 4, 5), _solid("#c0c0c0"))])


def snowball() -> Part:
    tex = np.tile(parse("#f4fbfb"), (4, 4, 1))
    tex[1, 1] = tex[2, 3] = parse("#cfe0e4")
    return Part("snowball", boxes=[cuboid((-2, -2, -2), (4, 4, 4), {f: tex for f in FACES})])


def flying_block(name: str, size: float = 8.0) -> Part:
    faces = blocks()[name].faces
    return Part("block", boxes=[cuboid((-size / 2, -size / 2, -size / 2), (size, size, size), faces)])


def projectile(kind: str, t: float = 0.5, spin: bool = False) -> Part:
    """`t` runs 0..1 over the sprite's frames: the pitch for arrows, the spin for thrown things."""
    if kind in ("arrow", "fire_arrow", "bolt"):
        body = arrow(1.7 if kind == "bolt" else 1.0, burning=kind == "fire_arrow")
        pitch = 0.0 if not spin else 50.0 - 100.0 * t
        return Part("projectile", rot=(pitch, 0, 0), children=[body])
    if kind == "stuck_arrow":
        return Part("projectile", rot=(-55, 0, 0), offset=(0, 0, 5), children=[arrow()])
    if kind in ("axe", "sword"):
        return Part("projectile", rot=(-360.0 * t, 0, 0), children=[thrown(kind)])
    if kind == "snowball":
        return snowball()
    block = {"cobble": "cobblestone", "stone": "mossy_cobblestone", "tnt": "tnt", "magma": "shroomlight"}[kind]
    return Part("projectile", rot=(360.0 * t, 90.0 * t, 0), children=[flying_block(block)])
