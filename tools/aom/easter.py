"""Easter eggs, in the game's hidden cheat-unit slots.

* Pac-Man replaces Furious the Monkey Boy (chat cheat: "furious the monkey boy"):
  a voxel ball whose jaw chomps as he walks and attacks, with the arcade death
  where the mouth opens all the way and he vanishes with a pop.
* A ghost replaces the VDML cheat guy ("i love the monkey head"): the ghost is
  in the owner's team colour, like Blinky, Pinky, Inky and Clyde.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import Part, cuboid
from .textures import FACES, PC, Painter, parse
from .units import Unit

R = 10.0  # Pac-Man's radius in Minecraft pixels
CELL = 2.0


def _tex(paint: np.ndarray, w: int = 2, h: int = 2) -> np.ndarray:
    return paint[:h, :w]


def _hemisphere(p: Painter, upper: bool, skin: str, mouth) -> list:
    """Columns of a voxel half-sphere around the origin; the flat cut face is the inside of the mouth."""
    boxes = []
    yellow = p.speckle(skin, ("#f2c200", 0.25), ("#fff066", 0.08))(16, 16)
    inside = p.fill(16, 16, mouth, 0.05)
    n = int(R // CELL)
    for i in range(-n, n):
        for j in range(-n, n):
            cx, cy = (i + 0.5) * CELL, (j + 0.5) * CELL
            d2 = cx * cx + cy * cy
            if d2 >= R * R:
                continue
            h = math.sqrt(R * R - d2)
            h = max(CELL / 2, round(h / 1.0) * 1.0)
            faces = {f: yellow[:2, :2] for f in FACES}
            faces["bottom" if upper else "top"] = inside[:2, :2]
            z0 = 0.0 if upper else -h
            boxes.append(cuboid((cx - CELL / 2, cy - CELL / 2, z0), (CELL, CELL, h), faces))
    return boxes


def pacman(key: str = "pacman") -> Unit:
    p = Painter(key)
    mouth = PC(0.15)  # the inside of the mouth shows the owner's colour, very dark
    centre = R + 1.0
    upper = Part("jaw_top", pivot=(0, 0, centre), boxes=[
        cuboid(b.lo + (0, 0, centre), b.hi - b.lo, b.faces) for b in _hemisphere(p, True, "#ffd400", mouth)])
    lower = Part("jaw_bottom", pivot=(0, 0, centre), boxes=[
        cuboid(b.lo + (0, 0, centre), b.hi - b.lo, b.faces) for b in _hemisphere(p, False, "#ffd400", mouth)])
    black = {f: np.tile(parse("#111111"), (2, 2, 1)) for f in FACES}
    for sx in (-1, 1):  # eyes on the upper half, near the front
        e = np.array([sx * 0.42, 0.5, 0.62])
        e = e / np.linalg.norm(e) * (R - 0.6)
        upper.boxes.append(cuboid((e[0] - 1.25, e[1] - 1.25, centre + e[2] - 1.25), (2.5, 2.5, 2.5), black))
    white = {f: np.tile(parse("#ffffff"), (2, 2, 1)) for f in FACES}
    pop = Part("pop", boxes=[cuboid((-1, -1, centre - 7), (2, 2, 14), white),
                             cuboid((-7, -1, centre - 1), (14, 2, 2), white),
                             cuboid((-1, -7, centre - 1), (2, 14, 2), white)])
    root = Part("root").add(Part("body").add(upper, lower), pop)
    return Unit(key, "Pac-Man", "Furious the Monkey Boy (cheat)", "pacman", root, group="easter",
                attack="chomp", scale=1.2)


def ghost(key: str = "ghost") -> Unit:
    """A Pac-Man ghost in the owner's team colour: dome head, wavy skirt, eyes looking ahead."""
    p = Painter(key)
    body_paint = p.fill(16, 16, PC(0.6), 0.04)
    faces = {f: body_paint[:2, :2] for f in FACES}
    w, h0 = 7.0, 10.0  # half width, height of the straight part
    boxes = []
    for i in range(-3, 4):
        for j in range(-3, 4):
            cx, cy = i * 2.0, j * 2.0
            d2 = cx * cx + cy * cy
            if d2 > w * w:
                continue
            top = h0 + math.sqrt(max(0.0, w * w - d2))
            boxes.append(cuboid((cx - 1, cy - 1, 4), (2, 2, top - 4), faces))
    white = {f: np.tile(parse("#ffffff"), (2, 2, 1)) for f in FACES}
    blue = {f: np.tile(parse("#2121de"), (2, 2, 1)) for f in FACES}
    for sx in (-1, 1):
        boxes.append(cuboid((sx * 3 - 2, w - 1.5, 11), (4, 2, 5), white))
        boxes.append(cuboid((sx * 3 - 1, w + 0.2, 11.5), (2, 1, 2.5), blue))
    body = Part("body", boxes=boxes)
    skirt = []
    for k, (cx, cy) in enumerate(((-4, -4), (4, -4), (-4, 4), (4, 4), (0, -5), (0, 5), (-5, 0), (5, 0))):
        skirt.append(Part(f"foot{k % 2}_{k}", boxes=[cuboid((cx - 1.5, cy - 1.5, 1), (3, 3, 3.5), faces)]))
    root = Part("root", offset=(0, 0, 2)).add(body, *skirt)
    return Unit(key, "Ghost", "VDML (cheat)", "ghost", root, group="easter", attack="none", scale=1.2)


EASTER = {"pacman": pacman, "ghost": ghost}
