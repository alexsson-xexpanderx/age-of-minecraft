"""Easter eggs, in the game's hidden cheat-unit slots.

* Pac-Man replaces Furious the Monkey Boy (chat cheat: "furious the monkey boy"):
  a voxel ball whose jaw chomps as he walks and attacks, with the arcade death
  where the mouth opens all the way and he vanishes with a pop.
* A ghost replaces the VDML cheat guy ("i love the monkey head"): the ghost is
  in the owner's team colour, like Blinky, Pinky, Inky and Clyde.
* A blocky Cobra replaces the Cobra Car ("how do you turn this on"): the same
  roadster built from blocks, in the owner's team colour (the original is
  always blue) with its two white racing stripes, wide fenders, side pipes and
  a glass windshield. The game draws it from one picture per direction for
  everything it does.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import Part, cuboid
from .siege import wheel
from .textures import FACES, PC, Painter, parse
from .units import Unit, solid

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


WINDSHIELD_TILT = -25  # degrees


def _striped(p: Painter, w: int, d: int, paint) -> np.ndarray:
    """A top face (d rows along the car, w columns across) with the Cobra's two white stripes down the middle."""
    tex = p.fill(w, d, paint, 0.05)
    for x in range(w):
        if 1 <= abs(x + 0.5 - w / 2) <= 4:
            tex[:, x] = parse("#f2f2f2")
    return tex


def cobra_car(key: str = "cobra_car") -> Unit:
    """A blocky AC Cobra: an open two-seater facing +y, its body in the owner's colour with white stripes."""
    p = Painter(key)
    paint, dark = PC(0.55), PC(0.35)
    body = Part("body")

    def box(lo, size, faces):
        body.boxes.append(cuboid(lo, size, faces))

    nose = p.skin((16, 1, 5), paint, front=p.grid(  # the front: headlights, the grille and the stripes
        ["ppppWWWppWWWpppp", "pYYpWWWppWWWpYYp", "pYYpKKKKKKKKpYYp", "pppKKKKKKKKKKppp", "pppppppppppppppp"], {"p": paint, "W": "#f2f2f2", "Y": "#fff3b0", "K": "#1c1c1c"}))
    tail = p.skin((16, 1, 5), paint, back=p.grid(
        ["ppppWWWppWWWpppp", "pRRpWWWppWWWpRRp", "pRRpWWWppWWWpRRp", "pppppppppppppppp", "pppppppppppppppp"], {"p": paint, "W": "#f2f2f2", "R": "#d02020"}))
    # hood and rear deck, striped on top; their ends carry the lights
    box((-8, 6, 4), (16, 12, 6), {**p.skin((16, 12, 6), paint), "top": _striped(p, 16, 12, paint)})
    box((-8, 18, 4), (16, 1, 5), nose)
    box((-8, -18, 4), (16, 8, 6), {**p.skin((16, 8, 6), paint), "top": _striped(p, 16, 8, paint)})
    box((-8, -19, 4), (16, 1, 5), tail)
    # the cockpit: low sides, a floor, two seats, the dashboard and the steering wheel
    for x in (-9, 7.5):
        box((x, -10, 3), (1.5, 16, 6.5), p.skin((1.5, 16, 6.5), paint))
    box((-7.5, -10, 3), (15, 16, 1.5), p.skin((15, 16, 1.5), "#2a2a2a"))
    leather, back = p.skin((5, 5, 2.5), "#4a2e1e"), p.skin((5, 1.5, 6), "#3c2416")
    for x in (-6.5, 1.5):
        box((x, -7, 4.5), (5, 5, 2.5), leather)
        box((x, -9, 4.5), (5, 1.5, 6.5), back)
    box((-7.5, 4, 4.5), (15, 2, 5), p.skin((15, 2, 5), "#2a2a2a", top=_striped(p, 15, 2, paint)))
    box((-5.5, 3, 8.5), (3, 0.8, 3), solid("#141414"))
    # the windshield: glass in an iron frame, leaning back
    glass = p.skin((14, 0.8, 4), "#b8e2f2", top="#dcdcdc", bottom="#dcdcdc")
    shield = Part("windshield", pivot=(0, 6, 9.5), rot=(WINDSHIELD_TILT, 0, 0), boxes=[
        cuboid((-7, 5.2, 9.5), (14, 0.8, 4), glass), cuboid((-7.5, 5, 13.5), (15, 1.2, 0.8), solid("#dcdcdc"))])
    body.add(shield)
    # wide fenders over the wheels, side pipes, bumpers
    for x in (-10, 8):
        for y0 in (7, -15):
            box((x, y0, 6), (2, 8, 3.5), p.skin((2, 8, 3.5), paint, top=dark))
        box((x + (0.3 if x < 0 else 0.7), -6, 3), (1, 10, 1.2), solid("#cfcfcf"))
    box((-8, 19, 3.5), (16, 0.8, 1), solid("#dcdcdc"))
    box((-8, -19.8, 3.5), (16, 0.8, 1), solid("#dcdcdc"))
    box((-9, -18, 3), (18, 36, 1), p.skin((18, 36, 1), dark))  # the underside, between the wheels
    wheels = [wheel(p, f"wheel_{i + 1}", (x, y, 4.5), 4.5, 3, rim="#1c1c1c", wood="#bdbdbd")
              for i, (x, y) in enumerate(((9.5, 11), (-9.5, 11), (9.5, -11), (-9.5, -11)))]
    root = Part("root").add(body, *wheels)
    return Unit(key, "Blocky Cobra", "Cobra Car (cheat)", "wheeled", root, group="easter", attack="none", scale=1.5)


EASTER = {"pacman": pacman, "ghost": ghost, "cobra_car": cobra_car}
