"""Mounted units: riders on Minecraft horses, donkeys, zombie horses and llamas.

The horse follows Minecraft's proportions: a 10x10x22 body on 11-pixel legs,
a neck and head tilted 30 degrees forward, and a hanging tail. The rider is
any foot unit, re-seated with its legs forward the way Minecraft draws a
player on horseback. Team colour shows on the saddle blanket (horses) or the
carpet (llamas), and on the rider.
"""
from __future__ import annotations

from typing import Optional

from . import items
from .geometry import Part, cuboid
from .textures import PC, Painter, layered
from .units import (ARMOUR, Unit, biped, cleric, crafter, masked, pillager, rows_only, skeleton_archer,
                    zombie_look)

COATS = {  # coat, shade, mane, muzzle
    "brown": ("#8a5a2f", "#6e4624", "#3a2414", "#5b3a20"),
    "chestnut": ("#a8612f", "#8a4d24", "#5a2e14", "#6e3a1c"),
    "black": ("#3a3330", "#2b2522", "#161312", "#241e1c"),
    "white": ("#e2ddd2", "#c8c1b4", "#b8b0a2", "#9c9488"),
    "grey": ("#8d8a86", "#74716d", "#4a4745", "#b8b3ac"),  # donkey
    "zombie": ("#5f7f52", "#4a6640", "#2e3f28", "#40573a"),
    "skeleton": ("#d6d3c4", "#b3ae9c", "#d6d3c4", "#a8a392"),
}
SADDLE, SADDLE_DARK, HOOF = "#6b3f1d", "#4a2a12", "#2e2a26"
SEAT_HORSE = 10  # rider hips (z=12) lifted onto the saddle
SEAT_LLAMA = 12


def horse(p: Painter, coat: str = "brown", armour: Optional[str] = None, donkey: bool = False) -> Part:
    base, shade, mane, muzzle = COATS[coat]
    bones = coat == "skeleton"
    hide = p.speckle(base, (shade, 0.25))
    if bones:  # ribs and gaps instead of a coat
        hide = p.bands(*[(1, "#8a8676" if i % 2 else base) for i in range(10)])
    if coat == "zombie":  # rotting patches
        hide = p.speckle(base, (shade, 0.3), ("#2e3f28", 0.1), ("#8a9a7a", 0.05))

    blanket = PC(0.6)
    body = p.skin((10, 22, 10), hide,
                  right=p.grid(["cccccccbbbbbbbbccccccc"] + ["cccccccPPPPPPPPccccccc"] * 5
                               + ["cccccccDDDDDDDDccccccc"] + ["cccccccccccccccccccccc"] * 3,
                               {"c": base, "b": SADDLE_DARK, "P": blanket, "D": PC(0.38)}),
                  top=p.grid(["cccccccccc"] * 7 + ["PPssssssPP"] * 8 + ["cccccccccc"] * 7,
                             {"c": base, "P": blanket, "s": SADDLE}))
    eye = {"c": base, "K": "#101010", "w": "#e8e8e8", "D": "#1e1e1e", "r": "#a52a1a"}
    head = p.skin((6, 7, 5), hide, right=p.grid(
        ["cccccDD", "ccccDDD", "cccccDD", "ccccccc", "ccccccc"] if bones else
        ["cccccKK", "ccccKrK" if coat == "zombie" else "ccccKwK", "cccccKK", "ccccccc", "ccccccc"], eye))
    snout = p.skin((4, 6, 5), muzzle if not bones else base,
                   front=p.grid(["mmmm", "mmmm", "KmmK", "mmmm", "mmmm"], {"m": muzzle if not bones else base,
                                                                         "K": "#101010"}))
    neck = p.skin((4, 7, 12), hide)
    mane_tex = p.skin((2, 2, 16), p.speckle(mane, (shade, 0.15)))
    leg = p.skin((4, 4, 11), p.bands((9, hide), (2, HOOF if not bones else "#8a8676")))
    tail = p.skin((3, 4, 14), p.speckle(mane, (shade, 0.2)))

    if armour:
        mat = ARMOUR[armour](p)
        head = layered(head, p.skin((6, 7, 5), mat, bottom=None))
        snout = layered(snout, p.skin((4, 6, 5), mat, bottom=None,
                                      front=masked(p, mat, ["aaaa", "a..a", "....", "....", "...."])))
        neck = layered(neck, p.skin((4, 7, 12), mat, top=None, bottom=None, back=masked(p, mat, ["...."] * 12)))
        body = layered(body, p.skin((10, 22, 10), rows_only(p, mat, 0, 6), top=None, bottom=None,
                                    right=masked(p, mat, ["aaaaaaa.........aaaaaa"] * 7 + ["." * 22] * 3)))

    ear_h = 6 if donkey else 3
    root = Part("root")
    body_part = Part("horse_body", pivot=(0, 0, 16), boxes=[cuboid((-5, -11, 11), (10, 22, 10), body)])
    head_part = Part("horse_head", pivot=(0, 9, 19), rot=(-30, 0, 0), boxes=[
        cuboid((-2, 7, 17), (4, 7, 12), neck),
        cuboid((-1, 5, 17), (2, 2, 16), mane_tex),
        cuboid((-3, 7, 29), (6, 7, 5), head),
        cuboid((-2, 14, 29), (4, 6, 5), snout),
        cuboid((-2.5, 8, 34), (2, 1, ear_h), p.skin((2, 1, ear_h), base)),
        cuboid((0.5, 8, 34), (2, 1, ear_h), p.skin((2, 1, ear_h), base)),
    ])
    body_part.add(head_part, Part("tail", pivot=(0, -11, 20), rot=(-30, 0, 0),
                                  boxes=[cuboid((-1.5, -14, 6), (3, 4, 14), tail)]))
    root.add(
        body_part,
        Part("leg_fr", pivot=(3, 8, 11), boxes=[cuboid((1, 6, 0), (4, 4, 11), leg)]),
        Part("leg_fl", pivot=(-3, 8, 11), boxes=[cuboid((-5, 6, 0), (4, 4, 11), leg)]),
        Part("leg_br", pivot=(3, -8, 11), boxes=[cuboid((1, -10, 0), (4, 4, 11), leg)]),
        Part("leg_bl", pivot=(-3, -8, 11), boxes=[cuboid((-5, -10, 0), (4, 4, 11), leg)]),
    )
    return root


def llama(p: Painter, chest: bool = False, armour: Optional[str] = None) -> Part:
    """Camel stand-in: a llama with a team-colour carpet on its back."""
    wool = p.speckle("#e6dcc6", ("#cbbfa6", 0.3))
    body = p.skin((12, 20, 10), wool, top=p.grid(["wwwwwwwwwwww"] * 4 + ["PPPPPPPPPPPP", "PDDPPDDPPDDP"] * 6
                                                 + ["wwwwwwwwwwww"] * 4, {"w": "#e6dcc6", "P": PC(0.65),
                                                                          "D": PC(0.4)}),
                  right=p.grid(["wwwwPPPPPPPPPPPPwwww", "wwwwPDDPPDDPPDDPwwww", "wwwwDDDDDDDDDDDDwwww"]
                               + ["wwwwwwwwwwwwwwwwwwww"] * 7, {"w": "#e6dcc6", "P": PC(0.65), "D": PC(0.4)}))
    if armour:
        body = layered(body, p.skin((12, 20, 10), rows_only(p, ARMOUR[armour](p), 4, 7), top=None, bottom=None))
    head = p.skin((8, 6, 6), wool, front=p.grid(["wwwwwwww", "wKwwwwKw", "wwwwwwww", "wwwwwwww", "wwwwwwww",
                                                 "wwwwwwww"], {"w": "#e6dcc6", "K": "#1a1a1a"}))
    snout = p.skin((4, 4, 4), "#d8ccb0", front=p.grid(["ssss", "sKKs", "ssss", "ssss"], {"s": "#d8ccb0",
                                                                                         "K": "#6a5a48"}))
    leg = p.skin((4, 4, 13), p.bands((11, wool), (2, "#8a7a64")))
    root = Part("root")
    body_part = Part("horse_body", pivot=(0, 0, 18), boxes=[cuboid((-6, -10, 13), (12, 20, 10), body)])
    if chest:
        box = p.skin((3, 8, 7), "#8a6236")
        body_part.boxes += [cuboid((6, -6, 14), (3, 8, 7), box), cuboid((-9, -6, 14), (3, 8, 7), box)]
    body_part.add(Part("horse_head", pivot=(0, 8, 20), boxes=[
        cuboid((-4, 6, 20), (8, 6, 14), p.skin((8, 6, 14), wool)),
        cuboid((-4, 7, 30), (8, 6, 6), head),
        cuboid((-2, 13, 30), (4, 4, 4), snout),
        cuboid((-4, 8, 36), (3, 2, 3), p.skin((3, 2, 3), wool)), cuboid((1, 8, 36), (3, 2, 3), p.skin((3, 2, 3), wool)),
    ]), Part("tail", pivot=(0, -10, 21), rot=(-20, 0, 0), boxes=[cuboid((-1.5, -12, 15), (3, 3, 6),
                                                                      p.skin((3, 3, 6), wool))]))
    root.add(body_part,
             Part("leg_fr", pivot=(3.5, 7, 13), boxes=[cuboid((1.5, 5, 0), (4, 4, 13), leg)]),
             Part("leg_fl", pivot=(-3.5, 7, 13), boxes=[cuboid((-5.5, 5, 0), (4, 4, 13), leg)]),
             Part("leg_br", pivot=(3.5, -7, 13), boxes=[cuboid((1.5, -9, 0), (4, 4, 13), leg)]),
             Part("leg_bl", pivot=(-3.5, -7, 13), boxes=[cuboid((-5.5, -9, 0), (4, 4, 13), leg)]))
    return root


def mount(key: str, name: str, replaces: str, rider: Unit, steed: Part, seat: float = SEAT_HORSE,
          civ: Optional[str] = None) -> Unit:
    """Seat `rider` on `steed`: hips on the saddle, legs forward and splayed, free hand on the reins."""
    rider_root = rider.root
    rider_root.name = "rider"
    rider_root.offset = (0, -1, seat)
    rider_root.find("leg_r").rot = (80, 0, -14)
    rider_root.find("leg_l").rot = (80, 0, 14)
    if rider.attack in ("chop", "throw", "cast"):
        rider_root.find("arm_l").rot = (35, 0, 0)  # reins
    elif rider.attack == "bow":
        rider_root.find("arm_l").rot = (35, 0, 0)  # bow held out front, kept upright
        rider_root.find("item_l").rot = (-35, 0, 0)
    steed.find("horse_body").add(rider_root)
    rig = {"bow": "horse_archer"}.get(rider.attack, "cavalry")
    return Unit(key, name, replaces, rig, steed, group="cavalry", attack=rider.attack, civ=civ)


def _rider(key, **kw) -> Unit:
    return crafter(key + "_rider", "", "", **kw)


def _horseman(key, name, replaces, coat, horse_armour=None, civ=None, **rider_kw) -> Unit:
    return mount(key, name, replaces, _rider(key, **rider_kw), horse(Painter(key + "_horse"), coat, horse_armour),
                 civ=civ)


def _llama_rider(key, name, replaces, rider: Unit, chest=False, armour=None, civ=None) -> Unit:
    return mount(key, name, replaces, rider, llama(Painter(key + "_llama"), chest, armour), SEAT_LLAMA, civ=civ)


def _husk_rider() -> Unit:
    p = Painter("mameluke_rider")
    return Unit("mameluke_rider", "", "", "biped", biped(zombie_look(p, "husk"), p, right=items.sword("iron"),
                                                         arms=((15, 0, 0), (0, 0, 0))), attack="throw")


def _zombie_rider() -> Unit:
    p = Painter("tarkan_rider")
    return Unit("tarkan_rider", "", "", "biped", biped(zombie_look(p, "zombie"), p, right=items.torch(),
                                                       arms=((30, 0, 0), (0, 0, 0))), attack="chop")


MOUNTED = {
    "scout_cavalry": lambda: _horseman("scout_cavalry", "Scout Rider", "Scout Cavalry", "brown",
                                       armour="leather", pieces="hc", sword="stone"),
    "light_cavalry": lambda: _horseman("light_cavalry", "Light Rider", "Light Cavalry", "chestnut", "leather",
                                       armour="chain", pieces="hc", sword="iron"),
    "hussar": lambda: _horseman("hussar", "Golden Hussar", "Hussar", "white", "leather",
                                armour="gold", pieces="h", sword="iron", has_cape=True),
    "knight": lambda: _horseman("knight", "Iron Horseman", "Knight", "black", "iron",
                                armour="iron", sword="iron", has_cape=True),
    "cavalier": lambda: _horseman("cavalier", "Gold Horseman", "Cavalier", "chestnut", "gold",
                                  armour="iron", sword="gold", has_cape=True),
    "paladin": lambda: _horseman("paladin", "Diamond Paladin", "Paladin", "white", "diamond",
                                 armour="diamond", sword="diamond", has_cape=True),
    "cavalry_archer": lambda: mount("cavalry_archer", "Skeleton Horseman", "Cavalry Archer",
                                    skeleton_archer("cavalry_archer_rider"),
                                    horse(Painter("cavalry_archer_horse"), "skeleton")),
    "heavy_cavalry_archer": lambda: mount("heavy_cavalry_archer", "Armoured Skeleton Horseman",
                                          "Heavy Cavalry Archer", skeleton_archer("hca_rider", helmet="iron"),
                                          horse(Painter("hca_horse"), "skeleton", "iron")),
    "camel": lambda: _llama_rider("camel", "Llama Rider", "Camel",
                                  _rider("camel", armour="leather", pieces="h", sword="iron")),
    "heavy_camel": lambda: _llama_rider("heavy_camel", "Heavy Llama Rider", "Heavy Camel",
                                        _rider("heavy_camel", armour="chain", pieces="hc", sword="iron"),
                                        chest=True, armour="iron"),
    # unique units
    "cataphract": lambda: _horseman("cataphract", "Netherite Cataphract", "Cataphract", "black", "netherite",
                                    civ="Byzantines", armour="gold", sword="diamond", has_cape=True),
    "mangudai": lambda: mount("mangudai", "Pillager Raider", "Mangudai",
                              pillager("mangudai_rider", "", ""), horse(Painter("mangudai_horse"), "brown"),
                              civ="Mongols"),
    "mameluke": lambda: _llama_rider("mameluke", "Husk Llama Rider", "Mameluke", _husk_rider(), civ="Saracens"),
    "tarkan": lambda: mount("tarkan", "Zombie Horseman", "Tarkan", _zombie_rider(),
                            horse(Painter("tarkan_horse"), "zombie"), civ="Huns"),
    "conquistador": lambda: _horseman("conquistador", "Firework Rider", "Conquistador", "brown", civ="Spanish",
                                      armour="iron", pieces="hc", weapon=items.hand_cannon(), attack="gun"),
    "missionary": lambda: mount("missionary", "Cleric on a Donkey", "Missionary",
                                cleric("missionary_rider", "", ""), horse(Painter("missionary_donkey"), "grey",
                                                                          donkey=True), civ="Spanish"),
}
