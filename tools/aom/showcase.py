"""Showcase renders: whole landscapes with the mod's figures and buildings, for screenshots and videos.

A `Scene` is a flat landscape of Minecraft blocks (one block type per 16x16-pixel cell: grass, sand, paths,
snow, water...) seen through the game's camera, with the mod's models standing on it. Everything is drawn
bigger than in the game (2 or 3 screen pixels per Minecraft pixel instead of 1.5) and every model keeps its
depth, so figures are hidden correctly behind buildings and walls. Shadows fall on the ground; the water sits a
little lower than the land, clear over the sand near the shore and deep blue further out, with surf along the
beach. Cloud shadows can drift over it all.

Positions are map tiles (i, j), as in the game: tile (i, j) is drawn (i - j) * 48 and (i + j) * 24 pixels from
tile (0, 0) at the game's size. `finish()` grades a rendered image (contrast, warm light, cool shadows, a
vignette and a tilt-shift blur that makes the map look like a miniature).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageFilter

from . import props
from .animation import pose
from .geometry import Part, Pose, cuboid
from .render import AMBIENT, DIFFUSE, LIGHT, OUTLINE, PLAYER, SHADOW, SOLID, SUN, Frame, fit_camera, render
from .textures import FACES, parse
from .voxel import BUILDING_HEADING, all_blocks

SCALE = 3.0  # screen pixels per Minecraft pixel (the game draws 1.5)
COS, SIN = math.cos(math.radians(30)), math.sin(math.radians(30))  # the game's camera looks down at 30 degrees
C = math.sqrt(0.5)
TILE = 64 * C  # Minecraft pixels per map tile along the block grid (about 2.83 blocks)
WATER_DROP = 3.0  # the water surface is this many pixels below the land
Tile = tuple[float, float]


# --------------------------------------------------------------------------- coordinates

def world(i: float, j: float) -> tuple[float, float]:
    """Ground position (x east, y north, in Minecraft pixels) of map tile (i, j)."""
    return (i - j) * 32.0, -(i + j) * 32.0


def _tiles(x, y):
    """Map tile (i, j) of ground position (x, y): the inverse of world()."""
    return (x - y) / 64.0, (-y - x) / 64.0


def screen(x: float, y: float, z: float = 0.0, scale: float = SCALE) -> tuple[float, float]:
    return x * scale, -(y * SIN + z * COS) * scale


def depth(x, y, z=0.0):
    """Distance along the view ray (bigger is further away)."""
    return y * COS - z * SIN


def heading_to(i: float, j: float, ti: float, tj: float, step: float = 22.5) -> float:
    """The heading (degrees, 0 = east) from tile (i, j) toward (ti, tj), snapped like the game's sprite angles."""
    x0, y0 = world(i, j)
    x1, y1 = world(ti, tj)
    h = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return round(h / step) * step if step else h


# the eight directions the game shows, by the name of the screen direction the figure faces
FACING = {"S": -90.0, "SW": -135.0, "W": 180.0, "NW": 135.0, "N": 90.0, "NE": 45.0, "E": 0.0, "SE": -45.0}


# --------------------------------------------------------------------------- noise

def _hash(a: np.ndarray, b: np.ndarray, seed: int) -> np.ndarray:
    n = (a.astype(np.int64) * 374761393 + b.astype(np.int64) * 668265263 + seed * 144269504) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0


def noise(x, y, seed: int = 0) -> np.ndarray:
    """Smooth value noise in 0..1 with features about one unit apart."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xi, yi = np.floor(x), np.floor(y)
    fx, fy = x - xi, y - yi
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash(xi, yi, seed), _hash(xi + 1, yi, seed)
    c, d = _hash(xi, yi + 1, seed), _hash(xi + 1, yi + 1, seed)
    return (a + (b - a) * sx) * (1 - sy) + (c + (d - c) * sx) * sy


def fbm(x, y, seed: int = 0, octaves: int = 3) -> np.ndarray:
    total, amp, norm = 0.0, 1.0, 0.0
    for k in range(octaves):
        total = total + amp * noise(x * 2 ** k, y * 2 ** k, seed + 17 * k)
        norm += amp
        amp *= 0.5
    return total / norm


# --------------------------------------------------------------------------- the ground

Where = Callable[[np.ndarray, np.ndarray], np.ndarray]


def disc(ci: float, cj: float, r: float, wobble: float = 0.0, seed: int = 0) -> Where:
    def where(i, j):
        d = np.hypot(i - ci, j - cj)
        if wobble:
            d = d + (fbm(i / 2.5, j / 2.5, seed) - 0.5) * 2 * wobble
        return d < r
    return where


def path(points: list[Tile], width: float, wobble: float = 0.0, seed: int = 0) -> Where:
    """Everything within `width` / 2 tiles of the polyline through `points`."""
    def where(i, j):
        best = np.full(np.shape(i), np.inf)
        for (a0, b0), (a1, b1) in zip(points, points[1:]):
            da, db = a1 - a0, b1 - b0
            t = np.clip(((i - a0) * da + (j - b0) * db) / max(da * da + db * db, 1e-9), 0, 1)
            best = np.minimum(best, np.hypot(i - a0 - t * da, j - b0 - t * db))
        if wobble:
            best = best + (fbm(i / 2, j / 2, seed) - 0.5) * 2 * wobble
        return best < width / 2
    return where


def beyond(a: float, b: float, c: float, wobble: float = 0.0, seed: int = 0, scale: float = 3.0) -> Where:
    """The side of the line a*i + b*j = c where a*i + b*j > c (a coastline, with `wobble` tiles of noise)."""
    norm = math.hypot(a, b)
    def where(i, j):
        s = (a * i + b * j - c) / norm
        if wobble:
            s = s + (fbm(i / scale, j / scale, seed) - 0.5) * 2 * wobble
        return s > 0
    return where


def patches(scale: float, cover: float, seed: int = 0) -> Where:
    """Noise blobs about `scale` tiles across covering roughly `cover` of the map."""
    threshold = 1 - cover
    def where(i, j):
        return fbm(i / scale, j / scale, seed) > 0.25 + 0.5 * threshold
    return where


def rect(i0: float, i1: float, j0: float, j1: float) -> Where:
    return lambda i, j: (i >= i0) & (i < i1) & (j >= j0) & (j < j1)


def both(*fs: Where) -> Where:
    return lambda i, j: np.logical_and.reduce([f(i, j) for f in fs])


def either(*fs: Where) -> Where:
    return lambda i, j: np.logical_or.reduce([f(i, j) for f in fs])


def but(f: Where, g: Where) -> Where:
    return lambda i, j: f(i, j) & ~g(i, j)


ROTATES = {"grass_block", "sand", "red_sand", "snow", "dirt", "coarse_dirt", "podzol", "gravel", "moss_block",
           "mycelium", "stone"}  # top textures turned at random per block, like Minecraft's grass


class Ground:
    """The block under every cell: `base` everywhere, then each painted layer over it in order."""

    def __init__(self, base: str = "grass_block", seed: int = 1, tint: tuple[float, float, float] = (1, 1, 1),
                 variation: float = 0.07):
        self.base, self.seed, self.tint, self.variation = base, seed, np.array(tint), variation
        self.layers: list[tuple[str, Where]] = []

    def paint(self, block: str, where: Where) -> "Ground":
        self.layers.append((block, where))
        return self

    def names(self) -> list[str]:
        out = [self.base]
        for b, _ in self.layers:
            if b not in out:
                out.append(b)
        return out

    def cells(self, bu: np.ndarray, bv: np.ndarray) -> np.ndarray:
        """Block codes (indices into names()) of the cells (bu, bv)."""
        names = self.names()
        j, i = (bu + 0.5) * 16 / TILE, (bv + 0.5) * 16 / TILE
        out = np.zeros(np.shape(bu), np.int16)
        for b, where in self.layers:
            out[where(i, j)] = names.index(b)
        return out


@lru_cache(maxsize=None)
def _faces(name: str) -> dict[str, np.ndarray]:
    return {f: tex[..., :3] for f, tex in all_blocks()[name].faces.items()}


def _shade(normal) -> float:
    return AMBIENT + DIFFUSE * max(0.0, float(np.dot(normal, LIGHT)))


_R = np.array([[-C, C], [-C, -C]])  # building model axes (u, v) -> world (x, y): model +x faces screen south-west
SHADE_TOP = _shade((0, 0, 1))
SHADE_U = _shade((*_R[:, 0], 0))  # the +u faces (screen south-west)
SHADE_V = _shade((*_R[:, 1], 0))  # the +v faces (screen south-east)


def _extruded(u, v, solid: Callable, drop: float):
    """Rays that cross a horizontal layer `drop` pixels thick, entered at (u, v) on its top plane: which side face
    of a solid cell (per `solid(bu, bv)`) each one hits before reaching the bottom plane.

    Returns (face, a, along, cu, cv): face 0 = none, 1 = a +u face, 2 = a +v face; `a` is how far down the
    layer the hit is (0..1); `along` the position across the face; (cu, cv) the cell hit. A ray moves toward -u
    and -v as it goes down.
    """
    delta = C * drop * math.sqrt(3)
    bu, bv = np.floor(u / 16), np.floor(v / 16)
    fu, fv = u - 16 * bu, v - 16 * bv
    au = np.where(fu < delta, fu / delta, np.inf)  # when the ray crosses into the cell at -u
    av = np.where(fv < delta, fv / delta, np.inf)
    u_first = au <= av
    a1, a2 = np.minimum(au, av), np.maximum(au, av)
    c1u, c1v = np.where(u_first, bu - 1, bu), np.where(u_first, bv, bv - 1)
    hit1 = np.isfinite(a1) & solid(c1u, c1v)
    hit2 = ~hit1 & np.isfinite(a2) & solid(bu - 1, bv - 1)  # on into the diagonal cell
    face = np.where(hit1, np.where(u_first, 1, 2), np.where(hit2, np.where(u_first, 2, 1), 0)).astype(np.int8)
    a = np.where(hit1, a1, np.where(hit2, a2, 0.0))
    cu, cv = np.where(hit1, c1u, bu - 1), np.where(hit1, c1v, bv - 1)
    along = np.where(face == 1, v - a * delta, u - a * delta)
    return face, a, along, cu, cv


# --------------------------------------------------------------------------- models

_UNITS = {}


def units() -> dict:
    if not _UNITS:
        from .roster import build_all
        _UNITS.update(build_all())
    return _UNITS


@lru_cache(maxsize=2500)
def figure_frame(key: str, heading: float, action: str, t: float, scale: float = SCALE) -> Frame:
    u = units()[key]
    ps = pose(u, action, t)
    return render(u.root, heading, ps, fit_camera(u.root, heading, ps, scale=scale * u.scale))


@lru_cache(maxsize=600)
def _model_frame(spec: tuple, variant: int, count: int, t: float, heading: float, scale: float) -> Frame:
    root = props.build(dict(spec), variant=variant, count=count, t=t)
    return render(root, heading, camera=fit_camera(root, heading, scale=scale))


def model_frame(spec: dict, variant: int = 0, count: int = 3, t: float = 0.0,
                heading: float = BUILDING_HEADING, scale: float = SCALE) -> Frame:
    return _model_frame(tuple(sorted(spec.items())), variant, count, t, heading, scale)


def part_frame(root: Part, heading: float, p: Pose = None, shadow: bool = True, scale: float = SCALE) -> Frame:
    return render(root, heading, p, fit_camera(root, heading, p, scale=scale), shadow=shadow)


DECOR = ("tuft", "flowers", "pebbles", "bush", "fern")


@lru_cache(maxsize=300)
def decor_frame(kind: str, variant: int, scale: float = SCALE) -> Frame:
    """Small things for the grass: tufts of grass, flowers, pebbles, a leafy bush."""
    from . import nature as NA
    from .voxel import Structure
    if kind in ("tuft", "fern", "flowers"):
        s = NA.plants(variant * 3 + 1, kind == "flowers", count=2 if kind != "fern" else 1)
    elif kind == "pebbles":
        s = NA.boulder(variant, 26.0 + 6 * (variant % 3))
    else:
        s = Structure("bush", origin=(0.5, 0.5))
        s.set(0, 0, 0, ("oak_leaves", "azalea_leaves", "flowering_azalea_leaves", "dark_oak_leaves")[variant % 4])
    root = s.part(all_blocks())
    return render(root, BUILDING_HEADING, camera=fit_camera(root, BUILDING_HEADING, scale=scale))


def cube(colour: str, size: float) -> Part:
    tex = np.tile(parse(colour), (2, 2, 1))
    return Part("cube", boxes=[cuboid((-size / 2, -size / 2, -size / 2), (size, size, size),
                                      {f: tex for f in FACES})])


@dataclass
class Placed:
    frame: Frame
    player: int
    x: float
    y: float
    z: float
    caster: bool = False  # a building or tree: figures standing in its shadow are shaded
    alpha: float = 1.0  # below 1: blended over what is behind it (smoke, clouds of dust)
    glow: float = 0.0  # added light (fire, explosions)
    shade: float = 1.0


def _outline_depth(frame: Frame) -> np.ndarray:
    """Depth for every pixel of the frame, outline pixels taking their nearest body neighbour's."""
    d = np.where((frame.kind == SOLID) | (frame.kind == PLAYER), frame.depth, np.inf)
    near = d.copy()
    near[1:] = np.minimum(near[1:], d[:-1])
    near[:-1] = np.minimum(near[:-1], d[1:])
    near[:, 1:] = np.minimum(near[:, 1:], d[:, :-1])
    near[:, :-1] = np.minimum(near[:, :-1], d[:, 1:])
    return np.where(frame.kind == OUTLINE, near, d)


def _layers_of(frame: Frame, player: int):
    """Colour, coverage and depth of a frame in a player's colours (kept with the frame, so a cache that drops
    the frame drops these too)."""
    cache = frame.__dict__.setdefault("_layers", {})
    if player not in cache:
        rgba = frame.to_rgba(player, shadow_alpha=0).astype(np.float32) / 255
        cache[player] = (rgba[..., :3], rgba[..., 3] > 0, _outline_depth(frame).astype(np.float32))
    return cache[player]


# --------------------------------------------------------------------------- the scene

@dataclass
class Clouds:
    """Soft shadows of clouds drifting over the map."""
    cover: float = 0.4
    size: float = 9.0  # tiles across
    drift: tuple[float, float] = (0.5, -0.35)  # tiles per second (i, j)
    darkness: float = 0.2
    seed: int = 3

    def shade(self, i, j, time: float = 0.0):
        n = fbm((i - self.drift[0] * time) / self.size, (j - self.drift[1] * time) / self.size, self.seed, 3)
        edge = 1 - self.cover
        return np.clip((n - edge) / 0.12, 0, 1) * self.darkness


class Scene:
    """A landscape and what stands on it; `render()` draws any window of it."""

    def __init__(self, ground: Ground, clouds: Optional[Clouds] = None, scale: float = SCALE):
        self.ground = ground
        self.clouds = clouds
        self.scale = scale  # screen pixels per Minecraft pixel
        self.items: list[Placed] = []
        self.sun_tint = np.array([1.04, 1.0, 0.93])

    # ---------------------------------------------------------------- placing things

    def add(self, frame: Frame, i: float, j: float, z: float = 0.0, player: int = 1, **kw) -> Placed:
        x, y = world(i, j)
        item = Placed(frame, player, x, y, z, **kw)
        self.items.append(item)
        return item

    def figure(self, key: str, i: float, j: float, facing, action: str = "idle", t: float = 0.0, player: int = 1,
               z: float = 0.0, **kw) -> Placed:
        """A unit. `facing` is a heading in degrees, a direction name ("SW") or a tile (i, j) to face."""
        if isinstance(facing, str):
            heading = FACING[facing]
        elif isinstance(facing, tuple):
            heading = heading_to(i, j, *facing)
        else:
            heading = float(facing)
        t = round((t % 1.0 if action != "die" else min(t, 1.0)) * 48) / 48
        if units()[key].group == "ship" and z == 0.0:
            z = -WATER_DROP
        return self.add(figure_frame(key, heading, action, t, self.scale), i, j, z, player, **kw)

    def model(self, spec: dict, i: float, j: float, player: int = 1, variant: int = 0, t: float = 0.0,
              heading: float = BUILDING_HEADING, caster: bool = True, **kw) -> Placed:
        """A building, tree, resource or decoration (a props.build spec)."""
        return self.add(model_frame(spec, variant, 3, t, heading, self.scale), i, j, kw.pop("z", 0.0), player,
                        caster=caster, **kw)

    def building(self, code: str, style: str, age: int, i: float, j: float, player: int = 1, **kw) -> Placed:
        extra = {k: kw.pop(k) for k in list(kw) if k in ("level", "stage")}
        return self.model({"model": "building", "code": code, "style": style, "age": age, **extra}, i, j, player,
                          **kw)

    def part(self, root: Part, i: float, j: float, heading: float = 0.0, player: int = 1, p: Pose = None,
             z: float = 0.0, shadow: bool = True, **kw) -> Placed:
        return self.add(part_frame(root, heading, p, shadow, self.scale), i, j, z, player, **kw)

    def scatter(self, area: tuple[float, float, float, float], count: int, kinds: dict[str, float] = None,
                seed: int = 0, on: tuple[str, ...] = ("grass_block",), where: Where = None, clear: float = 0.6) -> None:
        """Sprinkle `count` tries of small decorations over the tile rectangle `area` (i0, i1, j0, j1): only on
        the named ground blocks, inside `where`, and not under buildings or trees placed so far."""
        kinds = kinds or {"tuft": 5, "flowers": 2, "fern": 2, "pebbles": 1, "bush": 1}
        rng = np.random.default_rng(seed)
        i0, i1, j0, j1 = area
        ii, jj = rng.uniform(i0, i1, count), rng.uniform(j0, j1, count)
        names = self.ground.names()
        codes = self.ground.cells(np.floor(jj * TILE / 16), np.floor(ii * TILE / 16))
        ok = np.isin(codes, [names.index(n) for n in on if n in names])
        if where is not None:
            ok &= where(ii, jj)
        for it in self.items:
            if it.caster:
                ci, cj = _tiles(it.x, it.y)
                r = it.frame.kind.shape[1] / (96 * self.scale / 1.5) / 2 + clear
                ok &= np.hypot(ii - ci, jj - cj) > r
        names_k, weights = list(kinds), np.array(list(kinds.values()), float)
        for i, j in zip(ii[ok], jj[ok]):
            kind = names_k[rng.choice(len(names_k), p=weights / weights.sum())]
            self.add(decor_frame(kind, int(rng.integers(0, 6)), self.scale), i, j, player=7)

    # ---------------------------------------------------------------- drawing

    def render(self, centre: Tile, size: tuple[int, int], time: float = 0.0) -> "Shot":
        W, H = size
        cx, cy = screen(*world(*centre), scale=self.scale)
        sx0, sy0 = cx - W / 2, cy - H / 2
        sx = sx0 + np.arange(W) + 0.5
        sy = sy0 + np.arange(H) + 0.5
        SX, SY = np.meshgrid(sx, sy)
        rgb, zbuf, gx, gy, water = self._ground(SX, SY, time)
        ground_px = np.ones((H, W), bool)
        shadow = np.zeros((H, W), np.float32)
        caster_shadow = np.zeros((H, W), bool)
        glow = np.zeros((H, W), np.float32)

        order = sorted(self.items, key=lambda it: (it.alpha < 1, -depth(it.x, it.y, it.z)))
        for it in order:  # shadows first: they only ever darken the ground
            f = it.frame
            ox, oy = screen(it.x, it.y, it.z, self.scale)
            x0, y0 = int(round(ox - sx0)) - f.hotspot[0], int(round(oy - sy0)) - f.hotspot[1]
            sl = _clip(x0, y0, f.kind.shape, (H, W))
            if sl is None:
                continue
            (cy0, cy1, cx0, cx1), (fy0, fy1, fx0, fx1) = sl
            sh = f.kind[fy0:fy1, fx0:fx1] == SHADOW
            shadow[cy0:cy1, cx0:cx1][sh] = np.maximum(shadow[cy0:cy1, cx0:cx1][sh], it.alpha)
            if it.caster:
                caster_shadow[cy0:cy1, cx0:cx1] |= sh
        for it in order:
            f = it.frame
            ox, oy = screen(it.x, it.y, it.z, self.scale)
            x0, y0 = int(round(ox - sx0)) - f.hotspot[0], int(round(oy - sy0)) - f.hotspot[1]
            sl = _clip(x0, y0, f.kind.shape, (H, W))
            if sl is None:
                continue
            (cy0, cy1, cx0, cx1), (fy0, fy1, fx0, fx1) = sl
            col, body, dep = _layers_of(f, it.player)
            col, body, dep = col[fy0:fy1, fx0:fx1], body[fy0:fy1, fx0:fx1], dep[fy0:fy1, fx0:fx1]
            d = dep + depth(it.x, it.y, it.z)
            z = zbuf[cy0:cy1, cx0:cx1]
            front = body & (d <= z + 0.75)
            if not front.any():
                continue
            shade = it.shade
            if not it.caster:  # a figure standing in a building's shadow
                fy, fx = int(round(oy - sy0)), int(round(ox - sx0))
                if 0 <= fy < H and 0 <= fx < W and caster_shadow[fy, fx]:
                    shade *= 0.72
            c = col * shade
            if it.alpha < 1:
                target = rgb[cy0:cy1, cx0:cx1]
                target[front] = target[front] * (1 - it.alpha) + c[front] * it.alpha
            else:
                rgb[cy0:cy1, cx0:cx1][front] = c[front]
                z[front] = d[front]
                ground_px[cy0:cy1, cx0:cx1][front] = False
            if it.glow:
                glow[cy0:cy1, cx0:cx1][front] += it.glow
        cool = np.array([0.80, 0.86, 1.0])
        s = (shadow * ground_px)[..., None]
        rgb = rgb * (1 - s) + rgb * s * 0.58 * cool
        lit = (1 - s) * 1.0
        rgb = rgb * (lit * self.sun_tint + (1 - lit))
        if self.clouds is not None:  # worked out on a coarse grid: the shadows are soft anyway
            step = 8
            ci, cj = gy[::step, ::step], gx[::step, ::step]
            ti, tj = _tiles(ci, cj)
            dark = self.clouds.shade(ti, tj, time).astype(np.float32)
            dark = np.asarray(Image.fromarray(dark).resize((W, H), Image.BILINEAR))
            rgb = rgb * (1 - dark[..., None])
        return Shot(rgb, glow, ground_px, shadow)

    def _ground(self, SX, SY, time):
        H, W = SX.shape
        X = SX / self.scale
        Y = -SY / (self.scale * SIN)
        u, v = -C * X - C * Y, C * X - C * Y
        bu, bv = np.floor(u / 16).astype(int), np.floor(v / 16).astype(int)
        u0, v0 = bu.min() - 3, bv.min() - 3
        gu = np.arange(u0, bu.max() + 4)
        gv = np.arange(v0, bv.max() + 4)
        GU, GV = np.meshgrid(gu, gv, indexing="ij")
        grid = self.ground.cells(GU, GV)
        names = self.ground.names()
        wet_code = names.index("water") if "water" in names else -1

        def code(cu, cv):
            cu = np.clip(np.asarray(cu, int) - u0, 0, grid.shape[0] - 1)
            cv = np.clip(np.asarray(cv, int) - v0, 0, grid.shape[1] - 1)
            return grid[cu, cv]

        tops = np.stack([_faces(n)["top"] for n in names])
        sides_u = np.stack([_faces(n)["right"] for n in names])
        sides_v = np.stack([_faces(n)["front"] for n in names])
        rot = (_hash(GU, GV, self.ground.seed + 5) * 4).astype(int)
        jitter = 1 + (_hash(GU, GV, self.ground.seed + 9) - 0.5) * 0.07

        cells = code(bu, bv)
        fu, fv = u - 16 * bu, v - 16 * bv
        col = 15 - np.floor(fu).astype(int)
        row = np.floor(fv).astype(int)
        r = rot[bu - u0, bv - v0] * np.isin(cells, [names.index(n) for n in names if n in ROTATES])
        col, row = _turn(col, row, r)
        # large, gentle light and dark patches, block by block like Minecraft's biome shading
        big = fbm((GV + 0.5) * 16 / TILE / 7, (GU + 0.5) * 16 / TILE / 7, self.ground.seed + 21)
        jitter = jitter * (1 + (big - 0.5) * 2 * self.ground.variation)
        rgb = tops[cells, row, col] * SHADE_TOP
        rgb *= jitter[bu - u0, bv - v0][..., None]
        rgb *= self.ground.tint
        zbuf = depth(X, Y)
        gx, gy = X.copy(), Y.copy()
        water = np.zeros((H, W), bool)
        if wet_code >= 0:
            water = cells == wet_code
            self._water(rgb, zbuf, water, X, Y, u, v, code, wet_code, tops, sides_u, sides_v, time, grid, u0, v0)
        return rgb, zbuf, gx, gy, water

    def _water(self, rgb, zbuf, water, X, Y, u, v, code, wet, tops, sides_u, sides_v, time, grid, u0, v0):
        h = WATER_DROP
        uw, vw = u[water], v[water]
        land = lambda cu, cv: code(cu, cv) != wet
        face, a, along, hit_u, hit_v = _extruded(uw, vw, land, h)
        idx = np.nonzero(water)
        # the sides of the land blocks along the shore (the top rows of their side texture)
        for f, sides, shade in ((1, sides_u, SHADE_U), (2, sides_v, SHADE_V)):
            sel = face == f
            if not sel.any():
                continue
            cells = code(hit_u[sel], hit_v[sel])
            c_along = np.floor(along[sel] % 16).astype(int)
            if f == 2:
                c_along = 15 - c_along
            row = np.clip(np.floor(h * a[sel]).astype(int), 0, 15)
            px = (idx[0][sel], idx[1][sel])
            rgb[px] = sides[cells, row, c_along] * shade
            zbuf[px] = depth(X[px], Y[px] + a[sel] * h * math.sqrt(3), -h * a[sel])
        # the water surface
        surf = face == 0
        px = (idx[0][surf], idx[1][surf])
        Yw = Y[px] + h * math.sqrt(3)
        su, sv = uw[surf] - C * h * math.sqrt(3), vw[surf] - C * h * math.sqrt(3)
        zbuf[px] = depth(X[px], Yw, -h)
        # distance to the shore, in blocks, smooth across cells
        dist = _shore_distance(grid == wet)
        gu, gv = su / 16 - 0.5 - u0, sv / 16 - 0.5 - v0
        D = _bilinear(dist, gu, gv)
        wtex = tops[wet]
        flow = time * 3.0
        wc = wtex[(np.floor(sv + flow * 0.6) % 16).astype(int), (15 - np.floor(su + flow) % 16).astype(int)]
        bed = _faces("sand")["top"][(np.floor(sv) % 16).astype(int), (15 - np.floor(su) % 16).astype(int)]
        opacity = np.clip(0.30 + 0.20 * D, 0.30, 0.94)[..., None]
        deep = np.clip((D - 1.5) / 7, 0, 1)[..., None]
        colour = bed * 0.95 * (1 - opacity) + wc * 1.05 * opacity
        colour = colour * (1 - 0.35 * deep) + np.array([0.05, 0.12, 0.32]) * 0.35 * deep
        colour *= SHADE_TOP
        # sparkles, a texel at a time
        tu, tv = np.floor(su), np.floor(sv)
        sparkle = _hash(tu + np.floor(time * 5) * 131, tv, 77) > 0.9965
        colour[sparkle] = colour[sparkle] * 0.3 + 0.75
        # surf along the beach
        fu, fv = su - 16 * np.floor(su / 16), sv - 16 * np.floor(sv / 16)
        cu, cv = np.floor(su / 16), np.floor(sv / 16)
        dmin = np.full(fu.shape, np.inf)
        for du, dv, dd in ((1, 0, 16 - fu), (-1, 0, fu), (0, 1, 16 - fv), (0, -1, fv),
                           (1, 1, np.hypot(16 - fu, 16 - fv)), (-1, -1, np.hypot(fu, fv)),
                           (1, -1, np.hypot(16 - fu, fv)), (-1, 1, np.hypot(fu, 16 - fv))):
            dmin = np.where(land(cu + du, cv + dv), np.minimum(dmin, dd), dmin)
        dq = np.floor(dmin)
        wave = 2.2 + 1.6 * np.sin(time * 2.4 + (np.floor(su / 4) + np.floor(sv / 4)) * 0.9)
        foam = dq < wave
        colour[foam] = colour[foam] * 0.35 + np.array([0.93, 0.96, 1.0]) * 0.65
        rgb[px] = colour


def _turn(col, row, r):
    """Rotate texel coordinates by r quarter turns (per block)."""
    c, w = col.copy(), row.copy()
    for k, (a, b) in enumerate(((None, None), (lambda c, w: w, lambda c, w: 15 - c),
                                (lambda c, w: 15 - c, lambda c, w: 15 - w), (lambda c, w: 15 - w, lambda c, w: c))):
        if k == 0:
            continue
        sel = r == k
        c[sel], w[sel] = a(col[sel], row[sel]), b(col[sel], row[sel])
    return c, w


def _shore_distance(wet: np.ndarray, steps: int = 12) -> np.ndarray:
    """Blocks from each water cell to the nearest land cell (0 on land), by repeated growing."""
    dist = np.where(wet, float(steps), 0.0)
    frontier = ~wet
    for s in range(1, steps + 1):
        grown = frontier.copy()
        grown[1:] |= frontier[:-1]
        grown[:-1] |= frontier[1:]
        grown[:, 1:] |= frontier[:, :-1]
        grown[:, :-1] |= frontier[:, 1:]
        new = grown & ~frontier
        dist[new & wet] = np.minimum(dist[new & wet], s)
        frontier = grown
    return dist


def _bilinear(grid: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, grid.shape[0] - 1.001)
    y = np.clip(y, 0, grid.shape[1] - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (grid[x0, y0] * (1 - fx) * (1 - fy) + grid[x0 + 1, y0] * fx * (1 - fy)
            + grid[x0, y0 + 1] * (1 - fx) * fy + grid[x0 + 1, y0 + 1] * fx * fy)


def _clip(x0: int, y0: int, shape, canvas):
    h, w = shape
    H, W = canvas
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if cx0 >= cx1 or cy0 >= cy1:
        return None
    return (cy0, cy1, cx0, cx1), (cy0 - y0, cy1 - y0, cx0 - x0, cx1 - x0)


# --------------------------------------------------------------------------- finishing

@dataclass
class Shot:
    rgb: np.ndarray  # (H, W, 3) linear-ish colour, 0..1
    glow: np.ndarray  # (H, W) extra light from fire and explosions
    ground: np.ndarray  # (H, W) pixels showing the ground
    shadow: np.ndarray  # (H, W) shadowed ground


def finish(shot: Shot, tilt: float = 0.28, blur: float = 3.2, vignette: float = 0.28, contrast: float = 1.08,
           saturation: float = 1.12, bloom: float = 0.35) -> Image.Image:
    """Grade a render: contrast, saturation, glow, a vignette and a tilt-shift blur (0 turns it off)."""
    img = np.clip(shot.rgb, 0, 1.2)
    lum = img @ np.array([0.299, 0.587, 0.114])
    img = lum[..., None] + (img - lum[..., None]) * saturation
    img = 0.46 + (img - 0.46) * contrast
    if shot.glow.any():
        g = np.clip(shot.glow, 0, 1)
        halo = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(14)),
                          np.float32) / 255
        img = img + (halo * 0.9 + g * 0.2)[..., None] * np.array([1.0, 0.62, 0.25]) * bloom * 2
    H, W = lum.shape
    if vignette:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) / math.sqrt(2)
        img = img * (1 - vignette * np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6)[..., None]
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    if tilt:
        soft = out.filter(ImageFilter.GaussianBlur(blur))
        y = np.abs(np.arange(H) / H - 0.5) * 2  # 0 in the middle, 1 at the top and bottom edges
        m = np.clip((y - (1 - 2 * tilt)) / (2 * tilt), 0, 1) ** 1.3
        mask = Image.fromarray((np.repeat(m[:, None], W, 1) * 255).astype(np.uint8))
        out = Image.composite(soft, out, mask)
    return out
