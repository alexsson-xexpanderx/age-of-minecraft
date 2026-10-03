"""Easter eggs, in the game's hidden cheat-unit slots.

* Pac-Man replaces Furious the Monkey Boy (chat cheat: "furious the monkey boy"):
  a voxel ball whose jaw chomps as he walks and attacks, with the arcade death
  where the mouth opens all the way and he vanishes with a pop.
* A ghost replaces the VDML cheat guy ("i love the monkey head"): the ghost is
  in the owner's team colour, like Blinky, Pinky, Inky and Clyde.
* A giant red Pac-Man replaces the Saboteur ("to smithereens"; gameplay._giant):
  Pac-Man painted red and drawn 12.5 times as big as him, wider and taller than a
  Castle and a Wonder side by side.
* A blocky Cobra replaces the Cobra Car ("how do you turn this on"): the same
  roadster built from blocks, in the owner's team colour (the original is
  always blue) with its two white racing stripes, wide fenders, side pipes and
  a glass windshield. The game draws it from one picture per direction for
  everything it does.
* A dragon takes the Advanced Heavy Crossbowman's slot (unit 493, a leftover the
  game never trains; gameplay._dragon makes the Wonder train it): black like the
  Ender Dragon, with wings in the owner's colour, always up in the air with its
  shadow on the ground. It spits fire, and its shots are fireballs (`fireball`).
"""
from __future__ import annotations

import dataclasses
import math
import zlib

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
    # twice the size he first had (1.2), with twice the room on the map to match (gameplay.PACMAN_SIZE)
    return Unit(key, "Pac-Man", "Furious the Monkey Boy (cheat)", "pacman", root, group="easter",
                attack="chomp", scale=2.4)


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


GIANT_SCALE = 30.0  # Pac-Man is drawn at 2.4: this is wider and taller than a Castle and a Wonder side by side
RED_TEAM = 32  # the game palette's red team shades, dark to light: plain pixels there stay red whoever owns him


def _team_paint(part: Part) -> None:
    """Pac-Man's yellow becomes team-colour paint of the same lightness (drawn later in RED_TEAM's shades)."""
    for b in part.boxes:
        for face, tex in b.faces.items():
            t = tex.astype(np.float32)
            yellow = (t[..., 0] > 0.6) & (t[..., 1] > 0.45) & (t[..., 2] < 0.45) & (t[..., 3] > 0)
            if yellow.any():
                t = t.copy()
                light = np.clip(t[..., :3].mean(-1)[yellow], 0, 1)
                t[yellow] = np.stack([light, light, light, np.ones_like(light), np.ones_like(light)], -1)
                b.faces[face] = t
    for c in part.children:
        _team_paint(c)


def giant_pacman(key: str = "giant_pacman") -> Unit:
    """The giant red Pac-Man: Pac-Man himself, painted for the red team's shades and drawn far bigger."""
    u = pacman(key)
    _team_paint(u.root)
    return dataclasses.replace(u, name="Giant Pac-Man", replaces="Saboteur (cheat)", scale=GIANT_SCALE)


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


DRAGON_HEIGHT = 40.0  # Minecraft pixels from the ground to the middle of its body: it is always in the air
DRAGON_SCALE = 1.7
DRAGON_MOUTH = (47.0, 1.0)  # its mouth, forward from and up from the middle of its body: where its fire comes out


def dragon(key: str = "dragon") -> Unit:
    """A Minecraft dragon in the Ender Dragon's colours, flying, facing +y: black scales with grey plates down its
    back, neck and tail, glowing purple eyes, and wings of the owner's colour. Its jaw opens to spit fire."""
    p = Painter(key)
    scales = p.speckle("#1c1c20", ("#2a2a31", 0.3), ("#121215", 0.2))
    plate, bone = solid("#55555f"), p.skin((2, 2, 2), "#34343c")
    membrane = p.speckle(PC(0.4), (PC(0.3), 0.25), (PC(0.5), 0.1))

    def skin(size):
        return p.skin(size, scales)

    torso = Part("torso", boxes=[cuboid((-6, -14, -5), (12, 28, 10), skin((12, 28, 10)))]
                 + [cuboid((-1, y, 5), (2, 6, 3), plate) for y in (-11, -3, 5)])
    head = Part("head", pivot=(0, 27, 2), boxes=[
        cuboid((-5, 27, -1), (10, 10, 8), skin((10, 10, 8))),
        cuboid((-3.5, 37, 1), (7, 9, 4), p.skin((7, 9, 4), scales, top=p.grid(
            ["sssssss"] * 7 + ["sKsssKs", "sssssss"], {"s": "#1c1c20", "K": "#5a5a66"}))),
        cuboid((-3, 37.5, 0), (6, 8.5, 1), solid("#4a0c0c")),  # inside the mouth
        cuboid((-4, 28, 7), (2, 3, 3), plate), cuboid((2, 28, 7), (2, 3, 3), plate)]
        + [cuboid((x, 32, 3.5), (0.6, 3, 1.5), solid("#d27cff")) for x in (-5.4, 4.8)])  # the eyes
    head.add(Part("jaw", pivot=(0, 37, 0.5), boxes=[cuboid((-3.5, 37, -1.5), (7, 9, 2.5), skin((7, 9, 2.5)))]))
    # a cone of fire from its mouth, widening and reddening away from it, with a hot yellow streak along its top
    flames = [((-2.5, 46, -1.5), (5, 6, 5), "#fff27a"), ((-4, 51.5, -2.5), (8, 7, 7), "#ffb020"),
              ((-5, 58, -3), (10, 8, 8), "#ff8a14"), ((-4.5, 65.5, -2.5), (9, 6, 7), "#ff5a0a"),
              ((-3, 71, -1.5), (6, 5, 5), "#e8300a"), ((-2, 52, 4.4), (4, 14, 0.8), "#fff27a"),
              ((5, 60, 3.5), (2, 2, 2), "#ffd84a"), ((-7, 66, -3), (2, 2, 2), "#ff8a14"),
              ((1.5, 76.5, 2), (2, 2, 2), "#ffd84a")]
    head.add(Part("fire_long", boxes=[cuboid(lo, size, solid(c)) for lo, size, c in flames]),
             Part("fire_short", boxes=[cuboid(lo, size, solid(c)) for lo, size, c in flames[:2]]))
    neck = Part("neck", pivot=(0, 14, 0), boxes=[
        cuboid((-3, 14, -2), (6, 7, 6), skin((6, 7, 6))), cuboid((-3, 20, -1), (6, 7, 6), skin((6, 7, 6))),
        cuboid((-0.75, 16, 4), (1.5, 3, 2), plate), cuboid((-0.75, 22, 5), (1.5, 3, 2), plate)]).add(head)
    tail, y = torso, -14.0
    for k, (w, d) in enumerate(((7, 7), (6, 7), (5, 7), (4, 7), (3, 6))):  # five links, thinner to the tip
        link = Part(f"tail{k + 1}", pivot=(0, y, 0), boxes=[
            cuboid((-w / 2, y - d, -w / 2), (w, d, w), skin((w, d, w))),
            cuboid((-0.5, y - d + 2, w / 2), (1, 3, 1.5), plate)])
        tail.add(link)
        tail, y = link, y - d
    def web(w: int, d: int, struts: tuple[int, ...]) -> dict:
        """A wing's membrane, w across and d deep, with thin finger bones running back through it."""
        faces = p.skin((w, d, 0.8), membrane)
        for face in ("top", "bottom"):
            for x in struts:
                faces[face][:, x] = parse("#34343c")
        return faces

    for side in (1, -1):  # bony arms with the membrane trailing behind them, folding at the wrist
        x0 = 6 * side
        arm = Part("wing_r" if side > 0 else "wing_l", pivot=(x0, 6, 3), boxes=[
            cuboid((min(x0, x0 + 20 * side), 4, 2), (20, 2.5, 2.5), bone),
            cuboid((min(x0, x0 + 20 * side), -12, 2.5), (20, 16, 0.8), web(20, 16, (7, 14)))])
        x1 = x0 + 20 * side
        arm.add(Part("tip_r" if side > 0 else "tip_l", pivot=(x1, 5, 3), boxes=[
            cuboid((min(x1, x1 + 18 * side), 4.2, 2.2), (18, 2, 2), bone),
            cuboid((min(x1, x1 + 18 * side), -8, 2.6), (18, 12, 0.8), web(18, 12, (6, 12)))]))
        torso.add(arm)
    claws = solid("#6a6a72")
    torso.add(Part("legs", boxes=[b for x in (3, -6) for b in (
        cuboid((x, 7, -9), (3, 3, 5), skin((3, 3, 5))), cuboid((x, 9, -10), (3, 2, 1), claws))] + [
        b for x in (3, -7) for b in (cuboid((x, -10, -10), (4, 5, 6), skin((4, 5, 6))),
                                     cuboid((x, -7, -11), (4, 3, 1), claws))]), neck)
    root = Part("root", offset=(0, 0, DRAGON_HEIGHT)).add(torso)
    return Unit(key, "Dragon", "Adv. Heavy Crossbowman", "dragon", root, group="easter",
                attack="fire", scale=DRAGON_SCALE)


def fireball(key: str = "fireball") -> Unit:
    """The dragon's fire: a ball of one-pixel blocks, orange flecked with yellow and red, with sparks that flicker."""
    rng = np.random.default_rng(zlib.crc32(key.encode()))
    colours = ["#ff9a1a"] * 11 + ["#ffd84a"] * 5 + ["#e8480c"] * 4
    r = 3.6
    ball = []
    for x in range(-4, 4):
        for y in range(-4, 4):
            for z in range(-4, 4):
                if (x + 0.5) ** 2 + (y + 0.5) ** 2 + (z + 0.5) ** 2 <= r * r:
                    ball.append(cuboid((x, y, z), (1, 1, 1), solid(colours[int(rng.integers(len(colours)))])))
    sparks = [cuboid((x, y, z), (1, 1, 1), solid(c)) for x, y, z, c in (
        (3.5, 1, 1, "#ffd84a"), (-4.5, -1, 0, "#ff6a10"), (0, 3.5, -3, "#ffd84a"), (-1, -4.5, 2, "#ff6a10"))]
    root = Part("root").add(Part("ball", boxes=ball), Part("flame_a", boxes=sparks[:2]),
                            Part("flame_b", boxes=sparks[2:]))
    return Unit(key, "Fire charge", "the dragon's projectile", "fireball", root, group="easter", attack="none")


EASTER = {"pacman": pacman, "ghost": ghost, "cobra_car": cobra_car, "dragon": dragon}
