"""Ships: Minecraft boats grown into a fleet, with team-colour wool sails.

Hulls are stepped plank boxes with a pointed bow, sitting on the water line
(z = 0). Every ship carries team colour on its sails, shields or shell rim.
"""
from __future__ import annotations

from . import items
from .geometry import Part, cuboid
from .items import held
from .siege import _tnt
from .textures import PC, Painter, parse
from .units import Unit, solid, worker

WOODS = {  # plank, seam, trim
    "oak": ("#b18d54", "#8a6a3a", "#6b5132"),
    "spruce": ("#7a5a35", "#5c4225", "#3e2c18"),
    "dark_oak": ("#4f3720", "#3a2715", "#231609"),
    "obsidian": ("#241b36", "#150f22", "#4a3a6a"),
}


def planks(p: Painter, wood: str):
    light, seam, _ = WOODS[wood]

    def paint(w: int, h: int):
        tex = p.fill(w, h, light, 0.05)
        tex[3::4] = parse(seam)
        return tex

    return paint


def hull(p: Painter, length: float, width: float, height: float, wood: str = "oak", bow: float = 8) -> list:
    """Flat-bottomed hull with side walls, a stern and a stepped, pointed bow."""
    paint = planks(p, wood)
    trim = WOODS[wood][2]
    wall = 1.5
    y0, y1 = -length / 2, length / 2 - bow
    boxes = [
        cuboid((-width / 2, y0, 0), (width, y1 - y0, 1.5), p.skin((width, y1 - y0, 1.5), paint)),
        cuboid((width / 2 - wall, y0, 0), (wall, y1 - y0, height), p.skin((wall, y1 - y0, height), paint, top=trim)),
        cuboid((-width / 2, y0, 0), (wall, y1 - y0, height), p.skin((wall, y1 - y0, height), paint, top=trim)),
        cuboid((-width / 2, y0, 0), (width, wall, height + 1), p.skin((width, wall, height + 1), paint, top=trim)),
    ]
    for i in range(3):  # bow steps, narrowing toward the prow
        w = width * (1 - (i + 1) / 4)
        ys = y1 + i * bow / 3
        boxes.append(cuboid((-w / 2, ys, 0), (w, bow / 3, height + i * 0.7),
                            p.skin((w, bow / 3, height), paint, top=trim)))
    return boxes


def sail(p: Painter, name: str, at, width: float, height: float, mast: float, pattern: str = "plain") -> Part:
    """Mast with a team-colour wool sail hanging from a yard."""
    x, y, z = at
    rows = {"plain": ["PPPPPPPP"] * 7 + ["DDDDDDDD"],
            "stripes": ["PPPPPPPP", "WWWWWWWW"] * 4,
            "emblem": ["PPPPPPPP", "PPPDDPPP", "PPDLLDPP", "PPDLLDPP", "PPPDDPPP", "PPPPPPPP", "PPPPPPPP",
                       "DDDDDDDD"]}[pattern]
    cloth = p.grid(rows, {"P": PC(0.62), "D": PC(0.38), "L": PC(0.85), "W": "#ececec"})
    faces = {f: cloth for f in ("front", "back", "right", "left", "top", "bottom")}
    top = z + mast
    part = Part(name, pivot=(x, y, top - 1), boxes=[
        cuboid((x - width / 2 - 1, y - 0.5, top - 2), (width + 2, 1, 1), solid("#4e3a22")),  # yard
        cuboid((x - width / 2, y - 1.5, top - 2 - height), (width, 1, height), faces),
    ])
    return Part(name + "_mast", boxes=[cuboid((x - 0.75, y - 0.75, z), (1.5, 1.5, mast), p.skin(
        (1.5, 1.5, mast), p.speckle("#6b5132", ("#4e3a22", 0.3))))]).add(part)


def oars(p: Painter, length: float, width: float, n: int = 3) -> list:
    tex = solid("#8a6a3a")
    boxes = []
    for i in range(n):
        y = -length / 2 + 6 + i * (length - 14) / max(1, n - 1)
        boxes += [cuboid((width / 2, y, 2), (6, 1, 1), tex), cuboid((-width / 2 - 6, y, 2), (6, 1, 1), tex)]
    return boxes


def bow_weapon(p: Painter, y: float, z: float, voxel: float = 1.1) -> Part:
    return Part("weapon", pivot=(0, y, z)).add(held(items.crossbow(voxel=voxel), "ship_bow", (0, y - 3, z), p))


def barrel(p: Painter, x: float, y: float, z: float) -> list:
    return [cuboid((x - 2.5, y - 2.5, z), (5, 5, 6), p.skin((5, 5, 6), p.bands((1, "#3a3a3a"), (4, "#8a6236"),
                                                                              (1, "#3a3a3a")), top="#6b4a2a"))]


SHIP_SIZE = 2.0  # every ship drawn twice as big as first designed (the player asked for bigger ships)


def _ship(key, name, replaces, root, attack="fire", civ=None, scale=1.0) -> Unit:
    return Unit(key, name, replaces, "ship", root, group="ship", attack=attack, civ=civ, scale=scale * SHIP_SIZE)


# --------------------------------------------------------------------------- the fleet

def fishing_ship() -> Unit:
    p = Painter("fishing_ship")
    fisher = worker("fisherman").root
    fisher.name, fisher.offset = "crew", (0, -4, -8)  # seated: hips just above the floor
    fisher.find("leg_r").rot = (80, 0, -10)
    fisher.find("leg_l").rot = (80, 0, 10)
    fisher.find("item_r").rot = (-80, 0, 0)  # rod held out over the side
    torso = fisher.find("torso")
    torso.children = [c for c in torso.children if c.name != "carry"]
    root = Part("root", boxes=hull(p, 24, 12, 5, "oak", 7)).add(fisher, sail(p, "sail", (0, 6, 1.5), 8, 8, 16))
    return _ship("fishing_ship", "Fishing Boat", "Fishing Ship", root, attack="none", scale=1.2)


def transport_ship() -> Unit:
    p = Painter("transport_ship")
    chest = p.skin((6, 6, 6), p.bands((2, "#9a6a34"), (1, "#3a2410"), (3, "#8a5a2a")), top="#a87438")
    cargo = [cuboid((-6, -10, 1.5), (6, 6, 6), chest), cuboid((1, -10, 1.5), (6, 6, 6), chest)] \
        + barrel(p, -4, 2, 1.5) + barrel(p, 3, 3, 1.5)
    root = Part("root", boxes=hull(p, 32, 18, 5, "spruce", 8) + cargo).add(sail(p, "sail", (0, 8, 1.5), 12, 10, 20))
    return _ship("transport_ship", "Cargo Raft", "Transport Ship", root, attack="none", scale=1.2)


def trade_cog() -> Unit:
    p = Painter("trade_cog")
    chest = p.skin((6, 6, 6), p.bands((2, "#9a6a34"), (1, "#3a2410"), (3, "#8a5a2a")), top="#a87438")
    root = Part("root", boxes=hull(p, 30, 14, 7, "oak", 8) + [cuboid((-3, -12, 1.5), (6, 6, 6), chest)]
                + barrel(p, 3, -3, 1.5)).add(sail(p, "sail", (0, 2, 1.5), 12, 12, 24, "emblem"))
    return _ship("trade_cog", "Trading Cog", "Trade Cog", root, attack="none", scale=1.2)


def galley(key: str, name: str, replaces: str, wood: str, length: float, width: float, height: float,
           masts: int = 1, scale: float = 1.2) -> Unit:
    p = Painter(key)
    root = Part("root", boxes=hull(p, length, width, height, wood, 9) + oars(p, length, width, 3 + masts))
    root.add(sail(p, "sail", (0, -2, 1.5), width - 2, 12 + 2 * masts, 22 + 4 * masts, "emblem"))
    if masts > 1:
        root.add(sail(p, "sail_2", (0, -length / 2 + 6, 1.5), width - 4, 9, 18))
    root.add(bow_weapon(p, length / 2 - 11, height + 1.5))
    return _ship(key, name, replaces, root, scale=scale)


def fire_ship(key: str, name: str, replaces: str, soul: bool = False) -> Unit:
    p = Painter(key)
    flame, core = ("#6fe0ff", "#2a9ac8") if soul else ("#ffb030", "#ff6a10")
    campfire = [cuboid((-4, 7, 7), (8, 2, 2), solid("#6b5132")), cuboid((-1, 4, 7), (2, 8, 2), solid("#6b5132")),
                cuboid((-3, 5, 9), (6, 6, 5), p.skin((6, 6, 5), p.speckle(core, (flame, 0.4)))),
                cuboid((-1.5, 6.5, 14), (3, 3, 4), solid(flame))]
    root = Part("root", boxes=hull(p, 30, 12, 6, "spruce" if soul else "oak", 9) + oars(p, 30, 12, 3))
    root.add(Part("weapon", pivot=(0, 8, 7), boxes=campfire), sail(p, "sail", (0, -5, 1.5), 10, 11, 20))
    return _ship(key, name, replaces, root, scale=1.2)


def demolition_ship(key: str, name: str, replaces: str, heavy: bool = False) -> Unit:
    p = Painter(key)
    tnt = _tnt(p)
    boxes = hull(p, 26, 12, 5, "obsidian" if heavy else "dark_oak", 7)
    spots = [(-5, -8), (0, -8), (-5, -2), (0, -2)] + ([(-2.5, 4), (-2.5, -5)] if heavy else [])
    for i, (x, y) in enumerate(spots):
        boxes.append(cuboid((x, y, 1.5 + (5 if i >= 4 else 0)), (5, 5, 5), tnt))
    root = Part("root", boxes=boxes).add(Part("weapon"), sail(p, "sail", (0, 8, 1.5), 7, 7, 14))
    return _ship(key, name, replaces, root, attack="explode", scale=1.1)


def cannon_galleon(key: str, name: str, replaces: str, elite: bool = False) -> Unit:
    p = Painter(key)
    obsidian = p.speckle("#1f1830", ("#3a2a5a", 0.2), ("#0e0a16", 0.2))
    muzzle = p.skin((7, 2, 7), "#bdbdbd")
    muzzle["front"][2:5, 2:5] = parse("#050505")
    barrels = [0] if not elite else [-3.5, 3.5]
    weapon = Part("weapon", pivot=(0, 10, 9))
    for x in barrels:
        weapon.boxes += [cuboid((x - 2.5, 4, 7), (5, 16, 5), p.skin((5, 16, 5), obsidian)),
                         cuboid((x - 3.5, 20, 6), (7, 2, 7), muzzle)]
    root = Part("root", boxes=hull(p, 40, 15, 8, "dark_oak", 9))
    root.add(weapon, sail(p, "sail", (0, -4, 1.5), 13, 14, 28, "emblem"),
             sail(p, "sail_2", (0, -15, 1.5), 10, 10, 20))
    return _ship(key, name, replaces, root, scale=1.3)


def longboat() -> Unit:
    p = Painter("longboat")
    boxes = hull(p, 40, 10, 5, "spruce", 10)
    shield = p.skin((1, 4, 4), p.grid(["PPPP", "PKKP", "PKKP", "PPPP"], {"P": PC(0.6), "K": "#6a6a6a"}))
    for i in range(5):
        y = -16 + i * 5.5
        boxes += [cuboid((5, y, 2.5), (1, 4, 4), shield), cuboid((-6, y, 2.5), (1, 4, 4), shield)]
    boxes += [cuboid((-1, 16, 5), (2, 4, 6), solid("#3e2c18")), cuboid((-1.5, 18, 10), (3, 4, 3), solid("#3e2c18"))]
    root = Part("root", boxes=boxes + oars(p, 40, 10, 4)).add(sail(p, "sail", (0, -2, 1.5), 12, 12, 24, "stripes"),
                                                              bow_weapon(p, 8, 6.5))
    return _ship("longboat", "Spruce Longship", "Longboat", root, civ="Vikings", scale=1.2)


def turtle_ship() -> Unit:
    p = Painter("turtle_ship")
    scutes = p.grid(["gGgggGgg", "GGGgGGGg", "gGgggGgg", "ggGgggGg", "gGGGgGGG", "ggGgggGg"],
                    {"g": "#4f8f3a", "G": "#2f6a2a"})
    shell = {f: scutes for f in ("front", "back", "right", "left", "top", "bottom")}
    rim = p.skin((15, 30, 1.5), PC(0.6))
    boxes = hull(p, 38, 14, 5, "dark_oak", 8) + [
        cuboid((-7.5, -17, 5), (15, 30, 1.5), rim),
        cuboid((-7, -16.5, 6.5), (14, 29, 4), shell), cuboid((-5, -14, 10.5), (10, 24, 3), shell),
        cuboid((-2, 15, 5), (4, 4, 4), solid("#b8a030")), cuboid((-1.5, 18, 6), (3, 3, 3), solid("#d8342a"))]
    for i in range(4):
        boxes.append(cuboid((-0.5, -12 + i * 6, 13.5), (1, 1, 2), solid("#bdbdbd")))
    muzzle = p.skin((4, 2, 4), "#3a3a3a")
    root = Part("root", boxes=boxes).add(Part("weapon", pivot=(0, 12, 8), boxes=[
        cuboid((5, -6, 7), (4, 2, 4), muzzle), cuboid((-9, -6, 7), (4, 2, 4), muzzle)]))
    return _ship("turtle_ship", "Turtle-Shell Ship", "Turtle Ship", root, civ="Koreans", scale=1.3)


SHIPS = {
    "fishing_ship": fishing_ship,
    "transport_ship": transport_ship,
    "trade_cog": trade_cog,
    "galley": lambda: galley("galley", "Oak Galley", "Galley", "oak", 30, 12, 6),
    "war_galley": lambda: galley("war_galley", "Spruce War Galley", "War Galley", "spruce", 34, 13, 7, 2),
    "galleon": lambda: galley("galleon", "Dark Oak Galleon", "Galleon", "dark_oak", 40, 15, 9, 2, scale=1.3),
    "fire_ship": lambda: fire_ship("fire_ship", "Campfire Ship", "Fire Ship"),
    "fast_fire_ship": lambda: fire_ship("fast_fire_ship", "Soul-Fire Ship", "Fast Fire Ship", soul=True),
    "demolition_ship": lambda: demolition_ship("demolition_ship", "TNT Boat", "Demolition Ship"),
    "heavy_demolition_ship": lambda: demolition_ship("heavy_demolition_ship", "Obsidian TNT Boat",
                                                     "Heavy Demolition Ship", True),
    "cannon_galleon": lambda: cannon_galleon("cannon_galleon", "TNT Galleon", "Cannon Galleon"),
    "elite_cannon_galleon": lambda: cannon_galleon("elite_cannon_galleon", "Twin-TNT Galleon",
                                                   "Elite Cannon Galleon", True),
    "longboat": longboat,
    "turtle_ship": turtle_ship,
}
