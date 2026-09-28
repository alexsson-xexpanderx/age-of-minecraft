"""Orthographic ray-caster that draws box models the way AoE2 shows units.

AoE2 uses a 2:1 isometric view: the camera looks "north" and down at 30
degrees, so ground distances shrink by half on screen. Every screen pixel
casts a parallel ray into the scene and picks the nearest textured box face
(nearest-texel sampling, no anti-aliasing -> crisp pixel art).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .colors import player_rgb
from .geometry import PlacedBox, Pose, affine, place, rotation

# Pixel kinds, mirroring what an SLP frame can hold.
TRANSPARENT, SOLID, PLAYER, SHADOW, OUTLINE = range(5)

LIGHT = np.array([-0.6, -0.8, 1.2]) / np.linalg.norm([-0.6, -0.8, 1.2])  # shading: upper-left-front
SUN = np.array([-1.0, 0.35, 2.2]) / np.linalg.norm([-1.0, 0.35, 2.2])  # shadows fall to the lower right
AMBIENT, DIFFUSE = 0.5, 0.55

# Entry face per axis, keyed by whether the local ray runs toward -axis
# (then it enters through the +axis face).
_FACE = {(0, True): "right", (0, False): "left", (1, True): "front", (1, False): "back",
         (2, True): "top", (2, False): "bottom"}


@dataclass
class Camera:
    width: int = 96
    height: int = 96
    origin: tuple[float, float] = (48, 80)  # screen position of the model origin (the hotspot)
    scale: float = 1.5  # screen pixels per Minecraft pixel
    elevation: float = 30.0

    def rays(self) -> tuple[np.ndarray, np.ndarray]:
        a = np.radians(self.elevation)
        d = np.array([0.0, np.cos(a), -np.sin(a)])
        right = np.array([1.0, 0.0, 0.0])
        up = np.array([0.0, np.sin(a), np.cos(a)])
        jj, ii = np.mgrid[0:self.height, 0:self.width]
        u = (ii + 0.5 - self.origin[0]) / self.scale
        v = (self.origin[1] - (jj + 0.5)) / self.scale
        o = u[..., None] * right + v[..., None] * up - 500.0 * d
        return o.reshape(-1, 3), d

    def window(self, points: np.ndarray) -> np.ndarray:
        """Flat indices of the pixels covering the screen bounding box of world `points`."""
        a = np.radians(self.elevation)
        x = points[:, 0] * self.scale + self.origin[0]
        y = self.origin[1] - (points[:, 1] * np.sin(a) + points[:, 2] * np.cos(a)) * self.scale
        c0, c1 = max(int(np.floor(x.min())) - 1, 0), min(int(np.ceil(x.max())) + 1, self.width)
        r0, r1 = max(int(np.floor(y.min())) - 1, 0), min(int(np.ceil(y.max())) + 1, self.height)
        if c0 >= c1 or r0 >= r1:
            return np.zeros(0, int)
        return (np.arange(r0, r1)[:, None] * self.width + np.arange(c0, c1)).ravel()


@dataclass
class Frame:
    """One rendered frame, kept palette-agnostic until export."""

    kind: np.ndarray  # (H, W) pixel kinds
    rgb: np.ndarray  # (H, W, 3) colour of SOLID pixels, 0..1
    light: np.ndarray  # (H, W) lightness of PLAYER pixels, 0..1
    hotspot: tuple[int, int]
    depth: np.ndarray = None  # (H, W) distance along the view ray from the model origin's plane (inf: nothing)

    def to_rgba(self, player: int = 1, shadow_alpha: float = 0.4,
                outline_rgb=(0.08, 0.07, 0.06)) -> np.ndarray:
        h, w = self.kind.shape
        out = np.zeros((h, w, 4))
        solid = self.kind == SOLID
        out[solid, :3] = self.rgb[solid]
        pc = self.kind == PLAYER
        out[pc, :3] = player_rgb(player, self.light[pc])
        out[solid | pc, 3] = 1
        out[self.kind == OUTLINE] = (*outline_rgb, 1)
        out[self.kind == SHADOW] = (0, 0, 0, shadow_alpha)
        return (out * 255 + 0.5).astype(np.uint8)


def _slabs(pb: PlacedBox, O: np.ndarray, D: np.ndarray):
    """Ray/box slab test in the box's local frame."""
    R, t = pb.matrix[:3, :3], pb.matrix[:3, 3]
    o = (O - t) @ R  # R^T (p - t) for each row
    d = R.T @ D
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    t1 = (pb.box.lo - o) / d
    t2 = (pb.box.hi - o) / d
    tmin = np.minimum(t1, t2)
    tnear = tmin.max(axis=1)
    tfar = np.maximum(t1, t2).min(axis=1)
    return o, d, tnear, tfar, tmin.argmax(axis=1)


def _uv(face: str, p: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    size = hi - lo
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    if face == "front":
        return (hi[0] - x) / size[0], (hi[2] - z) / size[2]
    if face == "back":
        return (x - lo[0]) / size[0], (hi[2] - z) / size[2]
    if face == "right":
        return (y - lo[1]) / size[1], (hi[2] - z) / size[2]
    if face == "left":
        return (hi[1] - y) / size[1], (hi[2] - z) / size[2]
    if face == "top":
        return (hi[0] - x) / size[0], (y - lo[1]) / size[1]
    return (hi[0] - x) / size[0], (hi[1] - y) / size[1]  # bottom


_NORMAL = {"right": (1, 0, 0), "left": (-1, 0, 0), "front": (0, 1, 0), "back": (0, -1, 0),
           "top": (0, 0, 1), "bottom": (0, 0, -1)}


def _corners(pb: PlacedBox) -> np.ndarray:
    lo, hi = pb.box.lo, pb.box.hi
    local = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    return local @ pb.matrix[:3, :3].T + pb.matrix[:3, 3]


def _cast(boxes: list[PlacedBox], O: np.ndarray, D: np.ndarray, camera: Camera):
    n = len(O)
    depth = np.full(n, np.inf)
    texel = np.zeros((n, 5), np.float32)
    shade = np.zeros(n)
    for pb in boxes:
        win = camera.window(_corners(pb))  # only rays that can reach this box
        if not len(win):
            continue
        o, d, tnear, tfar, axis = _slabs(pb, O[win], D)
        hit = np.nonzero((tfar >= tnear) & (tnear < depth[win]))[0]
        if not len(hit):
            continue
        p = o[hit] + tnear[hit, None] * d
        for k in range(3):
            sel = axis[hit] == k
            if not sel.any():
                continue
            face = _FACE[(k, bool(d[k] < 0))]
            tex = pb.box.faces[face]
            u, v = _uv(face, p[sel], pb.box.lo, pb.box.hi)
            th, tw = tex.shape[:2]
            col = np.clip((u * tw).astype(int), 0, tw - 1)
            row = np.clip((v * th).astype(int), 0, th - 1)
            tx = tex[row, col]
            ok = tx[:, 3] > 0
            local = hit[sel][ok]
            rows = win[local]
            depth[rows] = tnear[local]
            texel[rows] = tx[ok]
            n_world = pb.matrix[:3, :3] @ np.array(_NORMAL[face], float)
            shade[rows] = AMBIENT + DIFFUSE * max(0.0, float(n_world @ LIGHT))
    return depth, texel, shade


def _shadowed(boxes: list[PlacedBox], ground: np.ndarray, camera: Camera) -> np.ndarray:
    """Which ground points (one per pixel) have a box between them and the sun."""
    hit = np.zeros(len(ground), bool)
    for pb in boxes:
        c = _corners(pb)
        footprint = c - (c[:, 2:3] / SUN[2]) * SUN  # corners dropped onto the ground along the sun ray
        win = camera.window(footprint)
        if not len(win):
            continue
        _, _, tnear, tfar, _ = _slabs(pb, ground[win] + SUN * 0.01, SUN)
        hit[win] |= (tfar >= tnear) & (tfar > 0)
    return hit


def model_matrix(heading: float) -> np.ndarray:
    """World transform for a model facing `heading` (degrees, 0 = east, 90 = north)."""
    return affine(rotation(rz=heading - 90.0))


def fit_camera(root, heading: float, pose: Pose = None, scale: float = 1.5,
               elevation: float = 30.0, pad: int = 4) -> Camera:
    """A camera just big enough for the model and its shadow (used for buildings)."""
    boxes = place(root, pose or Pose(), model_matrix(heading))
    pts = np.concatenate([_corners(pb) for pb in boxes])
    pts = np.concatenate([pts, pts - (pts[:, 2:3] / SUN[2]) * SUN])
    a = np.radians(elevation)
    x = pts[:, 0] * scale
    y = -(pts[:, 1] * np.sin(a) + pts[:, 2] * np.cos(a)) * scale
    x0, x1 = int(np.floor(x.min())) - pad, int(np.ceil(x.max())) + pad
    y0, y1 = int(np.floor(y.min())) - pad, int(np.ceil(y.max())) + pad
    return Camera(width=x1 - x0, height=y1 - y0, origin=(-x0, -y0), scale=scale, elevation=elevation)


def render(root, heading: float, pose: Pose = None, camera: Camera = None,
           shadow: bool = True, outline: bool = True) -> Frame:
    pose = pose or Pose()
    camera = camera or Camera()
    boxes = place(root, pose, model_matrix(heading))
    O, D = camera.rays()
    depth, texel, shade = _cast(boxes, O, D, camera)

    H, W = camera.height, camera.width
    drawn = np.isfinite(depth)
    kind = np.full(H * W, TRANSPARENT, np.uint8)
    is_pc = drawn & (texel[:, 4] > 0)
    kind[drawn & ~is_pc] = SOLID
    kind[is_pc] = PLAYER
    rgb = np.clip(texel[:, :3] * shade[:, None], 0, 1)
    if pose.tint is not None:
        r, g, b, s = pose.tint
        rgb = rgb * (1 - s) + np.array([r, g, b]) * s * rgb.mean(axis=1, keepdims=True) * 2
        rgb = np.clip(rgb, 0, 1)
    light = np.clip(texel[:, 0] * shade, 0, 1)

    if shadow:
        ground = O + (-O[:, 2] / D[2])[:, None] * D
        kind[~drawn & _shadowed(boxes, ground, camera)] = SHADOW

    kind = kind.reshape(H, W)
    if outline:
        body = (kind == SOLID) | (kind == PLAYER)
        edge = np.zeros_like(body)
        edge[1:, :] |= body[:-1, :]
        edge[:-1, :] |= body[1:, :]
        edge[:, 1:] |= body[:, :-1]
        edge[:, :-1] |= body[:, 1:]
        kind[edge & ~body] = OUTLINE

    # the rays start 500 units before the plane through the model origin (Camera.rays)
    return Frame(kind, rgb.reshape(H, W, 3), light.reshape(H, W),
                 (int(round(camera.origin[0])), int(round(camera.origin[1]))), (depth - 500.0).reshape(H, W))
