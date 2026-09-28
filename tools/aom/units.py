"""Foot units: Minecraft-style figures standing in for AoE2 infantry, archers,
civilians and unique units.

Every model is original pixel art in the Minecraft style (cuboid bodies,
8x8 faces, small noisy palettes) rather than copied game textures. Player
colour (`PC`) marks the parts that show which team a unit belongs to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import items
from .geometry import Box, Part, cuboid
from .items import Item, held
from .textures import PC, Painter, Spec, layered, parse


@dataclass
class Unit:
    key: str
    name: str  # in-mod name
    replaces: str  # AoE2 unit it replaces
    rig: str  # animation rig, see animation.py
    root: Part
    group: str = "foot"  # foot, cavalry, siege, ship, animal
    attack: str = "chop"  # attack style, see animation.py
    civ: Optional[str] = None  # set for unique units
    carry: bool = False  # has a hidden 'carry' part shown while carrying resources
    scale: float = 1.0  # render-size multiplier (big siege and ships read better a bit larger)


# --------------------------------------------------------------------------- texture helpers

def masked(p: Painter, paint, rows: list[str]) -> np.ndarray:
    """Paint a whole face, then keep only the pixels marked with a letter in `rows`."""
    h, w = len(rows), len(rows[0])
    tex = p.resolve(paint, w, h)
    keep = np.array([[ch != "." for ch in row] for row in rows])
    tex[~keep] = 0
    return tex


def rows_only(p: Painter, paint, first: int, last: int):
    """Paint only rows first..last (inclusive) of a face; the rest stays transparent."""

    def paint_rows(w: int, h: int) -> np.ndarray:
        tex = p.resolve(paint, w, h)
        keep = np.zeros(h, bool)
        keep[first:last + 1] = True
        tex[~keep] = 0
        return tex

    return paint_rows


def metal(p: Painter, base: Spec, dark: Spec, light: Spec):
    """Armour plating: noisy base with a lit top edge, shaded bottom edge and scattered glints."""

    def paint(w: int, h: int) -> np.ndarray:
        tex = p.fill(w, h, base, 0.04)
        rnd = p.rng.random((h, w))
        tex[rnd < 0.10] = parse(light)
        tex[rnd > 0.90] = parse(dark)
        tex[0] = parse(light)
        tex[-1] = parse(dark)
        return tex

    return paint


def chainmail(p: Painter):
    def paint(w: int, h: int) -> np.ndarray:
        tex = p.fill(w, h, "#9a9a9a", 0.06)
        yy, xx = np.mgrid[0:h, 0:w]
        tex[(yy % 2 == 1) & (xx % 2 == 0)] = 0  # holes show the shirt underneath
        tex[(yy % 2 == 0) & (xx % 2 == 1)] = parse("#6a6a6a")
        return tex

    return paint


ARMOUR = {
    "leather": lambda p: metal(p, PC(0.55), PC(0.35), PC(0.72)),  # leather is dyed in team colour
    "chain": chainmail,
    "copper": lambda p: metal(p, "#d27a4e", "#9a4f2e", "#f0a882"),
    "iron": lambda p: metal(p, "#d4d4d4", "#8c8c8c", "#fafafa"),
    "gold": lambda p: metal(p, "#f3d03e", "#b3861a", "#fff4a3"),
    "diamond": lambda p: metal(p, "#4fdfcd", "#1f8f82", "#c9fff5"),
    "netherite": lambda p: metal(p, "#4d4649", "#2f2a2d", "#716a6e"),
}

HELMET_FRONT = ["aaaaaaaa", "aaaaaaaa", "a......a", "a......a"] + ["........"] * 4
HELMET_SIDE = ["aaaaaaaa"] * 4 + ["aaaaa...", "aaaa....", "aaa.....", "........"]


def solid(spec: Spec) -> dict[str, np.ndarray]:
    return {f: parse(spec)[None, None].copy() for f in ("front", "back", "right", "left", "top", "bottom")}


# --------------------------------------------------------------------------- the biped builder

@dataclass
class Look:
    """Face textures and sizes for a Minecraft-style biped."""

    head: dict
    body: dict
    arm: dict
    leg: dict
    arm_l: Optional[dict] = None
    head_size: tuple = (8, 8, 8)
    body_size: tuple = (8, 4, 12)
    arm_size: tuple = (4, 4, 12)
    leg_size: tuple = (4, 4, 12)
    inflate: dict = field(default_factory=lambda: {"head": 0.0, "body": 0.0, "arm": 0.0, "leg": 0.0})
    head_extras: list = field(default_factory=list)  # boxes that move with the head (noses, hats, ears)
    torso_extras: list = field(default_factory=list)  # boxes or parts on the torso (capes, quivers, robes)


def armour_up(p: Painter, look: Look, material: str, pieces: str = "hclb") -> Look:
    """Layer Minecraft-style armour onto a standard 8x8x8-head biped."""
    mat = ARMOUR[material](p)
    hw, hd, hh = look.head_size
    if "h" in pieces:
        look.head = layered(look.head, p.skin((hw, hd, hh), mat, bottom=None,
                                              front=masked(p, mat, HELMET_FRONT), right=masked(p, mat, HELMET_SIDE),
                                              back=rows_only(p, mat, 0, 6)))
        look.inflate["head"] = 0.6
    if "c" in pieces:
        look.body = layered(look.body, p.skin(look.body_size, rows_only(p, mat, 0, 8), top=mat, bottom=None))
        look.arm = layered(look.arm, p.skin(look.arm_size, rows_only(p, mat, 0, 5), top=mat, bottom=None))
        if look.arm_l is not None:
            look.arm_l = layered(look.arm_l, p.skin(look.arm_size, rows_only(p, mat, 0, 5), top=mat, bottom=None))
        look.inflate["body"] = look.inflate["arm"] = 0.5
    if "l" in pieces:
        look.body = layered(look.body, p.skin(look.body_size, rows_only(p, mat, 9, 11), top=None, bottom=mat))
        look.leg = layered(look.leg, p.skin(look.leg_size, rows_only(p, mat, 0, 8), top=mat, bottom=None))
        look.inflate["leg"] = 0.4
    if "b" in pieces:
        look.leg = layered(look.leg, p.skin(look.leg_size, rows_only(p, mat, 8, 11), top=None, bottom=mat))
        look.inflate["leg"] = 0.4
    return look


def biped(look: Look, p: Painter, *, right: Optional[Item] = None, left: Optional[Item] = None,
          chest: Optional[Item] = None, arms: tuple = ((0, 0, 0), (0, 0, 0)), carry: Optional[dict] = None) -> Part:
    """Assemble head, torso, arms and legs; `arms` are rest rotations for (right, left)."""
    bw, bd, bh = look.body_size
    hw, hd, hh = look.head_size
    aw, ad, ah = look.arm_size
    lw, ld, lh = look.leg_size
    top = lh + bh
    inf = look.inflate
    ax = bw / 2 + aw / 2  # arm centre line
    hand_z = top - ah + 1

    root = Part("root")
    torso = Part("torso", pivot=(0, 0, lh), boxes=[cuboid((-bw / 2, -bd / 2, lh), look.body_size, look.body,
                                                          inf["body"])])
    head = Part("head", pivot=(0, 0, top), boxes=[cuboid((-hw / 2, -hd / 2, top), look.head_size, look.head,
                                                         inf["head"])] + look.head_extras)
    arm_r = Part("arm_r", pivot=(ax, 0, top - 2), rot=arms[0],
                 boxes=[cuboid((bw / 2, -ad / 2, top - ah), look.arm_size, look.arm, inf["arm"])])
    arm_l = Part("arm_l", pivot=(-ax, 0, top - 2), rot=arms[1],
                 boxes=[cuboid((-bw / 2 - aw, -ad / 2, top - ah), look.arm_size, look.arm_l or look.arm, inf["arm"])])
    if right is not None:
        arm_r.add(held(right, "item_r", (ax, 1.0, hand_z), p))
    if left is not None:
        arm_l.add(held(left, "item_l", (-ax, 1.0, hand_z), p))
    torso.add(head, arm_r, arm_l)
    if chest is not None:  # two-handed weapon carried in front of the chest
        at = (0.0, bd / 2 + 9, top - 5) if chest.flat else (ax - 2.5, bd / 2 + 4, top - 3)
        torso.add(held(chest, "item_c", at, p))
    if carry is not None:  # resource carried in both arms, hidden unless carrying
        torso.add(Part("carry", boxes=[cuboid((-3.5, bd / 2 + 3, top - 11), (7, 7, 7), carry)]))
    for extra in look.torso_extras:
        if isinstance(extra, Part):
            torso.add(extra)
        else:
            torso.boxes.append(extra)
    cx = bw / 4
    root.add(torso,
             Part("leg_r", pivot=(cx, 0, lh), boxes=[cuboid((cx - lw / 2, -ld / 2, 0), look.leg_size, look.leg,
                                                             inf["leg"])]),
             Part("leg_l", pivot=(-cx, 0, lh), boxes=[cuboid((-cx - lw / 2, -ld / 2, 0), look.leg_size, look.leg,
                                                              inf["leg"])]))
    return root


def cape(p: Painter, body_depth: float = 4, top: float = 24) -> Part:
    tex = p.skin((10, 1, 16), p.bands((15, PC(0.55)), (1, PC(0.35))), top=PC(0.5))
    y = -body_depth / 2 - 0.5
    return Part("cape", pivot=(0, y, top), rot=(-6, 0, 0), boxes=[cuboid((-5, y - 1, top - 15), (10, 1, 15), tex)])


def back_banner(p: Painter, body_depth: float = 4, top: float = 24) -> Part:
    """A team banner on a pole strapped to the back (Arbalest, captains)."""
    cloth = p.grid(["DDDDDD"] + ["PPPPPP"] * 2 + ["PPDDPP", "PDLLDP", "PPDDPP"] + ["PPPPPP"] * 5 + ["PDPPDP"],
                   {"P": PC(0.6), "D": PC(0.35), "L": PC(0.85)})
    y = -body_depth / 2 - 1.5
    return Part("banner", boxes=[cuboid((-0.5, y - 1, top - 10), (1, 1, 26), solid(items.STICK)),
                                 cuboid((-3, y - 1.5, top + 4), (6, 1, 12), {f: cloth for f in
                                                                              ("front", "back", "right", "left",
                                                                               "top", "bottom")})])


# --------------------------------------------------------------------------- looks

SKIN, SKIN_SHADE = "#c89478", "#a8765c"
HAIR = "#4b3222"
PANTS, SHOES, BELT, BUCKLE = "#3d3a5e", "#5a5a5a", "#5b3a1e", "#e0b44a"

CRAFTER_FACE = ["hhhhhhhh", "hhhhhhhh", "hssssssh", "ssssssss", "swessews", "sssnnsss", "ssmmmmss", "ssssssss"]
CRAFTER_SIDE = ["hhhhhhhh", "hhhhhhhh", "hhhhhsss", "hhhhssss", "hhhsssss", "hhssssss", "hsssssss", "ssssssss"]


def crafter_look(p: Painter, *, skin: str = SKIN, hair: str = HAIR, eyes: str = "#3a62b8", shirt: Spec = PC(0.62),
                 pants: str = PANTS, shoes: str = SHOES, face: Optional[list[str]] = None) -> Look:
    legend = {"h": hair, "s": skin, "S": SKIN_SHADE, "w": "#f4f4f4", "e": eyes, "n": SKIN_SHADE, "m": "#7a4636",
              "b": "#2e1f14"}
    head = p.skin((8, 8, 8), hair, top=hair, bottom=skin, front=p.grid(face or CRAFTER_FACE, legend),
                  right=p.grid(CRAFTER_SIDE, legend))
    body = p.skin((8, 4, 12), p.bands((9, shirt), (1, BELT), (2, pants)), top=shirt, bottom=pants,
                  front=p.grid(["PPPssPPP"] + ["PPPPPPPP"] * 8 + ["bbbyybbb", "pppppppp", "pppppppp"],
                               {"P": shirt, "s": skin, "b": BELT, "y": BUCKLE, "p": pants}))
    arm = p.skin((4, 4, 12), p.bands((4, shirt), (8, skin)), top=shirt, bottom=skin)
    leg = p.skin((4, 4, 12), p.bands((9, pants), (3, shoes)), top=pants, bottom=shoes)
    return Look(head, body, arm, leg)


BONE_PALETTES = {  # bone, shade, gaps, sockets
    "skeleton": ("#c3c3c3", "#9c9c9c", "#4a4a4a", "#1c1c1c"),
    "stray": ("#b6c6c7", "#8fa2a4", "#46585a", "#172224"),
    "wither": ("#2e2e2e", "#1f1f1f", "#101010", "#060606"),
    "bogged": ("#a3ab86", "#7f8a62", "#3f4a2e", "#18200f"),
}


def skeleton_look(p: Painter, kind: str = "skeleton", cap: Optional[str] = "leather",
                  tunic: bool = True) -> Look:
    bone, bone_d, dark, hole = BONE_PALETTES[kind]
    legend = {"k": bone, "K": bone_d, "D": hole, "d": dark}
    head = p.skin((8, 8, 8), p.speckle(bone, (bone_d, 0.2)),
                  front=p.grid(["kkkkkkkk", "kkkkkkkk", "kkkkkkkk", "kDDkkDDk",
                                "kDDkkDDk", "kkkddkkk", "kdkdkdkk", "kkkkkkkk"], legend))
    ribs = p.skin((8, 4, 12), bone,
                  front=p.grid(["kkkkkkkk", "dkkkkkkd", "kkkkkkkk", "dkkddkkd", "kkkkkkkk", "dkkddkkd",
                                "kkkkkkkk", "dddkkddd", "dddkkddd", "dddkkddd", "kkkkkkkk", "kkddddkk"], legend))
    if tunic:
        ribs = layered(ribs, p.skin((8, 4, 12), rows_only(p, metal(p, PC(0.55), PC(0.35), PC(0.72)), 0, 7),
                                    top=PC(0.55), bottom=None))
    limb = p.skin((2, 2, 12), p.speckle(bone, (bone_d, 0.25)))
    look = Look(head, ribs, limb, limb, arm_size=(2, 2, 12), leg_size=(2, 2, 12))
    look.inflate.update(head=0.3, body=0.3)
    if cap:
        mat = ARMOUR[cap](p)
        look.head = layered(look.head, p.skin((8, 8, 8), mat, bottom=None,
                                              front=masked(p, mat, ["aaaaaaaa", "aaaaaaaa"] + ["........"] * 6),
                                              right=masked(p, mat, ["aaaaaaaa", "aaaaaaaa", "aaaa....", "aaa....."]
                                                           + ["........"] * 4),
                                              back=rows_only(p, mat, 0, 3)))
    if kind == "bogged":  # mushrooms growing on the skull
        look.head_extras += [cuboid((1, -1, 32), (3, 3, 2), solid("#b8322a")), cuboid((2, 0, 34), (1, 1, 1),
                                                                                         solid("#e8e8e8")),
                             cuboid((-4, -3, 32), (2, 2, 2), solid("#8a6a4a"))]
    return look


def quiver(p: Painter, depth: float = 4) -> Box:
    tex = p.skin((3, 2, 9), p.bands((2, "#e8e8e8"), (7, "#7a5230")), top="#e8e8e8")
    return cuboid((-3.5, -depth / 2 - 2.3, 14), (3, 2, 9), tex)


def zombie_look(p: Painter, kind: str = "zombie") -> Look:
    skins = {"zombie": ("#5d9a4f", "#467a3b", "#2e5a26"), "husk": ("#9c8660", "#7e6a48", "#5a4a30"),
             "drowned": ("#4f9e96", "#3a7a74", "#2a5a56")}
    skin, shade, hair = skins[kind]
    eye = {"zombie": "#1f3a1a", "husk": "#2e2416", "drowned": "#a6fff4"}[kind]
    legend = {"h": hair, "s": skin, "S": shade, "e": eye, "m": "#2a2a1e", "w": "#2f5fc0"}
    face = ["hhhhhhhh", "hhshhhsh", "ssssssss", "wsssssww" if kind == "zombie" else "ssssssss",
            "seessees", "sssSSsss", "ssmmmmss", "ssssssss"]
    head = p.skin((8, 8, 8), p.speckle(skin, (shade, 0.25)), top=hair, front=p.grid(face, legend),
                  right=p.grid(["hhhhhhhh", "hhhhhhss", "hhhsssss", "hhssssss"] + ["ssssssss"] * 4, legend))
    shirt, pants = PC(0.6), {"zombie": "#463aa0", "husk": "#6b5433", "drowned": "#5a6b3a"}[kind]
    torn = p.speckle(shirt, (skin, 0.25 if kind == "drowned" else 0.0))
    body = p.skin((8, 4, 12), p.bands((9, torn), (3, pants)), top=shirt, bottom=pants)
    arm = p.skin((4, 4, 12), p.bands((4, torn), (8, p.speckle(skin, (shade, 0.25)))), top=shirt, bottom=skin)
    leg = p.skin((4, 4, 12), p.bands((10, pants), (2, "#4a4a4a" if kind != "drowned" else skin)))
    return Look(head, body, arm, leg)


ILLAGER_SKIN = "#9ea39b"


def villager_head(p: Painter, skin: str, brow: str = "#4a2c22", eyes: str = "#2f8a3a") -> tuple[dict, list]:
    """Villager / illager head: 8x8x10 with the big nose; returns (faces, extra boxes)."""
    legend = {"s": skin, "b": brow, "w": "#f0f0f0", "g": eyes}
    head = p.skin((8, 8, 10), skin,
                  front=p.grid(["ssssssss", "ssssssss", "ssssssss", "sbbbbbbs", "swgssgws",
                                "ssssssss", "ssssssss", "ssssssss", "ssssssss", "ssssssss"], legend))
    shade = "#" + "".join(f"{int(int(skin[i:i + 2], 16) * 0.85):02x}" for i in (1, 3, 5))
    return head, [cuboid((-1, 4, 25), (2, 2, 4), p.skin((2, 2, 4), shade))]


def illager_look(p: Painter, *, skin: str = ILLAGER_SKIN, coat: Spec = "#39322e", shirt: Spec = PC(0.6),
                 pants: str = "#2f2f2f", robe: Optional[Spec] = None, brow: str = "#2a2a2a",
                 eyes: str = "#2a2a2a", sleeve: Optional[Spec] = None) -> Look:
    head, nose = villager_head(p, skin, brow, eyes)
    body = p.skin((8, 6, 12), p.bands((10, coat), (2, pants)), top=coat,
                  front=p.grid(["CCPPPPCC"] * 9 + ["CCbbbbCC", "pppppppp", "pppppppp"],
                               {"C": coat, "P": shirt, "b": BELT, "p": pants}))
    sleeve = coat if sleeve is None else sleeve
    arm = p.skin((4, 4, 12), p.bands((8, sleeve), (4, skin)), top=sleeve, bottom=skin)
    leg = p.skin((4, 4, 12), p.bands((10, pants), (2, "#222222")))
    look = Look(head, body, arm, leg, head_size=(8, 8, 10), body_size=(8, 6, 12), head_extras=nose)
    if robe is not None:  # full-length robe over body and upper legs
        robe_tex = p.skin((8, 6, 18), p.bands((1, PC(0.4) if isinstance(robe, PC) else robe), (16, robe),
                                             (1, PC(0.3) if isinstance(robe, PC) else "#2a2a2a")),
                          front=p.grid(["LLLLLLLL"] + ["RRRDDRRR"] * 16 + ["DDDDDDDD"],
                                       {"L": PC(0.45) if isinstance(robe, PC) else robe, "R": robe,
                                        "D": PC(0.4) if isinstance(robe, PC) else "#2a2a2a"}))
        look.torso_extras.append(cuboid((-4, -3, 6), (8, 6, 18), robe_tex, 0.5))
    return look


def piglin_look(p: Painter, brute: bool = False) -> Look:
    skin, shade, dark = "#dd9791", "#bf7771", "#8a4f4a"
    legend = {"s": skin, "S": shade, "e": "#101010", "w": "#f0f0f0", "d": dark, "g": "#f2c233"}
    head = p.skin((10, 8, 8), p.speckle(skin, (shade, 0.3)),
                  front=p.grid(["ssssssssss", "sSssssssSs", "ssssssssss", "swessssews", "ssssssssss",
                                "ssssssssss", "ssssssssss", "sgssssssgs"], legend))
    snout = p.skin((4, 2, 3), shade, front=p.grid(["SSSS", "dSSd", "SSSS"], legend))
    ear = p.skin((1, 5, 4), p.speckle(skin, (shade, 0.3)))
    belt = "#2a2420" if brute else "#6b3f1d"
    body = p.skin((8, 4, 12), p.bands((8, PC(0.6)), (2, belt), (2, "#5a3a24")), top=PC(0.6),
                  front=p.grid(["PPPPPPPP"] * 8 + ["bbbggbbb", "bbbbbbbb", "llllllll", "llllllll"],
                               {"P": PC(0.6), "b": belt, "g": "#f2c233", "l": "#5a3a24"}))
    arm = p.skin((4, 4, 12), p.speckle(skin, (shade, 0.3)))
    leg = p.skin((4, 4, 12), p.bands((6, "#5a3a24"), (6, p.speckle(skin, (shade, 0.3)))))
    look = Look(head, body, arm, leg, head_size=(10, 8, 8))
    look.head_extras += [cuboid((-2, 4, 25), (4, 2, 3), snout),
                         cuboid((4.5, -2, 27), (1, 5, 4), ear), cuboid((-5.5, -2, 27), (1, 5, 4), ear)]
    return look


# --------------------------------------------------------------------------- foot soldiers

def crafter(key: str, name: str, replaces: str, *, armour: Optional[str] = None, pieces: str = "hclb",
            sword: Optional[str] = None, weapon: Optional[Item] = None, has_cape: bool = False,
            attack: str = "chop", civ: Optional[str] = None, look: Optional[Look] = None) -> Unit:
    """A Steve-like humanoid; `pieces` picks helmet/chestplate/leggings/boots."""
    p = Painter(key)
    look = look or crafter_look(p)
    if armour:
        armour_up(p, look, armour, pieces)
    if has_cape:
        look.torso_extras.append(cape(p))
    weapon = weapon or (items.sword(sword) if sword else None)
    if attack in ("gun", "crossbow"):
        root = biped(look, p, chest=weapon, arms=((75, 0, 20), (75, 0, -25)))
    else:
        root = biped(look, p, right=weapon, arms=((15, 0, 0), (0, 0, 0)))
    return Unit(key, name, replaces, "biped", root, attack=attack, civ=civ)


def skeleton_archer(key: str = "skeleton_archer", *, kind: str = "skeleton", helmet: Optional[str] = None,
                    name: str = "Skeleton Archer", replaces: str = "Archer", tall_bow: bool = False,
                    civ: Optional[str] = None) -> Unit:
    p = Painter(key)
    look = skeleton_look(p, kind, cap=helmet or "leather")
    look.torso_extras.append(quiver(p))
    root = biped(look, p, left=items.bow(tall_bow))
    return Unit(key, name, replaces, "biped", root, attack="bow", civ=civ)


def drowned(key: str, name: str, replaces: str, helmet: Optional[str] = None, pieces: str = "h") -> Unit:
    p = Painter(key)
    look = zombie_look(p, "drowned")
    if helmet:
        armour_up(p, look, helmet, pieces)
    root = biped(look, p, right=items.trident(), arms=((30, 0, 0), (0, 0, 0)))
    return Unit(key, name, replaces, "biped", root, attack="thrust")


def pillager(key: str, name: str, replaces: str, *, helmet: Optional[str] = None, banner: bool = False,
             look: Optional[Look] = None, glint: bool = False, civ: Optional[str] = None) -> Unit:
    p = Painter(key)
    look = look or illager_look(p)
    if helmet:
        mat = ARMOUR[helmet](p)
        look.head = layered(look.head, p.skin((8, 8, 10), mat, bottom=None,
                                              front=masked(p, mat, ["aaaaaaaa", "aaaaaaaa", "a......a"]
                                                           + ["........"] * 7),
                                              right=rows_only(p, mat, 0, 4), back=rows_only(p, mat, 0, 6)))
        look.inflate["head"] = 0.5
    if banner:
        look.torso_extras.append(back_banner(p, body_depth=6))
    root = biped(look, p, chest=items.crossbow(glint), arms=((75, 0, 20), (75, 0, -25)))
    return Unit(key, name, replaces, "biped", root, attack="crossbow", civ=civ)


def snow_golem(key: str, name: str, replaces: str, elite: bool = False) -> Unit:
    p = Painter(key)
    snow = p.speckle("#f2f6f7", ("#dce4e6", 0.3))
    face_legend = {"o": "#e0892a", "O": "#c46a18", "K": "#3a2410", "Y": "#ffd23a"}
    eye = "Y" if elite else "K"
    pumpkin = p.skin((8, 8, 8), p.bands(*[(1, "#e0892a" if i % 2 else "#c46a18") for i in range(8)]),
                     top=p.grid(["oooooooo"] * 3 + ["oooGGooo", "oooGGooo"] + ["oooooooo"] * 3,
                                {"o": "#c46a18", "G": "#5a7a2a"}),
                     front=p.grid(["oOooooOo", "oooooooo", f"o{eye}{eye}oo{eye}{eye}o", f"o{eye}{eye}oo{eye}{eye}o",
                                   "oooooooo", f"o{eye}o{eye}{eye}o{eye}o", f"oo{eye}oo{eye}oo", "oooooooo"],
                                  face_legend))
    scarf = p.skin((11, 11, 2), p.bands((1, PC(0.6)), (1, PC(0.4))))
    stick = solid(items.STICK)
    root = Part("root")
    body = Part("torso", pivot=(0, 0, 6), boxes=[cuboid((-6, -6, 0), (12, 12, 12), p.skin((12, 12, 12), snow)),
                                                 cuboid((-5, -5, 11), (10, 10, 10), p.skin((10, 10, 10), snow)),
                                                 cuboid((-5.5, -5.5, 19.5), (11, 11, 2), scarf)])
    body.add(Part("head", pivot=(0, 0, 21), boxes=[cuboid((-4, -4, 21), (8, 8, 8), pumpkin)]),
             Part("arm_r", pivot=(5, 0, 17), rot=(0, -50, 0), boxes=[cuboid((5, -1, 16), (11, 2, 2), stick)]),
             Part("arm_l", pivot=(-5, 0, 17), rot=(0, 50, 0), boxes=[cuboid((-16, -1, 16), (11, 2, 2), stick)]))
    root.add(body)
    return Unit(key, name, replaces, "snow_golem", root, attack="throw")


def blaze(key: str = "blaze") -> Unit:
    p = Painter(key)
    legend = {"y": "#f2c230", "o": "#e08a18", "K": "#3a2008", "w": "#fff2a0"}
    head = p.skin((8, 8, 8), p.speckle("#f2c230", ("#e08a18", 0.35)),
                  front=p.grid(["yoyyoyyo", "yyoyyyoy", "yyyyyyyy", "yKKyyKKy", "yyyyyyyy",
                                "yyoKKoyy", "yyyyyyyy", "oyyoyyoy"], legend))
    rod = p.skin((2, 2, 8), p.bands((2, "#ffe07a"), (4, "#f0a020"), (2, "#b86a10")))
    rod_pc = p.skin((2, 2, 8), p.bands((2, PC(0.8)), (4, PC(0.6)), (2, PC(0.4))))
    root = Part("root")
    rings = []
    for name, z, radius, n, phase, tex in (("rods_top", 14, 6.5, 4, 0, rod), ("rods_mid", 8, 5.0, 4, 45, rod_pc),
                                           ("rods_low", 1, 3.5, 4, 0, rod)):
        boxes = []
        for i in range(n):
            a = np.radians(phase + i * 360 / n)
            x, y = radius * np.cos(a), radius * np.sin(a)
            boxes.append(cuboid((x - 1, y - 1, z), (2, 2, 8), tex))
        rings.append(Part(name, pivot=(0, 0, z), boxes=boxes))
    body = Part("torso", pivot=(0, 0, 8), boxes=[cuboid((-1, -1, 4), (2, 2, 18), solid("#c98a18"))])
    body.add(Part("head", pivot=(0, 0, 22), boxes=[cuboid((-4, -4, 22), (8, 8, 8), head)]), *rings)
    root.add(body)
    return Unit(key, "Blaze", "Janissary", "blaze", root, attack="blaze", civ="Turks")


def iron_golem(key: str = "iron_golem") -> Unit:
    p = Painter(key)
    iron = p.speckle("#d9d0c6", ("#b8aea3", 0.3), ("#9a8f86", 0.08), ("#5c8a34", 0.05))
    legend = {"i": "#d9d0c6", "I": "#b8aea3", "r": "#a52a1a", "d": "#6e645c"}
    head = p.skin((8, 8, 10), iron, front=p.grid(["iiiiiiii", "iIiiiiIi", "iiiiiiii", "IIIIIIII", "irIiiIri",
                                                  "iiiiiiii", "iiiiiiii", "iiiiiiii", "iiiiiiii", "iiIiiIii"], legend))
    chest = p.skin((18, 11, 12), iron, front=p.grid(["iiiiiiiiiiiiiiiiii"] * 2 + ["iiiPPPPPPPPPPPPiii"] * 7
                                                    + ["iiiiPPPPPPPPPPiiii", "iiiiiPPPPPPPPiiiii", "iiiiiiiiiiiiiiii"
                                                                                                   "ii"],
                                                    {"i": "#d9d0c6", "P": PC(0.6)}))
    waist = p.skin((9, 6, 5), iron)
    arm = p.skin((4, 6, 30), p.bands((26, iron), (4, "#b8aea3")))
    leg = p.skin((6, 5, 16), iron)
    root = Part("root")
    torso = Part("torso", pivot=(0, 0, 16), boxes=[cuboid((-4.5, -3, 16), (9, 6, 5), waist),
                                                   cuboid((-9, -5.5, 21), (18, 11, 12), chest)])
    torso.add(Part("head", pivot=(0, 0, 33), boxes=[cuboid((-4, -4, 31), (8, 8, 10), head),
                                                    cuboid((-1, 4, 33), (2, 2, 4), p.skin((2, 2, 4), "#b8aea3")),
                                                    cuboid((2.5, 3.5, 33.5), (2, 1, 2), solid(PC(0.55))),
                                                    ]),
              Part("arm_r", pivot=(11, 0, 31), boxes=[cuboid((9, -3, 3), (4, 6, 30), arm)]),
              Part("arm_l", pivot=(-11, 0, 31), boxes=[cuboid((-13, -3, 3), (4, 6, 30), arm)]))
    root.add(torso,
             Part("leg_r", pivot=(3.5, 0, 16), boxes=[cuboid((0.5, -2.5, 0), (6, 5, 16), leg)]),
             Part("leg_l", pivot=(-3.5, 0, 16), boxes=[cuboid((-6.5, -2.5, 0), (6, 5, 16), leg)]))
    return Unit(key, "Iron Golem", "War Elephant", "golem", root, attack="slam", civ="Persians")


def creeper(key: str = "creeper") -> Unit:
    p = Painter(key)
    greens = ("#5db34a", ("#3d8a2e", 0.3), ("#8fd36f", 0.15), (PC(0.5), 0.12))
    face = p.grid(["gggggggg", "gGgggggg", "gFFggFFg", "gFFggFFg",
                   "gggFFggg", "ggFFFFgg", "ggFFFFgg", "ggFggFgg"],
                  {"g": "#5db34a", "G": "#8fd36f", "F": "#101010"})
    mottled = p.speckle(*greens)
    head = p.skin((8, 8, 8), mottled, front=face)
    body = p.skin((8, 4, 12), mottled)
    foot = p.skin((4, 4, 6), p.bands((4, mottled), (2, "#3d8a2e")))
    root = Part("root")
    root.add(
        Part("torso", pivot=(0, 0, 6), boxes=[cuboid((-4, -2, 6), (8, 4, 12), body)]).add(
            Part("head", pivot=(0, 0, 18), boxes=[cuboid((-4, -4, 18), (8, 8, 8), head)])),
        Part("leg_fr", pivot=(2, 4, 6), boxes=[cuboid((0, 2, 0), (4, 4, 6), foot)]),
        Part("leg_fl", pivot=(-2, 4, 6), boxes=[cuboid((-4, 2, 0), (4, 4, 6), foot)]),
        Part("leg_br", pivot=(2, -4, 6), boxes=[cuboid((0, -6, 0), (4, 4, 6), foot)]),
        Part("leg_bl", pivot=(-2, -4, 6), boxes=[cuboid((-4, -6, 0), (4, 4, 6), foot)]),
    )
    return Unit(key, "Creeper", "Petard", "quadruped", root, attack="explode")


def feathered(p: Painter, look: Look, elite: bool = False) -> Look:
    """Parrot-feather headdress for the Eagle Warrior line."""
    colours = ["#d8342a", "#2f6fd8", "#f2c233", "#3aa04a"] + (["#d8342a", "#2f6fd8"] if elite else [])
    x = -len(colours) * 1.5 / 2
    for i, c in enumerate(colours):
        look.head_extras.append(cuboid((x + i * 1.5, -3, 32), (1.5, 1.5, 6 + (i % 2) * 2), solid(c)))
    look.head_extras.append(cuboid((-4.5, -4.5, 30), (9, 9, 2), solid("#f2c233" if elite else "#3aa04a")))
    return look


def jaguar_hood(p: Painter, look: Look) -> Look:
    pelt = p.speckle("#e3b84e", ("#6b4a1e", 0.25), ("#f2d27a", 0.1))
    look.head = layered(look.head, p.skin((8, 8, 8), pelt, bottom=None, front=masked(p, pelt, HELMET_FRONT),
                                          right=masked(p, pelt, HELMET_SIDE), back=rows_only(p, pelt, 0, 7)))
    look.inflate["head"] = 0.6
    look.head_extras += [cuboid((2, -1, 32), (2, 1, 2), solid("#e3b84e")), cuboid((-4, -1, 32), (2, 1, 2),
                                                                                  solid("#e3b84e"))]
    return look


def crown(look: Look) -> Look:
    gold = solid("#f2c233")
    look.head_extras.append(cuboid((-4.5, -4.5, 32), (9, 9, 1.5), gold))
    for x, y in ((-4.5, -4.5), (3, -4.5), (-4.5, 3), (3, 3), (-0.75, 3.5), (-0.75, -4.5)):
        look.head_extras.append(cuboid((x, y, 33.5), (1.5, 1.5, 2), gold))
    look.head_extras.append(cuboid((-0.75, 3.8, 32.3), (1.5, 1, 1.5), solid("#d8342a")))
    return look


# --------------------------------------------------------------------------- civilians

VILLAGER_SKIN = "#b8866c"
TASKS = {  # task: (tool, carried block colours, hat)
    "lumberjack": (lambda: items.axe("stone"), ("#6b5132", "#9c7c4c"), None),
    "gold_miner": (lambda: items.pickaxe("stone"), ("#8a8a8a", "#f2c233"), None),
    "stone_miner": (lambda: items.pickaxe("stone"), ("#8a8a8a", "#6a6a6a"), None),
    "farmer": (lambda: items.hoe("iron"), ("#c8a43a", "#a88422"), "straw"),
    "builder": (lambda: items.hammer("iron"), None, None),
    "repairer": (lambda: items.hammer("iron"), None, None),
    "hunter": (lambda: items.bow(), ("#b8433a", "#e8a09a"), None),
    "fisherman": (lambda: items.fishing_rod(), ("#9a8a6a", "#c8b894"), "bucket"),
    "forager": (lambda: items.shears(), ("#b8322a", "#3a7a2a"), None),
    "shepherd": (lambda: items.shears(), ("#b8433a", "#e8a09a"), None),
}
WORK_STYLE = {"hunter": "bow", "fisherman": "fish", "forager": "gather", "shepherd": "shear"}


def villager(key: str = "villager") -> Unit:
    """The generic villager: robe in team colour, arms crossed like in Minecraft."""
    p = Painter(key)
    robe = PC(0.6)
    head, nose = villager_head(p, VILLAGER_SKIN)
    robe_tex = p.skin((8, 6, 18), p.bands((1, PC(0.45)), (16, robe), (1, PC(0.35))), top=robe, bottom=robe,
                      front=p.grid(["LLLLLLLL"] + ["RRRDDRRR"] * 16 + ["DDDDDDDD"],
                                   {"L": PC(0.45), "R": robe, "D": PC(0.4)}))
    sleeve = p.skin((4, 4, 8), p.bands((6, robe), (2, VILLAGER_SKIN)), top=robe, bottom=VILLAGER_SKIN)
    hands = p.skin((8, 4, 4), robe, front=p.grid(["RRRRRRRR", "RRssssRR", "RRssssRR", "RRRRRRRR"],
                                                  {"R": robe, "s": VILLAGER_SKIN}))
    leg = p.skin((4, 4, 12), p.bands((9, "#5a4636"), (3, "#3b2c21")), bottom="#3b2c21")

    root = Part("root")
    torso = Part("torso", pivot=(0, 0, 12), boxes=[cuboid((-4, -3, 6), (8, 6, 18), robe_tex, 0.5)])
    torso.add(Part("head", pivot=(0, 0, 24), boxes=[cuboid((-4, -4, 24), (8, 8, 10), head)] + nose),
              Part("arms", pivot=(0, 1, 21), rot=(43, 0, 0), boxes=[
                  cuboid((4, -2, 15), (4, 4, 8), sleeve), cuboid((-8, -2, 15), (4, 4, 8), sleeve),
                  cuboid((-4, -2, 15), (8, 4, 4), hands)]))
    root.add(torso,
             Part("leg_r", pivot=(2, 0, 12), boxes=[cuboid((0, -2, 0), (4, 4, 12), leg)]),
             Part("leg_l", pivot=(-2, 0, 12), boxes=[cuboid((-4, -2, 0), (4, 4, 12), leg)]))
    return Unit(key, "Villager", "Villager", "villager", root, group="civilian")


def worker(task: str) -> Unit:
    """A villager at work: arms uncrossed, holding the task's tool (and carrying its resource)."""
    key = f"villager_{task}"
    p = Painter(key)
    tool, carried, hat = TASKS[task]
    look = illager_look(p, skin=VILLAGER_SKIN, coat=PC(0.6), shirt=PC(0.5), pants="#5a4636", robe=PC(0.6),
                        brow="#4a2c22", eyes="#2f8a3a", sleeve=PC(0.6))
    if hat == "straw":
        straw = p.speckle("#e2c46a", ("#c8a44a", 0.3))
        look.head_extras += [cuboid((-8, -8, 33), (16, 16, 1), p.skin((16, 16, 1), straw)),
                             cuboid((-4.5, -4.5, 33), (9, 9, 3), p.skin((9, 9, 3), straw))]
    elif hat == "bucket":
        look.head_extras += [cuboid((-5, -5, 33), (10, 10, 3), p.skin((10, 10, 3), p.speckle("#6b8a5a",
                                                                                        ("#55704a", 0.3))))]
    carry = None
    if carried:
        carry = p.skin((7, 7, 7), p.speckle(carried[0], (carried[1], 0.35)))
    left_bow = task == "hunter"
    tool_item = tool()
    root = biped(look, p, right=None if left_bow else tool_item, left=tool_item if left_bow else None,
                 arms=((20, 0, 0), (0, 0, 0)), carry=carry)
    title = task.replace("_", " ").title()
    return Unit(key, f"Villager ({title})", title, "biped", root, group="civilian",
                attack=WORK_STYLE.get(task, "chop"), carry=carry is not None)


def cleric(key: str = "monk", name: str = "Cleric", replaces: str = "Monk") -> Unit:
    """Monk: a Minecraft cleric villager in a hooded team-colour robe, holding a book."""
    p = Painter(key)
    robe = PC(0.5)
    look = illager_look(p, skin=VILLAGER_SKIN, coat=robe, shirt=PC(0.4), pants="#3a2a20", robe=robe,
                        brow="#4a2c22", eyes="#2f8a3a", sleeve=robe)
    hood = PC(0.42)
    look.head = layered(look.head, p.skin((8, 8, 10), hood, bottom=None,
                                          front=masked(p, hood, ["hhhhhhhh", "hhhhhhhh", "h......h", "h......h"]
                                                       + ["h......h"] * 3 + ["........"] * 3),
                                          back=hood))
    look.inflate["head"] = 0.5
    root = biped(look, p, right=items.book(), arms=((35, 0, 10), (25, 0, -10)))
    return Unit(key, name, replaces, "biped", root, group="civilian", attack="cast")


# --------------------------------------------------------------------------- roster of foot units

def _crafter_variant(key, name, replaces, **kw):
    return lambda: crafter(key, name, replaces, **kw)


def _king() -> Unit:
    p = Painter("king")
    look = crown(armour_up(p, crafter_look(p), "netherite", "clb"))
    look.torso_extras.append(cape(p))
    root = biped(look, p, right=items.sword("gold"), arms=((15, 0, 0), (0, 0, 0)))
    return Unit("king", "Crowned Crafter", "King", "biped", root, group="civilian")


def _parrot_warrior(elite: bool) -> Unit:
    key = "elite_eagle_warrior" if elite else "eagle_warrior"
    p = Painter(key)
    look = feathered(p, crafter_look(p, skin="#9a6a48", hair="#1e1410", eyes="#2a1a10",
                                     pants="#6b3f1d"), elite)
    if elite:
        armour_up(p, look, "gold", "c")
    root = biped(look, p, right=items.club(), arms=((15, 0, 0), (0, 0, 0)))
    return Unit(key, ("Elite " if elite else "") + "Parrot Warrior",
                ("Elite " if elite else "") + "Eagle Warrior", "biped", root)


def _jaguar() -> Unit:
    p = Painter("jaguar_warrior")
    look = jaguar_hood(p, crafter_look(p, skin="#9a6a48", hair="#1e1410", eyes="#2a1a10", pants="#6b3f1d"))
    root = biped(look, p, right=items.club(), arms=((15, 0, 0), (0, 0, 0)))
    return Unit("jaguar_warrior", "Ocelot Warrior", "Jaguar Warrior", "biped", root, civ="Aztecs")


def _zombie(key, name, replaces, kind="zombie", weapon=None, civ=None) -> Unit:
    p = Painter(key)
    look = zombie_look(p, kind)
    root = biped(look, p, right=weapon, arms=((85, 0, 0), (85, 0, 0)))
    return Unit(key, name, replaces, "biped", root, attack="punch", civ=civ)


def _piglin(key, name, replaces, brute, weapon, attack, civ) -> Unit:
    p = Painter(key)
    root = biped(piglin_look(p, brute), p, right=weapon, arms=((15, 0, 0), (0, 0, 0)))
    return Unit(key, name, replaces, "biped", root, attack=attack, civ=civ)


def _vindicator() -> Unit:
    p = Painter("berserk")
    look = illager_look(p, coat="#232a2e", pants="#3a3f44")
    root = biped(look, p, right=items.axe("iron"), arms=((15, 0, 0), (0, 0, 0)))
    return Unit("berserk", "Vindicator", "Berserk", "biped", root, civ="Vikings")


def _wither_samurai() -> Unit:
    p = Painter("samurai")
    look = skeleton_look(p, "wither", cap="iron")
    look.arm_size = look.leg_size = (2, 2, 14)
    look.arm = look.leg = p.skin((2, 2, 14), p.speckle("#2e2e2e", ("#1f1f1f", 0.25)))
    root = biped(look, p, right=items.sword("stone"), arms=((15, 0, 0), (0, 0, 0)))
    return Unit("samurai", "Wither Samurai", "Samurai", "biped", root, civ="Japanese")


def _illusioner() -> Unit:
    p = Painter("chu_ko_nu")
    look = illager_look(p, coat=PC(0.5), shirt=PC(0.4), robe=PC(0.55), sleeve=PC(0.5))
    return pillager("chu_ko_nu", "Illusioner", "Chu Ko Nu", look=look, glint=True, civ="Chinese")


def _hand_cannoneer() -> Unit:
    return crafter("hand_cannoneer", "Firework Gunner", "Hand Cannoneer", armour="iron", pieces="h",
                   weapon=items.hand_cannon(), attack="gun")


FOOT = {
    # civilians
    "villager": villager,
    **{f"villager_{t}": (lambda t=t: worker(t)) for t in TASKS},
    "monk": cleric,
    "king": _king,
    # swordsmen
    "militia": _crafter_variant("militia", "Crafter", "Militia", sword="wood"),
    "man_at_arms": _crafter_variant("man_at_arms", "Leather Crafter", "Man-at-Arms", armour="leather",
                                    pieces="hc", sword="stone"),
    "long_swordsman": _crafter_variant("long_swordsman", "Chainmail Knight", "Long Swordsman", armour="chain",
                                       sword="iron"),
    "two_handed": _crafter_variant("two_handed", "Iron Knight", "Two-Handed Swordsman", armour="iron",
                                   sword="iron", has_cape=True),
    "champion": _crafter_variant("champion", "Diamond Champion", "Champion", armour="diamond", sword="diamond",
                                 has_cape=True),
    # spearmen
    "spearman": lambda: drowned("spearman", "Drowned", "Spearman"),
    "pikeman": lambda: drowned("pikeman", "Chainmail Drowned", "Pikeman", "chain", "hc"),
    "halberdier": lambda: drowned("halberdier", "Iron Drowned", "Halberdier", "iron", "hc"),
    # eagles
    "eagle_warrior": lambda: _parrot_warrior(False),
    "elite_eagle_warrior": lambda: _parrot_warrior(True),
    # archers
    "archer": skeleton_archer,
    "crossbowman": lambda: pillager("crossbowman", "Pillager", "Crossbowman"),
    "arbalest": lambda: pillager("arbalest", "Pillager Captain", "Arbalest", helmet="iron", banner=True),
    "skirmisher": lambda: snow_golem("skirmisher", "Snow Golem", "Skirmisher"),
    "elite_skirmisher": lambda: snow_golem("elite_skirmisher", "Lantern Snow Golem", "Elite Skirmisher", True),
    "hand_cannoneer": _hand_cannoneer,
    "petard": creeper,
    # unique foot units
    "longbowman": lambda: skeleton_archer("longbowman", kind="stray", name="Stray Longbow", replaces="Longbowman",
                                          tall_bow=True, civ="Britons"),
    "woad_raider": lambda: _zombie("woad_raider", "Zombie", "Woad Raider", weapon=None, civ="Celts"),
    "chu_ko_nu": _illusioner,
    "throwing_axeman": lambda: _piglin("throwing_axeman", "Piglin", "Throwing Axeman", False, items.axe("gold"),
                                       "throw", "Franks"),
    "huskarl": lambda: _piglin("huskarl", "Piglin Brute", "Huskarl", True, items.axe("gold"), "chop", "Goths"),
    "samurai": _wither_samurai,
    "war_elephant": iron_golem,
    "teutonic_knight": _crafter_variant("teutonic_knight", "Netherite Knight", "Teutonic Knight",
                                        armour="netherite", sword="diamond", has_cape=True, civ="Teutons"),
    "janissary": blaze,
    "berserk": _vindicator,
    "jaguar_warrior": _jaguar,
    "plumed_archer": lambda: skeleton_archer("plumed_archer", kind="bogged", name="Bogged",
                                             replaces="Plumed Archer", civ="Mayans"),
}
