"""Unit models: Minecraft-style figures standing in for AoE2 units.

Every model is original pixel art in the Minecraft style (cuboid bodies,
8x8 faces, 16-colour-ish textures) rather than copied game textures. Player
colour (`PC`) marks the parts that show which team a unit belongs to.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .geometry import Part, cuboid, voxel_sprite
from .textures import PC, Painter, Spec, layered, parse


@dataclass
class Unit:
    key: str
    name: str  # in-mod name
    replaces: str  # AoE2 unit it replaces
    rig: str  # animation rig, see animation.py
    root: Part


# --------------------------------------------------------------------------- helpers

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
    "iron": lambda p: metal(p, "#d4d4d4", "#8c8c8c", "#fafafa"),
    "gold": lambda p: metal(p, "#f3d03e", "#b3861a", "#fff4a3"),
    "diamond": lambda p: metal(p, "#4fdfcd", "#1f8f82", "#c9fff5"),
    "netherite": lambda p: metal(p, "#4d4649", "#2f2a2d", "#716a6e"),
}

SWORD_ART = [
    "..E..",
    ".ELE.",
    ".ELE.",
    ".ELE.",
    ".ELE.",
    ".ELE.",
    ".ELE.",
    ".ELE.",
    ".ELE.",
    "GGGGG",
    "..H..",
    "..H..",
    "..P..",
]
SWORD_MATERIALS = {
    "wood": {"E": "#5e4222", "L": "#b08953", "G": "#6e4d28", "H": "#6b4a2a", "P": "#4a321b"},
    "stone": {"E": "#555555", "L": "#a2a2a2", "G": "#4a4a4a", "H": "#6b4a2a", "P": "#4a321b"},
    "iron": {"E": "#7d7d7d", "L": "#f0f0f0", "G": "#5c5c5c", "H": "#6b4a2a", "P": "#4a321b"},
    "gold": {"E": "#b38a14", "L": "#fff27a", "G": "#8f6b0e", "H": "#6b4a2a", "P": "#4a321b"},
    "diamond": {"E": "#168b7e", "L": "#8ff7ea", "G": "#12685e", "H": "#6b4a2a", "P": "#4a321b"},
}

BOW_ART = [
    "sW....",
    "s.W...",
    "s..W..",
    "s..W..",
    "s...W.",
    "s...W.",
    "s....W",
    "s....G",
    "s....W",
    "s...W.",
    "s...W.",
    "s..W..",
    "s..W..",
    "s.W...",
    "sW....",
]
BOW_LEGEND = {"s": "#e6e6e6", "W": "#8a5a2b", "G": "#3f2a18"}


# --------------------------------------------------------------------------- crafter (humanoid)

SKIN, SKIN_SHADE = "#c89478", "#a8765c"
HAIR = "#4b3222"
PANTS, SHOES, BELT, BUCKLE = "#3d3a5e", "#5a5a5a", "#5b3a1e", "#e0b44a"

FACE_LEGEND = {"h": HAIR, "s": SKIN, "S": SKIN_SHADE, "w": "#f4f4f4", "e": "#3a62b8",
               "n": SKIN_SHADE, "m": "#7a4636"}


def crafter(key: str, name: str, replaces: str, *, armour: Optional[str] = None,
            pieces: str = "hclb", sword: Optional[str] = None, cape: bool = False) -> Unit:
    """A Steve-like humanoid; `pieces` picks helmet/chestplate/leggings/boots."""
    p = Painter(key)
    shirt = PC(0.62)

    head = p.skin((8, 8, 8), HAIR, top=HAIR, bottom=SKIN,
                  front=p.grid(["hhhhhhhh",
                                "hhhhhhhh",
                                "hssssssh",
                                "ssssssss",
                                "swessews",
                                "sssnnsss",
                                "ssmmmmss",
                                "ssssssss"], FACE_LEGEND),
                  right=p.grid(["hhhhhhhh",
                                "hhhhhhhh",
                                "hhhhhsss",
                                "hhhhssss",
                                "hhhsssss",
                                "hhssssss",
                                "hsssssss",
                                "ssssssss"], FACE_LEGEND))
    body = p.skin((8, 4, 12), p.bands((9, shirt), (1, BELT), (2, PANTS)), top=shirt, bottom=PANTS,
                  front=p.grid(["PPPssPPP"] + ["PPPPPPPP"] * 8 + ["bbbyybbb", "pppppppp", "pppppppp"],
                               {"P": shirt, "s": SKIN, "b": BELT, "y": BUCKLE, "p": PANTS}))
    arm = p.skin((4, 4, 12), p.bands((4, shirt), (8, SKIN)), top=shirt, bottom=SKIN)
    leg = p.skin((4, 4, 12), p.bands((9, PANTS), (3, SHOES)), top=PANTS, bottom=SHOES)

    inflate = {"head": 0.0, "body": 0.0, "arm": 0.0, "leg": 0.0}
    if armour:
        mat = ARMOUR[armour](p)
        if "h" in pieces:
            head = layered(head, p.skin((8, 8, 8), mat, bottom=None,
                                        front=masked(p, mat, ["aaaaaaaa", "aaaaaaaa", "a......a", "a......a",
                                                              "........", "........", "........", "........"]),
                                        right=masked(p, mat, ["aaaaaaaa", "aaaaaaaa", "aaaaaaaa", "aaaaaaaa",
                                                              "aaaaa...", "aaaa....", "aaa.....", "........"]),
                                        back=rows_only(p, mat, 0, 6)))
            inflate["head"] = 0.6
        if "c" in pieces:
            body = layered(body, p.skin((8, 4, 12), rows_only(p, mat, 0, 8), top=mat, bottom=None))
            arm = layered(arm, p.skin((4, 4, 12), rows_only(p, mat, 0, 5), top=mat, bottom=None))
            inflate["body"] = inflate["arm"] = 0.5
        if "l" in pieces:
            body = layered(body, p.skin((8, 4, 12), rows_only(p, mat, 9, 11), top=None, bottom=mat))
            leg = layered(leg, p.skin((4, 4, 12), rows_only(p, mat, 0, 8), top=mat, bottom=None))
            inflate["leg"] = 0.4
        if "b" in pieces:
            leg = layered(leg, p.skin((4, 4, 12), rows_only(p, mat, 8, 11), top=None, bottom=mat))
            inflate["leg"] = 0.4

    root = Part("root")
    torso = Part("torso", pivot=(0, 0, 12), boxes=[cuboid((-4, -2, 12), (8, 4, 12), body, inflate["body"])])
    torso.add(
        Part("head", pivot=(0, 0, 24), boxes=[cuboid((-4, -4, 24), (8, 8, 8), head, inflate["head"])]),
        Part("arm_r", pivot=(6, 0, 22), boxes=[cuboid((4, -2, 12), (4, 4, 12), arm, inflate["arm"])]),
        Part("arm_l", pivot=(-6, 0, 22), boxes=[cuboid((-8, -2, 12), (4, 4, 12), arm, inflate["arm"])]),
    )
    if sword:
        torso.find("arm_r").add(voxel_sprite("item_r", SWORD_ART, SWORD_MATERIALS[sword], anchor=(2, 11),
                                             at=(6, 1.0, 13), voxel=0.85, rot=(-70, 0, 0), painter=p))
    if cape:
        cape_tex = p.skin((10, 1, 16), p.bands((15, PC(0.55)), (1, PC(0.35))), top=PC(0.5))
        torso.add(Part("cape", pivot=(0, -2.5, 24), rot=(-6, 0, 0),
                       boxes=[cuboid((-5, -3.5, 9), (10, 1, 15), cape_tex)]))
    root.add(torso,
             Part("leg_r", pivot=(2, 0, 12), boxes=[cuboid((0, -2, 0), (4, 4, 12), leg, inflate["leg"])]),
             Part("leg_l", pivot=(-2, 0, 12), boxes=[cuboid((-4, -2, 0), (4, 4, 12), leg, inflate["leg"])]))
    return Unit(key, name, replaces, "biped", root)


# --------------------------------------------------------------------------- villager

def villager(key: str = "villager") -> Unit:
    p = Painter(key)
    skin, shade = "#b8866c", "#9a6c55"
    robe = PC(0.6)
    leg_col, shoe = "#5a4636", "#3b2c21"
    legend = {"s": skin, "b": "#4a2c22", "w": "#f0f0f0", "g": "#2f8a3a"}

    head = p.skin((8, 8, 10), skin,
                  front=p.grid(["ssssssss", "ssssssss", "ssssssss", "sbbbbbbs", "swgssgws",
                                "ssssssss", "ssssssss", "ssssssss", "ssssssss", "ssssssss"], legend))
    nose = p.skin((2, 2, 4), shade)
    robe_tex = p.skin((8, 6, 18), p.bands((1, PC(0.45)), (16, robe), (1, PC(0.35))), top=robe, bottom=robe,
                      front=p.grid(["LLLLLLLL"] + ["RRRDDRRR"] * 16 + ["DDDDDDDD"],
                                   {"L": PC(0.45), "R": robe, "D": PC(0.4)}))
    sleeve = p.skin((4, 4, 8), p.bands((6, robe), (2, skin)), top=robe, bottom=skin)
    hands = p.skin((8, 4, 4), robe, front=p.grid(["RRRRRRRR", "RRssssRR", "RRssssRR", "RRRRRRRR"],
                                                  {"R": robe, "s": skin}))
    leg = p.skin((4, 4, 12), p.bands((9, leg_col), (3, shoe)), bottom=shoe)

    root = Part("root")
    torso = Part("torso", pivot=(0, 0, 12), boxes=[cuboid((-4, -3, 6), (8, 6, 18), robe_tex, 0.5)])
    head_part = Part("head", pivot=(0, 0, 24), boxes=[cuboid((-4, -4, 24), (8, 8, 10), head)])
    head_part.add(Part("nose", pivot=(0, 4, 27), boxes=[cuboid((-1, 4, 25), (2, 2, 4), nose)]))
    arms = Part("arms", pivot=(0, 1, 21), rot=(43, 0, 0), boxes=[
        cuboid((4, -2, 15), (4, 4, 8), sleeve),
        cuboid((-8, -2, 15), (4, 4, 8), sleeve),
        cuboid((-4, -2, 15), (8, 4, 4), hands),
    ])
    torso.add(head_part, arms)
    root.add(torso,
             Part("leg_r", pivot=(2, 0, 12), boxes=[cuboid((0, -2, 0), (4, 4, 12), leg)]),
             Part("leg_l", pivot=(-2, 0, 12), boxes=[cuboid((-4, -2, 0), (4, 4, 12), leg)]))
    return Unit(key, "Villager", "Villager", "villager", root)


# --------------------------------------------------------------------------- skeleton archer

def skeleton_archer(key: str = "skeleton_archer") -> Unit:
    p = Painter(key)
    bone, bone_d, dark, hole = "#c3c3c3", "#9c9c9c", "#4a4a4a", "#1c1c1c"
    legend = {"k": bone, "K": bone_d, "D": hole, "d": dark}
    head = p.skin((8, 8, 8), bone,
                  front=p.grid(["kkkkkkkk", "kkkkkkkk", "kkkkkkkk", "kDDkkDDk",
                                "kDDkkDDk", "kkkddkkk", "kdkdkdkk", "kkkkkkkk"], legend))
    cap = PC(0.55)
    head = layered(head, p.skin((8, 8, 8), cap, bottom=None,
                                front=masked(p, cap, ["cccccccc", "cccccccc"] + ["........"] * 6),
                                right=masked(p, cap, ["cccccccc", "cccccccc", "cccc....", "ccc....."]
                                             + ["........"] * 4),
                                back=rows_only(p, cap, 0, 3)))
    ribs = p.skin((8, 4, 12), bone,
                  front=p.grid(["kkkkkkkk", "dkkkkkkd", "kkkkkkkk", "dkkddkkd", "kkkkkkkk", "dkkddkkd",
                                "kkkkkkkk", "dddkkddd", "dddkkddd", "dddkkddd", "kkkkkkkk", "kkddddkk"], legend))
    tunic = PC(0.55)
    ribs = layered(ribs, p.skin((8, 4, 12), rows_only(p, metal(p, tunic, PC(0.35), PC(0.72)), 0, 7),
                                top=tunic, bottom=None))
    limb = p.skin((2, 2, 12), p.speckle(bone, (bone_d, 0.25)))
    quiver = p.skin((3, 2, 9), p.bands((2, "#e8e8e8"), (7, "#7a5230")), top="#e8e8e8")

    root = Part("root")
    torso = Part("torso", pivot=(0, 0, 12), boxes=[cuboid((-4, -2, 12), (8, 4, 12), ribs, 0.3),
                                                   cuboid((-3.5, -4.3, 14), (3, 2, 9), quiver)])
    torso.add(
        Part("head", pivot=(0, 0, 24), boxes=[cuboid((-4, -4, 24), (8, 8, 8), head, 0.3)]),
        Part("arm_r", pivot=(5, 0, 22), boxes=[cuboid((4, -1, 12), (2, 2, 12), limb)]),
        Part("arm_l", pivot=(-5, 0, 22), boxes=[cuboid((-6, -1, 12), (2, 2, 12), limb)]).add(
            voxel_sprite("item_l", BOW_ART, BOW_LEGEND, anchor=(5, 7), at=(-5, 1.0, 13), voxel=1.0,
                         painter=p)),
    )
    root.add(torso,
             Part("leg_r", pivot=(2, 0, 12), boxes=[cuboid((1, -1, 0), (2, 2, 12), limb)]),
             Part("leg_l", pivot=(-2, 0, 12), boxes=[cuboid((-3, -1, 0), (2, 2, 12), limb)]))
    return Unit(key, "Skeleton Archer", "Archer", "biped", root)


# --------------------------------------------------------------------------- creeper

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
    return Unit(key, "Creeper", "Petard", "quadruped", root)


# --------------------------------------------------------------------------- sheep

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
        Part("leg_fr", pivot=(3, 5, 12), boxes=[cuboid((1, 3, 0), (4, 4, 12), leg)]),
        Part("leg_fl", pivot=(-3, 5, 12), boxes=[cuboid((-5, 3, 0), (4, 4, 12), leg)]),
        Part("leg_br", pivot=(3, -5, 12), boxes=[cuboid((1, -7, 0), (4, 4, 12), leg)]),
        Part("leg_bl", pivot=(-3, -5, 12), boxes=[cuboid((-5, -7, 0), (4, 4, 12), leg)]),
    )
    return Unit(key, "Sheep", "Sheep", "quadruped", root)


# --------------------------------------------------------------------------- roster

ROSTER: dict[str, Callable[[], Unit]] = {
    "villager": villager,
    "militia": lambda: crafter("militia", "Crafter", "Militia", sword="wood"),
    "man_at_arms": lambda: crafter("man_at_arms", "Leather Crafter", "Man-at-Arms",
                                   armour="leather", pieces="hc", sword="stone"),
    "long_swordsman": lambda: crafter("long_swordsman", "Chainmail Knight", "Long Swordsman",
                                      armour="chain", pieces="hclb", sword="iron"),
    "two_handed": lambda: crafter("two_handed", "Iron Knight", "Two-Handed Swordsman",
                                  armour="iron", pieces="hclb", sword="iron", cape=True),
    "champion": lambda: crafter("champion", "Diamond Champion", "Champion",
                                armour="diamond", pieces="hclb", sword="diamond", cape=True),
    "skeleton_archer": skeleton_archer,
    "creeper": creeper,
    "sheep": sheep,
}
