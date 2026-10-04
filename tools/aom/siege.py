"""Siege weapons and wagons, built from Minecraft blocks and mobs.

    Battering Ram line  -> Ravager (bare, iron-capped, netherite-plated)
    Mangonel line       -> Dispenser carts (stone, iron, obsidian)
    Scorpion line       -> Giant crossbow turrets
    Bombard Cannon      -> TNT cannon with an obsidian barrel
    Trebuchet           -> Log-frame trebuchet with a team-colour counterweight
    War Wagon           -> Covered wagon with a team-colour wool canopy
    Trade Cart          -> A train: a furnace minecart pulling a chest minecart, laying its own rails (rails.py)
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import items
from .geometry import Part, cuboid
from .items import held
from .mounted import horse
from .rails import TRAIN_SCALE
from .textures import PC, Painter, layered, parse
from .units import ARMOUR, Unit, rows_only, solid


# --------------------------------------------------------------------------- shared parts

def wheel(p: Painter, name: str, centre, radius: float = 4.0, thickness: float = 2.0,
          rim: str = "#4a3520", wood: str = "#8a6a3a") -> Part:
    """A round, spoked wheel: one box whose circular side faces cut away the corners."""
    n = int(round(radius * 2))
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.hypot(xx + 0.5 - n / 2, yy + 0.5 - n / 2)
    side = p.fill(n, n, wood, 0.05)
    side[(np.abs(xx + 0.5 - n / 2) < 0.8) | (np.abs(yy + 0.5 - n / 2) < 0.8)] = parse(rim)  # spokes
    side[np.abs(np.abs(xx + 0.5 - n / 2) - np.abs(yy + 0.5 - n / 2)) < 0.6] = parse(rim)
    side[d >= radius - 1.2] = parse(rim)
    side[d < 1.2] = parse("#6a6a6a")  # hub
    side[d > radius] = 0
    tread = p.fill(max(1, int(round(thickness))), n, rim, 0.05)  # rows run around the rim
    band = np.abs(np.arange(n) + 0.5 - n / 2) < radius * 0.45
    tread[~band] = 0  # rim faces only exist where the circle touches them
    faces = {"right": side, "left": side[:, ::-1].copy(), "front": tread, "back": tread,
             "top": tread, "bottom": tread}
    x, y, z = centre
    return Part(name, pivot=centre, boxes=[cuboid((x - thickness / 2, y - radius, z - radius),
                                                  (thickness, 2 * radius, 2 * radius), faces)])


def flag(p: Painter, at, height: float = 18, width: float = 7) -> Part:
    """Team flag on a pole; `at` is the foot of the pole. The cloth trails backward."""
    x, y, z = at
    cloth = p.grid(["PPPPPPP", "PDDPPPP", "PDLDPPP", "PDDPPPP", "PPPPPPP"],
                   {"P": PC(0.6), "D": PC(0.38), "L": PC(0.85)})
    faces = {f: cloth for f in ("front", "back", "right", "left", "top", "bottom")}
    return Part("flag", boxes=[cuboid((x - 0.5, y - 0.5, z), (1, 1, height), solid(items.STICK)),
                               cuboid((x - 0.4, y - 0.5 - width, z + height - 5.5), (0.8, width, 5), faces)])


def _tnt(p: Painter) -> dict:
    side = p.grid(["RRRRRRRR", "RrRRrRRR", "WWWWWWWW", "KKKWKWKK", "WKWWKKWK", "WKWWKWKK", "WWWWWWWW",
                   "RRRrRRRR"], {"R": "#d8321f", "r": "#b02414", "W": "#ececec", "K": "#1e1e1e"})
    top = p.grid(["GGGGGGGG", "GggggggG", "GgGGGGgG", "GgGKKGgG", "GgGKKGgG", "GgGGGGgG", "GggggggG",
                  "GGGGGGGG"], {"G": "#b8b8b8", "g": "#d8321f", "K": "#3a3a3a"})
    return {"front": side, "back": side, "right": side, "left": side, "top": top, "bottom": top}


def _dispenser(p: Painter, stone: str, dark: str) -> dict:
    side = p.speckle(stone, (dark, 0.3))(10, 10)
    face = p.speckle(stone, (dark, 0.3))(10, 10)
    face[3:7, 3:7] = parse("#1a1a1a")
    face[3, 3:7] = face[3:7, 3] = parse(dark)
    top = p.fill(10, 10, stone, 0.06)
    return {"front": face, "back": side, "right": side, "left": side, "top": top, "bottom": top}


def _cart(p: Painter, x0, y0, z0, w, d, h, metal: str, rim: str, inner: str) -> list:
    """Open-topped minecart tub: floor plus four 1.5-thick walls."""
    wall = p.skin((w, 1.5, h), p.bands((1, rim), (h - 2, p.speckle(metal, (rim, 0.15))), (1, rim)),
                  top=rim, bottom=rim)
    side = p.skin((1.5, d, h), p.bands((1, rim), (h - 2, p.speckle(metal, (rim, 0.15))), (1, rim)),
                  top=rim, bottom=rim)
    floor = p.skin((w, d, 1.5), inner, bottom=rim)
    return [cuboid((x0, y0, z0), (w, d, 1.5), floor),
            cuboid((x0, y0 + d - 1.5, z0), (w, 1.5, h), wall), cuboid((x0, y0, z0), (w, 1.5, h), wall),
            cuboid((x0, y0, z0), (1.5, d, h), side), cuboid((x0 + w - 1.5, y0, z0), (1.5, d, h), side)]


def _wheels(p: Painter, positions, radius: float, **kw) -> list[Part]:
    return [wheel(p, f"wheel_{i + 1}", c, radius, **kw) for i, c in enumerate(positions)]


def _siege(key, name, replaces, root, attack="fire", civ=None, rig="wheeled", scale=1.0) -> Unit:
    return Unit(key, name, replaces, rig, root, group="siege", attack=attack, civ=civ, scale=scale)


# --------------------------------------------------------------------------- ram line: ravagers

def ravager(key: str, name: str, replaces: str, plate: Optional[str] = None) -> Unit:
    p = Painter(key)
    hide = p.speckle("#5a5650", ("#48453f", 0.3), ("#6e6a62", 0.1))
    legend = {"h": "#5a5650", "K": "#141414", "g": "#3fae5a", "t": "#e8e2cc", "T": "#5a5650", "n": "#2e2b28"}
    skull = p.skin((14, 14, 14), hide,
                   front=p.grid(["hhhhhhhhhhhhhh"] * 4 + ["hhKKhhhhhhKKhh", "hhKghhhhhhgKhh"]
                                + ["hhhhhhhhhhhhhh"] * 8, legend))
    jaw = p.skin((14, 14, 4), hide, front=p.grid(["tTtTtTtTtTtTtT", "hhhhhhhhhhhhhh", "hhhhhhhhhhhhhh",
                                                  "hhhhhhhhhhhhhh"], legend))
    if plate:
        mat = ARMOUR[plate](p)
        skull = layered(skull, p.skin((14, 14, 14), mat, bottom=None, back=None,
                                      front=rows_only(p, mat, 0, 3), right=rows_only(p, mat, 0, 5)))
    harness = p.skin((16, 24, 16), hide,
                     top=p.grid(["hhhhhhhhhhhhhhhh"] * 7 + ["hhhPPPPPPPPPPhhh"] * 10 + ["hhhhhhhhhhhhhhhh"] * 7,
                                {"h": "#5a5650", "P": PC(0.6)}),
                     right=p.grid(["hhhhhhhPPPhhhhhhhhhhhhhh"] * 3 + ["hhhhhhhPPPhhhhhhhhhhhhhh"] * 9
                                  + ["hhhhhhhDDDhhhhhhhhhhhhhh"] + ["hhhhhhhhhhhhhhhhhhhhhhhh"] * 3,
                                  {"h": "#5a5650", "P": PC(0.6), "D": PC(0.38)}))
    if plate == "netherite":  # siege ram: plated flanks too
        harness = layered(harness, p.skin((16, 24, 16), rows_only(p, ARMOUR[plate](p), 0, 4), top=None,
                                          bottom=None))
    horn = solid("#d8cfae")
    leg = p.skin((6, 6, 13), p.bands((11, hide), (2, "#2e2b28")))
    root = Part("root")
    torso = Part("torso", pivot=(0, 0, 13), boxes=[cuboid((-8, -13, 13), (16, 24, 16), harness),
                                                   cuboid((-6, 8, 18), (12, 8, 12), p.skin((12, 8, 12), hide))])
    torso.add(Part("head", pivot=(0, 12, 24), boxes=[
        cuboid((-7, 14, 15), (14, 14, 14), skull), cuboid((-7, 14, 11), (14, 14, 4), jaw),
        cuboid((-2, 28, 19), (4, 2, 5), solid("#2e2b28")),
        cuboid((7, 17, 24), (2.5, 3, 3), horn), cuboid((8.5, 17, 27), (2.5, 3, 8), horn),
        cuboid((-9.5, 17, 24), (2.5, 3, 3), horn), cuboid((-11, 17, 27), (2.5, 3, 8), horn),
    ]))
    root.add(torso,
             Part("leg_fr", pivot=(4.5, 6, 13), boxes=[cuboid((1.5, 3, 0), (6, 6, 13), leg)]),
             Part("leg_fl", pivot=(-4.5, 6, 13), boxes=[cuboid((-7.5, 3, 0), (6, 6, 13), leg)]),
             Part("leg_br", pivot=(4.5, -9, 13), boxes=[cuboid((1.5, -12, 0), (6, 6, 13), leg)]),
             Part("leg_bl", pivot=(-4.5, -9, 13), boxes=[cuboid((-7.5, -12, 0), (6, 6, 13), leg)]))
    return _siege(key, name, replaces, root, attack="ram", rig="ravager", scale=1.1)


# --------------------------------------------------------------------------- mangonel line: dispenser carts

def dispenser_cart(key: str, name: str, replaces: str, tier: int) -> Unit:
    p = Painter(key)
    metal, rim, inner = {1: ("#8a8a8a", "#5a5a5a", "#3e3e3e"), 2: ("#c9c9c9", "#8a8a8a", "#4a4a4a"),
                         3: ("#4d4649", "#2f2a2d", "#1e1a1c")}[tier]
    stone, dark = {1: ("#8a8a8a", "#6a6a6a"), 2: ("#9a9a9a", "#6a6a6a"), 3: ("#2a1f3a", "#140e1e")}[tier]
    body = Part("body", boxes=_cart(p, -7, -10, 4, 14, 20, 7, metal, rim, inner))
    for i in range(tier):
        body.boxes.append(cuboid((-6 + i * 4, -9, 5.5), (5, 5, 5), _tnt(p)))
    weapon = Part("weapon", pivot=(0, 2, 6), rot=(25, 0, 0),
                  boxes=[cuboid((-5, -2, 5.5), (10, 10, 10), _dispenser(p, stone, dark))])
    if tier == 3:  # obsidian dispenser in a netherite frame
        weapon.boxes.append(cuboid((-5.5, 7.5, 5), (11, 1, 11), p.skin((11, 1, 11), "#4d4649",
                                                                         front=p.grid(["NNNNNNNNNNN"] + ["N.........N"] * 9
                                                                                      + ["NNNNNNNNNNN"],
                                                                                      {"N": "#4d4649", ".": None}))))
    body.add(weapon, flag(p, (-5.5, -8.5, 11)))
    root = Part("root").add(body, *_wheels(p, [(7.8, 6, 4), (-7.8, 6, 4), (7.8, -6, 4), (-7.8, -6, 4)], 4))
    return _siege(key, name, replaces, root, scale=1.6)


# --------------------------------------------------------------------------- scorpions: crossbow turrets

def crossbow_turret(key: str, name: str, replaces: str, heavy: bool = False) -> Unit:
    p = Painter(key)
    planks = p.skin((12, 16, 3), p.bands(*[(1, "#7a5a35" if i % 3 else "#5c4225") for i in range(3)]),
                    top=p.grid(["PPPPPPPPPPPP", "pppppppppppp"] * 8, {"P": "#7a5a35", "p": "#6b4e2d"}))
    body = Part("body", boxes=[cuboid((-6, -8, 4), (12, 16, 3), planks),
                               cuboid((-1.5, -1.5, 7), (3, 3, 5), p.skin((3, 3, 5), "#6b5132"))])
    bow = items.crossbow(limb="#d8d8d8" if heavy else "#8f6537", voxel=1.35)
    weapon = Part("weapon", pivot=(0, -5, 13)).add(held(bow, "bolt_thrower", (0, -5, 13), p))
    body.add(weapon, flag(p, (-5.5, -7.5, 7), height=14))
    if heavy:
        body.boxes += [cuboid((-6.5, -8.5, 3.5), (1, 17, 4), solid("#b8b8b8")),
                       cuboid((5.5, -8.5, 3.5), (1, 17, 4), solid("#b8b8b8"))]
    root = Part("root").add(body, *_wheels(p, [(7, 5, 4), (-7, 5, 4), (7, -5, 4), (-7, -5, 4)], 4))
    return _siege(key, name, replaces, root, scale=1.5)


# --------------------------------------------------------------------------- bombard cannon: TNT cannon

def tnt_cannon(key: str = "bombard_cannon") -> Unit:
    p = Painter(key)
    obsidian = p.speckle("#1f1830", ("#3a2a5a", 0.2), ("#0e0a16", 0.2))
    iron = p.speckle("#bdbdbd", ("#8a8a8a", 0.3))
    carriage = p.skin((8, 16, 5), p.speckle("#6b4e2d", ("#5c4225", 0.3)))
    body = Part("body", boxes=[cuboid((-4, -10, 4), (8, 16, 5), carriage),
                               cuboid((-2, -18, 1), (4, 8, 4), p.skin((4, 8, 4), "#5c4225")),
                               cuboid((-3, -17, 5), (6, 6, 6), _tnt(p))])
    muzzle = p.skin((9, 3, 9), iron)
    muzzle["front"][3:6, 3:6] = parse("#050505")
    weapon = Part("weapon", pivot=(0, 0, 11), rot=(8, 0, 0), boxes=[
        cuboid((-3.5, -8, 7.5), (7, 22, 7), p.skin((7, 22, 7), obsidian)),
        cuboid((-4.5, 12, 6.5), (9, 3, 9), muzzle),
        cuboid((-4.5, -8, 6.5), (9, 2, 9), p.skin((9, 2, 9), iron)),
        cuboid((-4, 3, 7), (8, 1.5, 8), p.skin((8, 1.5, 8), iron)),
    ])
    body.add(weapon, flag(p, (3.5, -9, 9), height=14))
    root = Part("root").add(body, *_wheels(p, [(5.5, 0, 6.5), (-5.5, 0, 6.5)], 6.5))
    return _siege(key, "TNT Cannon", "Bombard Cannon", root, scale=1.5)


# --------------------------------------------------------------------------- trebuchet

def trebuchet(key: str = "trebuchet") -> Unit:
    p = Painter(key)
    beam = p.skin((3, 36, 3), p.speckle("#6b5132", ("#4e3a22", 0.35)))
    cross = p.skin((16, 3, 3), p.speckle("#6b5132", ("#4e3a22", 0.35)))
    stripped = p.skin((3, 44, 3), p.speckle("#b8955e", ("#9c7c4c", 0.3)))
    upright = p.skin((3, 3, 39), p.speckle("#6b5132", ("#4e3a22", 0.35)))
    crate = p.skin((10, 10, 10), p.bands((1, "#5a5a5a"), (8, PC(0.6)), (1, "#5a5a5a")),
                   top=p.speckle("#8a8a8a", ("#6a6a6a", 0.3)))
    base = Part("base", boxes=[cuboid((5, -18, 2), (3, 36, 3), beam), cuboid((-8, -18, 2), (3, 36, 3), beam),
                               cuboid((-8, 14, 2), (16, 3, 3), cross), cuboid((-8, -17, 2), (16, 3, 3), cross)])
    frame = Part("frame", pivot=(0, 0, 4), boxes=[cuboid((5, -1.5, 5), (3, 3, 39), upright),
                                                  cuboid((-8, -1.5, 5), (3, 3, 39), upright),
                                                  cuboid((-9, -1, 41), (18, 2, 2), solid("#4e3a22"))])
    for sx in (1, -1):
        x = sx * 6.5 - 1
        frame.add(Part(f"brace_f{sx}", pivot=(x + 1, 12, 5), rot=(20, 0, 0),
                       boxes=[cuboid((x, 11, 5), (2, 2, 33), p.skin((2, 2, 33), "#5c4225"))]),
                  Part(f"brace_b{sx}", pivot=(x + 1, -12, 5), rot=(-20, 0, 0),
                       boxes=[cuboid((x, -13, 5), (2, 2, 33), p.skin((2, 2, 33), "#5c4225"))]))
    arm = Part("arm", pivot=(0, 0, 42), boxes=[cuboid((-1.5, -34, 40.5), (3, 44, 3), stripped)])
    arm.add(Part("counterweight", pivot=(0, 9, 42), boxes=[
        cuboid((-2.5, 8.5, 34), (1, 1, 8), solid("#3a3a3a")), cuboid((1.5, 8.5, 34), (1, 1, 8), solid("#3a3a3a")),
        cuboid((-5, 4, 24), (10, 10, 10), crate)]),
        Part("sling", pivot=(0, -33, 42), boxes=[cuboid((-0.4, -33.4, 34), (0.8, 0.8, 8), solid("#d8d0b8")),
                                                  cuboid((-2.5, -35.5, 29), (5, 5, 5), _tnt(p))]))
    frame.add(arm, flag(p, (6.5, 0, 44), height=12))
    root = Part("root").add(base, frame, *_wheels(p, [(9.5, 14, 3), (-9.5, 14, 3), (9.5, -14, 3), (-9.5, -14, 3)],
                                                  3))
    return _siege(key, "Trebuchet", "Trebuchet", root, rig="trebuchet", scale=1.5)


# --------------------------------------------------------------------------- wagons

def _draught(p: Painter, coat: str, y: float, donkey: bool = False) -> Part:
    animal = horse(p, coat, donkey=donkey)
    animal.name = "draught"
    animal.offset = (0, y, 0)
    return animal


def war_wagon(key: str = "war_wagon") -> Unit:
    p = Painter(key)
    planks = p.speckle("#7a5a35", ("#5c4225", 0.3))
    wall = p.skin((14, 1.5, 8), planks, front=p.grid(["pppppppppppppp"] * 3 + ["ppKpppKppppKpp"] * 2
                                                     + ["pppppppppppppp"] * 3, {"p": "#7a5a35", "K": "#1a1a1a"}))
    side = p.skin((1.5, 20, 8), planks, right=p.grid(["pppppppppppppppppppp"] * 3
                                                     + ["ppKpppppKppppppKpppp"] * 2 + ["pppppppppppppppppppp"] * 3,
                                                     {"p": "#7a5a35", "K": "#1a1a1a"}))
    canopy = p.skin((15, 20, 6), p.bands((1, PC(0.45)), (5, PC(0.65))), top=PC(0.7),
                    front=p.grid(["..PPPPPPPPPPP..", ".PPPPPPPPPPPPP.", "PPPPPPPPPPPPPPP", "PPPPPPPPPPPPPPP",
                                  "PPPPPPPPPPPPPPP", "DDDDDDDDDDDDDDD"], {"P": PC(0.65), "D": PC(0.4), ".": None}))
    body = Part("body", boxes=[cuboid((-7, -12, 5), (14, 20, 2), p.skin((14, 20, 2), planks)),
                               cuboid((-7, 6.5, 7), (14, 1.5, 8), wall), cuboid((-7, -12, 7), (14, 1.5, 8), wall),
                               cuboid((-7, -12, 7), (1.5, 20, 8), side), cuboid((5.5, -12, 7), (1.5, 20, 8), side),
                               cuboid((-7.5, -12, 15), (15, 20, 6), canopy),
                               cuboid((-5, -12, 21), (10, 20, 2), p.skin((10, 20, 2), PC(0.72))),
                               cuboid((5.5, 8, 9), (1, 14, 1), solid(items.STICK)),
                               cuboid((-6.5, 8, 9), (1, 14, 1), solid(items.STICK))])
    body.add(Part("weapon", pivot=(0, 8, 14)).add(held(items.crossbow(voxel=1.0), "slit_bow", (0, 7, 13), p)))
    root = Part("root").add(body, _draught(p, "brown", 26),
                            *_wheels(p, [(8, 3, 4.5), (-8, 3, 4.5), (8, -8, 4.5), (-8, -8, 4.5)], 4.5))
    return _siege(key, "Armoured Wagon", "War Wagon", root, civ="Koreans")


def _furnace(p: Painter) -> dict:
    """Minecraft's lit furnace: cobblestone, its mouth at the front glowing with fire."""
    stone = p.speckle("#7c7c7c", ("#5e5e5e", 0.3), ("#9a9a9a", 0.15))
    mouth = p.grid(["SSSSSSSSSS", "SDDDDDDDDS", "SSSSSSSSSS", "SSSSSSSSSS", "SSKKKKKKSS", "SSKOYYOKSS",
                    "SSKYOOYKSS", "SSKKKKKKSS", "SSSSSSSSSS", "SDDDDDDDDS"],
                   {"S": "#7c7c7c", "D": "#5a5a5a", "K": "#2a2a2a", "O": "#f08a1c", "Y": "#ffd23a"})
    return p.skin((10, 10, 10), stone, top=p.speckle("#6e6e6e", ("#8a8a8a", 0.25)), front=mouth)


def trade_cart(key: str = "trade_cart") -> Unit:
    """A Minecraft train: a furnace minecart, smoking as it goes, pulling the chest minecart of goods."""
    p = Painter(key)
    chest = p.skin((9, 8, 8), p.bands((3, "#9a6a34"), (1, "#3a2410"), (4, "#8a5a2a")), top="#a87438",
                   front=p.grid(["wwwwwwwww", "wwwwwwwww", "wwwwwwwww", "KKKKGKKKK", "wwwwGwwww", "wwwwwwwww",
                                 "wwwwwwwww", "wwwwwwwww"], {"w": "#8a5a2a", "K": "#3a2410", "G": "#c8c8c8"}))
    iron = solid("#3a3a3a")
    engine = Part("body", boxes=_cart(p, -6, 2, 2.5, 12, 14, 6, "#8a8a8a", "#5a5a5a", "#3e3e3e")
                  + [cuboid((-5, 4, 4), (10, 10, 10), _furnace(p)),
                     cuboid((-1.5, 9, 14), (3, 3, 6), p.skin((3, 3, 6), p.bands((1, "#2a2a2a"), (5, "#4a4a4a")),
                                                            top="#1a1a1a")),  # a chimney
                     cuboid((-1, -3, 4.5), (2, 6, 1.5), iron)])  # the coupling
    puff = p.speckle("#d8d8d8", ("#b4b4b4", 0.3))
    for k in (1, 2):  # smoke from the chimney (it rises as the train goes: animation.SMOKE)
        engine.add(Part(f"smoke_{k}", boxes=[cuboid((-2.5, 8, 20), (5, 5, 5), p.skin((5, 5, 5), puff))]))
    wagon = Part("wagon", boxes=_cart(p, -6, -16, 2.5, 12, 14, 6, "#8a8a8a", "#5a5a5a", "#3e3e3e")
                 + [cuboid((-4.5, -13, 4), (9, 8, 8), chest),
                    cuboid((-1, -10, 12), (2, 2, 2), solid("#3ad06a"))])  # an emerald on top
    wagon.add(flag(p, (-4.5, -15, 8.5), height=12))
    engine.add(wagon)
    root = Part("root").add(engine, *_wheels(p, [(6.5, 13, 2.5), (-6.5, 13, 2.5), (6.5, 5, 2.5), (-6.5, 5, 2.5),
                                                 (6.5, -5, 2.5), (-6.5, -5, 2.5), (6.5, -13, 2.5),
                                                 (-6.5, -13, 2.5)], 2.5, rim="#2e2e2e", wood="#5a5a5a"))
    return _siege(key, "Minecart Train", "Trade Cart", root, attack="none", scale=TRAIN_SCALE)


SIEGE = {
    "battering_ram": lambda: ravager("battering_ram", "Ravager", "Battering Ram"),
    "capped_ram": lambda: ravager("capped_ram", "Iron-Capped Ravager", "Capped Ram", "iron"),
    "siege_ram": lambda: ravager("siege_ram", "Netherite Ravager", "Siege Ram", "netherite"),
    "mangonel": lambda: dispenser_cart("mangonel", "Dispenser Cart", "Mangonel", 1),
    "onager": lambda: dispenser_cart("onager", "Iron Dispenser Cart", "Onager", 2),
    "siege_onager": lambda: dispenser_cart("siege_onager", "Obsidian Dispenser Cart", "Siege Onager", 3),
    "scorpion": lambda: crossbow_turret("scorpion", "Crossbow Turret", "Scorpion"),
    "heavy_scorpion": lambda: crossbow_turret("heavy_scorpion", "Iron Crossbow Turret", "Heavy Scorpion", True),
    "bombard_cannon": tnt_cannon,
    "trebuchet": trebuchet,
    "war_wagon": war_wagon,
    "trade_cart": trade_cart,
}
