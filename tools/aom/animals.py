"""Gaia animals: sheep, turkey, deer, wild boar, javelina and wolf as their
closest Minecraft mobs (sheep, chicken, goat, hoglin, pig, wolf)."""
from __future__ import annotations

from .geometry import Part, cuboid
from .textures import PC, Painter
from .units import Unit, solid


def _legs(p: Painter, tex: dict, size, front_y: float, back_y: float, x: float, height: float) -> list[Part]:
    w, d, h = size
    parts = []
    for name, sx, y in (("leg_fr", 1, front_y), ("leg_fl", -1, front_y), ("leg_br", 1, back_y),
                        ("leg_bl", -1, back_y)):
        cx = sx * x
        parts.append(Part(name, pivot=(cx, y, height), boxes=[cuboid((cx - w / 2, y - d / 2, height - h), size, tex)]))
    return parts


def _animal(key: str, name: str, replaces: str, root: Part, attack: str = "bite") -> Unit:
    return Unit(key, name, replaces, "quadruped", root, group="animal", attack=attack)


def sheep(key: str = "sheep", dyed: bool = True) -> Unit:
    p = Painter(key)
    wool = PC(0.85) if dyed else "#ececec"
    wool_d = PC(0.7) if dyed else "#d2d2d2"
    fleece = p.speckle(wool, (wool_d, 0.3))
    skin = "#d9b9a0"
    face = p.grid(["ssssss", "ssssss", "wKssKw", "ssssss", "sspPss", "ssssss"],
                  {"s": skin, "w": "#f5f5f5", "K": "#1a1a1a", "p": "#e79aa0", "P": "#e79aa0"})
    head = p.skin((6, 8, 6), skin, front=face)
    body = p.skin((8, 16, 6), fleece)
    leg = p.skin((4, 4, 12), p.bands((5, fleece), (7, skin)))
    root = Part("root")
    root.add(
        Part("torso", pivot=(0, 0, 12), boxes=[cuboid((-4, -8, 12), (8, 16, 6), body, 1.75)]).add(
            Part("head", pivot=(0, 7, 18), boxes=[cuboid((-3, 6, 16), (6, 8, 6), head),
                                                  cuboid((-3, 6, 16), (6, 6, 6), p.skin((6, 6, 6), fleece), 0.6)])),
        *_legs(p, leg, (4, 4, 12), 5, -5, 3, 12),
    )
    return _animal(key, "Sheep", "Sheep", root, attack="none")


def chicken(key: str = "turkey") -> Unit:
    p = Painter(key)
    feathers = p.speckle("#f0f0f0", ("#d8d8d8", 0.25))
    head = p.skin((4, 3, 6), feathers, front=p.grid(["ffff", "KffK", "ffff", "ffff", "ffff", "ffff"],
                                                     {"f": "#f0f0f0", "K": "#1a1a1a"}))
    leg = p.skin((1, 1, 5), "#e8a030")
    root = Part("root")
    body = Part("torso", pivot=(0, 0, 5), boxes=[cuboid((-3, -4, 5), (6, 8, 6), p.skin((6, 8, 6), feathers)),
                                                 cuboid((3, -3, 7), (1, 6, 4), p.skin((1, 6, 4), feathers)),
                                                 cuboid((-4, -3, 7), (1, 6, 4), p.skin((1, 6, 4), feathers))])
    body.add(Part("head", pivot=(0, 3, 10), boxes=[cuboid((-2, 3, 9), (4, 3, 6), head),
                                                   cuboid((-2, 6, 11), (4, 2, 2), solid("#e8a030")),
                                                   cuboid((-1, 6, 9), (2, 1, 2), solid("#c8302a"))]))
    root.add(body, Part("leg_r", pivot=(1.5, 0, 5), boxes=[cuboid((1, -0.5, 0), (1, 1, 5), leg),
                                                          cuboid((0, -0.5, 0), (3, 3, 0.6), solid("#e8a030"))]),
             Part("leg_l", pivot=(-1.5, 0, 5), boxes=[cuboid((-2, -0.5, 0), (1, 1, 5), leg),
                                                      cuboid((-3, -0.5, 0), (3, 3, 0.6), solid("#e8a030"))]))
    return Unit(key, "Chicken", "Turkey", "biped_animal", root, group="animal", attack="none")


def goat(key: str = "deer") -> Unit:
    p = Painter(key)
    coat = p.speckle("#dcd6ca", ("#bdb5a6", 0.3))
    head = p.skin((5, 9, 6), coat, front=p.grid(["ccccc", "ccccc", "ccccc", "cKcKc", "ccccc", "cdddc"],
                                                 {"c": "#dcd6ca", "K": "#1a1a1a", "d": "#8a8276"}),
                  right=p.grid(["ccccccccc", "ccccccKcc", "ccccccccc", "ccccccccc", "ccccccccc", "ccccccccc"],
                               {"c": "#dcd6ca", "K": "#1a1a1a"}))
    horn = solid("#6e6558")
    leg = p.skin((3, 3, 10), p.bands((8, coat), (2, "#3a3530")))
    root = Part("root")
    root.add(
        Part("torso", pivot=(0, 0, 10), boxes=[cuboid((-4.5, -8, 10), (9, 16, 9), p.skin((9, 16, 9), coat)),
                                               cuboid((-5, 3, 9), (10, 6, 11), p.skin((10, 6, 11), coat))]).add(
            Part("head", pivot=(0, 8, 18), rot=(-25, 0, 0), boxes=[
                cuboid((-2.5, 7, 17), (5, 9, 6), head),
                cuboid((-2, 8, 23), (1.5, 1.5, 6), horn), cuboid((0.5, 8, 23), (1.5, 1.5, 6), horn),
                cuboid((-0.5, 14, 14), (1, 1, 3), solid("#bdb5a6"))])),
        *_legs(p, leg, (3, 3, 10), 5, -6, 2.5, 10),
    )
    return _animal(key, "Goat", "Deer", root, attack="none")


def hoglin(key: str = "wild_boar") -> Unit:
    p = Painter(key)
    hide = p.speckle("#b87660", ("#9a5e4a", 0.3), ("#d4907a", 0.1))
    mane = p.speckle("#e2cf8e", ("#c8b270", 0.3))
    head = p.skin((12, 14, 7), hide, front=p.grid(["hhhhhhhhhhhh", "hhhhhhhhhhhh", "hhhhhhhhhhhh",
                                                   "hddhhhhhhddh", "hhhhhhhhhhhh", "hhhhhhhhhhhh", "hhhhhhhhhhhh"],
                                                  {"h": "#b87660", "d": "#5a2e22"}),
                  right=p.grid(["hhhhhhhhhhhhhh", "hhhhhhhhhhKhhh"] + ["hhhhhhhhhhhhhh"] * 5,
                               {"h": "#b87660", "K": "#1a1a1a"}))
    tusk = solid("#efe6c8")
    leg = p.skin((5, 5, 10), p.bands((8, hide), (2, "#4a3028")))
    root = Part("root")
    root.add(
        Part("torso", pivot=(0, 0, 10), boxes=[cuboid((-7, -11, 10), (14, 22, 13), p.skin((14, 22, 13), hide)),
                                               cuboid((-1, -9, 23), (2, 16, 3), p.skin((2, 16, 3), mane))]).add(
            Part("head", pivot=(0, 10, 18), rot=(-20, 0, 0), boxes=[
                cuboid((-6, 9, 12), (12, 14, 7), head),
                cuboid((-7.5, 12, 16), (2, 3, 4), solid("#9a5e4a")), cuboid((5.5, 12, 16), (2, 3, 4), solid("#9a5e4a")),
                cuboid((-6, 21, 17), (2, 2, 5), tusk), cuboid((4, 21, 17), (2, 2, 5), tusk)])),
        *_legs(p, leg, (5, 5, 10), 7, -7, 4, 10),
    )
    return _animal(key, "Hoglin", "Wild Boar", root, attack="bite")


def pig(key: str = "javelina") -> Unit:
    p = Painter(key)
    skin = p.speckle("#eba3a0", ("#d88a88", 0.3))
    head = p.skin((8, 8, 8), skin, front=p.grid(["pppppppp", "pppppppp", "pwKppKwp", "pppppppp",
                                                 "pppppppp", "pppppppp", "pppppppp", "pppppppp"],
                                                {"p": "#eba3a0", "w": "#f5f5f5", "K": "#1a1a1a"}))
    snout = p.skin((4, 1, 3), "#f2b8b5", front=p.grid(["SSSS", "dSSd", "SSSS"], {"S": "#f2b8b5", "d": "#8a4a48"}))
    leg = p.skin((4, 4, 6), skin)
    root = Part("root")
    root.add(
        Part("torso", pivot=(0, 0, 6), boxes=[cuboid((-5, -8, 6), (10, 16, 8), p.skin((10, 16, 8), skin))]).add(
            Part("head", pivot=(0, 8, 12), boxes=[cuboid((-4, 7, 8), (8, 8, 8), head),
                                                  cuboid((-2, 15, 9), (4, 1, 3), snout)])),
        *_legs(p, leg, (4, 4, 6), 5, -5, 3, 6),
    )
    return _animal(key, "Pig", "Javelina", root, attack="bite")


def wolf(key: str = "wolf") -> Unit:
    p = Painter(key)
    fur = p.speckle("#d9d9d9", ("#b5b5b5", 0.3), ("#8f8f8f", 0.05))
    head = p.skin((6, 4, 6), fur, front=p.grid(["ffffff", "ffffff", "KwffwK", "ffffff", "ffffff", "ffffff"],
                                               {"f": "#d9d9d9", "K": "#1a1a1a", "w": "#f5f5f5"}))
    snout = p.skin((3, 4, 3), fur, front=p.grid(["fff", "fKf", "fff"], {"f": "#d9d9d9", "K": "#1a1a1a"}))
    leg = p.skin((2, 2, 8), fur)
    root = Part("root")
    root.add(
        Part("torso", pivot=(0, 0, 8), boxes=[cuboid((-3, -7, 8), (6, 9, 6), p.skin((6, 9, 6), fur)),
                                              cuboid((-4, 1, 7.5), (8, 6, 7), p.skin((8, 6, 7), fur))]).add(
            Part("head", pivot=(0, 7, 13), boxes=[cuboid((-3, 7, 10), (6, 4, 6), head),
                                                  cuboid((-1.5, 11, 10), (3, 4, 3), snout),
                                                  cuboid((-3, 8, 16), (2, 1, 2), p.skin((2, 1, 2), fur)),
                                                  cuboid((1, 8, 16), (2, 1, 2), p.skin((2, 1, 2), fur))]),
            Part("tail", pivot=(0, -7, 13), rot=(-50, 0, 0), boxes=[cuboid((-1, -8, 5), (2, 2, 8),
                                                                          p.skin((2, 2, 8), fur))])),
        *_legs(p, leg, (2, 2, 8), 4, -5, 1.5, 8),
    )
    return _animal(key, "Wolf", "Wolf", root, attack="bite")


ANIMALS = {
    "sheep": sheep,
    "turkey": chicken,
    "deer": goat,
    "wild_boar": hoglin,
    "javelina": pig,
    "wolf": wolf,
}
