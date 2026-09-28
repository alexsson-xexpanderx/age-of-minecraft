"""Held items, drawn as Minecraft-style extruded pixel sprites.

Upright items (swords, tools, bows, tridents) stand in the y-z plane:
columns run forward, rows run down, and `anchor` is the pixel held in the
hand. Flat items (crossbows) are drawn from above and laid horizontal.
All art is original.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .geometry import Part, Vec3, voxel_sprite
from .textures import Painter, Spec

STICK, STICK_DARK = "#7a5530", "#4f361c"

MATERIALS = {  # edge, light, dark
    "wood": ("#5e4222", "#b08953", "#6e4d28"),
    "stone": ("#555555", "#a2a2a2", "#4a4a4a"),
    "copper": ("#8a4a2c", "#e0875a", "#b0603a"),
    "iron": ("#7d7d7d", "#f0f0f0", "#5c5c5c"),
    "gold": ("#b38a14", "#fff27a", "#8f6b0e"),
    "diamond": ("#168b7e", "#8ff7ea", "#12685e"),
    "netherite": ("#2a2528", "#6f676b", "#3b3437"),
}


@dataclass
class Item:
    rows: list[str]
    legend: dict[str, Spec]
    anchor: tuple[int, int]
    voxel: float = 0.85
    rot: Vec3 = (-70, 0, 0)  # rest tilt relative to a hanging arm
    thickness: float = 1.0
    flat: bool = False  # drawn from above; laid horizontal when held


def _tool_legend(material: str) -> dict[str, Spec]:
    edge, light, dark = MATERIALS[material]
    return {"E": edge, "L": light, "G": dark, "H": STICK, "P": STICK_DARK, "s": STICK}


def sword(material: str = "iron") -> Item:
    return Item(["..E..", ".ELE.", ".ELE.", ".ELE.", ".ELE.", ".ELE.", ".ELE.", ".ELE.", ".ELE.",
                 "GGGGG", "..H..", "..H..", "..P.."], _tool_legend(material), anchor=(2, 11))


def axe(material: str = "iron") -> Item:
    return Item([".GLE.", ".GLLE", ".GLLE", ".GLE.", ".s...", ".s...", ".s...", ".s...", ".s...", ".s...",
                 ".P..."], _tool_legend(material), anchor=(1, 9))


def pickaxe(material: str = "iron") -> Item:
    return Item([".GLLLG.", "E..s..E", "...s...", "...s...", "...s...", "...s...", "...s...", "...s...",
                 "...P..."], _tool_legend(material), anchor=(3, 7))


def hoe(material: str = "iron") -> Item:
    return Item([".GLLE", ".s..E", ".s...", ".s...", ".s...", ".s...", ".s...", ".s...", ".P..."],
                _tool_legend(material), anchor=(1, 7))


def hammer(material: str = "iron") -> Item:
    """Builder's hammer (a Minecraft-style mace)."""
    return Item(["GLLLG", "GLLLG", "..s..", "..s..", "..s..", "..s..", "..s..", "..P.."],
                _tool_legend(material), anchor=(2, 6))


def club() -> Item:
    return Item([".GG.", "GLLG", "GLLG", "GLLG", ".GG.", "..s.", "..s.", "..s.", "..s.", "..P."],
                {"G": "#5a3d1f", "L": "#8a6236", "s": STICK, "P": STICK_DARK}, anchor=(2, 8))


def shears() -> Item:
    return Item(["E.E", "L.L", "L.L", ".E.", "R.R", "R.R"],
                {"E": "#7d7d7d", "L": "#e8e8e8", "R": "#b33a2a"}, anchor=(1, 4), voxel=0.7, rot=(-40, 0, 0))


def trident() -> Item:
    return Item(["T.T.T", "T.T.T", "TTTTT", "..T..", "..s..", "..s..", "..s..", "..s..", "..s..", "..s..",
                 "..s..", "..s..", "..s..", "..s..", "..s..", "..s.."],
                {"T": "#4fc0b0", "s": "#3d8a80"}, anchor=(2, 11), rot=(-80, 0, 0))


def spear(material: str = "iron") -> Item:
    edge, light, _ = MATERIALS[material]
    return Item([".L.", "ELE", "ELE", ".s.", ".s.", ".s.", ".s.", ".s.", ".s.", ".s.", ".s.", ".s.", ".s.",
                 ".s.", ".s."], {"E": edge, "L": light, "s": STICK}, anchor=(1, 10), rot=(-80, 0, 0))


def bow(tall: bool = False) -> Item:
    rows = ["sW....", "s.W...", "s..W..", "s..W..", "s...W.", "s...W.", "s....W", "s....G", "s....W",
            "s...W.", "s...W.", "s..W..", "s..W..", "s.W...", "sW...."]
    if tall:  # longbow
        rows = rows[:7] + ["s....W"] * 4 + rows[7:8] + ["s....W"] * 4 + rows[8:]
    return Item(rows, {"s": "#e6e6e6", "W": "#8a5a2b", "G": "#3f2a18"}, anchor=(5, len(rows) // 2),
                voxel=1.0, rot=(0, 0, 0))


def fishing_rod() -> Item:
    return Item(["s.....", "s.....", "s.....", "s.....", "s.....", "s.....", "s.....", "s.....", "sR....",
                 ".s....", ".s....", ".s....", ".s....", ".s....", ".P...."],
                {"s": STICK, "P": STICK_DARK, "R": "#d8d8d8"}, anchor=(1, 13), rot=(-35, 0, 0))


def torch() -> Item:
    return Item([".Y.", "YFY", ".F.", ".s.", ".s.", ".s.", ".s.", ".P."],
                {"Y": "#ffd23a", "F": "#ff7a1a", "s": STICK, "P": STICK_DARK}, anchor=(1, 6), rot=(-20, 0, 0))


def book() -> Item:
    return Item(["CCCC", "CPPC", "CPPC", "CCCC", "CCCC"], {"C": "#5a2b6e", "P": "#e8e0c8"}, anchor=(1, 4),
                voxel=0.9, rot=(-60, 0, 0), thickness=2.0)


def hand_cannon() -> Item:
    """Copper tube on a wooden stock, fired from the shoulder (side view, muzzle forward)."""
    return Item(["...........", "CCCCCCCCCCM", "CKCCCCCCCCM", "WWW........", ".WW........"],
                {"C": "#c86f45", "K": "#8a4a2c", "M": "#5a3020", "W": "#6b4a2a"}, anchor=(2, 3),
                voxel=1.0, rot=(0, 0, 0), thickness=2.0)


def crossbow(glint: bool = False, limb: str = "#8f6537", voxel: float = 0.9) -> Item:
    """Top view, forward to the right; laid flat and carried at chest height."""
    wood = "#6b4a2a"
    legend = {"S": wood, "W": "#d4c4ff" if glint else limb, "s": "#e6e6e6", "A": "#9a9a9a", "a": "#dcdcdc"}
    return Item(["........W...", "........W...", ".......W....", "......sW....", ".....s.W....",
                 "SSSSSSSSSAAa", ".....s.W....", "......sW....", ".......W....", "........W...",
                 "........W..."], legend, anchor=(2, 5), voxel=voxel, rot=(0, 90, 0), flat=True)


def held(item: Item, name: str, at: Vec3, painter: Optional[Painter] = None, rot: Optional[Vec3] = None) -> Part:
    return voxel_sprite(name, item.rows, item.legend, anchor=item.anchor, at=at, voxel=item.voxel,
                        thickness=item.thickness, rot=item.rot if rot is None else rot, painter=painter)
