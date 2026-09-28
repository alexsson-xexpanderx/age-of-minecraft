"""Box-model geometry.

Minecraft characters are built entirely from cuboids, so every unit is a
small tree of `Part`s, each holding axis-aligned `Box`es. All coordinates are
in model space and measured in Minecraft pixels:

    x = the character's right, y = forward (the way it faces), z = up,

with the origin on the ground between the feet. Each part rotates around its
own pivot (also given in model space) and carries its children along.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .textures import Painter, Spec, parse

Vec3 = tuple[float, float, float]


def rotation(rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> np.ndarray:
    """3x3 rotation from angles in degrees, applied x first, then y, then z.

    Positive rx swings a hanging limb forward; positive rz turns left.
    """
    ax, ay, az = np.radians([rx, ry, rz])
    cx, sx, cy, sy, cz, sz = np.cos(ax), np.sin(ax), np.cos(ay), np.sin(ay), np.cos(az), np.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def affine(R: np.ndarray = None, t: Vec3 = (0, 0, 0)) -> np.ndarray:
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    M[:3, 3] = t
    return M


@dataclass
class Box:
    lo: np.ndarray
    hi: np.ndarray
    faces: dict[str, np.ndarray]


def cuboid(origin: Vec3, size: Vec3, faces: dict[str, np.ndarray], inflate: float = 0.0) -> Box:
    """A box from its low corner and size; `inflate` grows it on every side (armour, wool)."""
    lo = np.asarray(origin, float) - inflate
    hi = np.asarray(origin, float) + np.asarray(size, float) + inflate
    return Box(lo, hi, faces)


@dataclass
class Part:
    name: str
    pivot: Vec3 = (0.0, 0.0, 0.0)
    rot: Vec3 = (0.0, 0.0, 0.0)  # rest pose, degrees
    boxes: list[Box] = field(default_factory=list)
    children: list["Part"] = field(default_factory=list)
    offset: Vec3 = (0.0, 0.0, 0.0)  # rest translation, e.g. a rider sitting on a horse

    def add(self, *children: "Part") -> "Part":
        self.children.extend(children)
        return self

    def find(self, name: str) -> Optional["Part"]:
        if self.name == name:
            return self
        for c in self.children:
            hit = c.find(name)
            if hit:
                return hit
        return None


@dataclass
class Pose:
    """Per-part rotations (degrees, added to the rest pose) and offsets for one frame."""

    rot: dict[str, Vec3] = field(default_factory=dict)
    move: dict[str, Vec3] = field(default_factory=dict)
    tint: Optional[tuple[float, float, float, float]] = None  # r, g, b, strength (hurt/death flash)
    hidden: set[str] = field(default_factory=set)  # parts (and their children) left out of this frame


@dataclass
class PlacedBox:
    box: Box
    matrix: np.ndarray  # rigid local -> world transform (4x4)


def place(part: Part, pose: Pose, parent: np.ndarray) -> list[PlacedBox]:
    if part.name in pose.hidden:
        return []
    rest = np.asarray(part.rot, float)
    extra = np.asarray(pose.rot.get(part.name, (0, 0, 0)), float)
    move = np.asarray(part.offset, float) + np.asarray(pose.move.get(part.name, (0, 0, 0)), float)
    pivot = np.asarray(part.pivot, float)
    M = parent @ affine(t=pivot + move) @ affine(rotation(*(rest + extra))) @ affine(t=-pivot)
    placed = [PlacedBox(b, M) for b in part.boxes]
    for child in part.children:
        placed += place(child, pose, M)
    return placed


def voxel_sprite(name: str, rows: list[str], legend: dict[str, Spec], anchor: tuple[int, int],
                 at: Vec3, voxel: float = 0.8, thickness: float = 1.0, rot: Vec3 = (0, 0, 0),
                 painter: Optional[Painter] = None) -> Part:
    """Extrude 2D pixel art into a 1-voxel-thick item, the way Minecraft draws held items.

    The sprite stands upright in the y-z plane (columns run forward, rows run
    down). The pixel at `anchor` (col, row) sits at model point `at`, which
    is also the part's pivot, so `rot` tilts the item around the grip.
    """
    ac, ar = anchor
    boxes = []
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            spec = legend.get(ch)
            if spec is None:
                continue
            texel = parse(spec)
            if painter is not None:
                texel = painter.jitter(texel[None, None].copy(), 0.05)[0, 0]
            faces = {f: texel[None, None].copy() for f in ("front", "back", "right", "left", "top", "bottom")}
            y = at[1] + (c - ac - 0.5) * voxel
            z = at[2] + (ar - r - 0.5) * voxel
            x = at[0] - thickness * voxel / 2
            boxes.append(cuboid((x, y, z), (thickness * voxel, voxel, voxel), faces))
    return Part(name, pivot=at, rot=rot, boxes=boxes)
