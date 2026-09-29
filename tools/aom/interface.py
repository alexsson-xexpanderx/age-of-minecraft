"""The in-game panels: the resource bar at the top and the command, info and minimap panel at the bottom.

The Conquerors draws them from one full-screen picture per civilisation and screen size in interfac.drs, with
the game view left transparent: 51101-51120 for 800x600, 51121-51140 for 1024x768 and 51141-51160 for
1280x1024 (UserPatch's data mod format calls this uiBaseId 51100, uiStride 20). UserPatch builds its
widescreen panels from the same pictures.

Each picture is repainted in the Minecraft style, every pixel keeping its place:

* the boxes in the resource bar, where the game writes the amounts in white, become dark sunk-in slots;
* the parchment the game writes on (large light areas, with their shaded border) becomes the grey of Minecraft's
  inventory, with a straight top edge, its black edge, white bevel at the top left and dark bevel at the bottom
  right;
* large dark areas become inventory slots, sunk in;
* everything else, the carved frames, becomes planks, as dark or light as the original frame was, so the
  game's white and black text stays readable on it;
* where the panels meet the game view they get a black edge, like every Minecraft window;
* the five resource icons in the top bar (wood, food, gold, stone, population) become an oak log, bread, a
  gold ingot, cobblestone and a villager's head.

The icons sit at fixed places in the 1280x1024 pictures (openage's hardcoded/interface.py). In the smaller
pictures they are found by matching the same civilisation's 1280x1024 icons; a picture whose icons can't be
found is left as it was, so no resource ever loses its icon.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable, Optional

import numpy as np

from . import slp
from . import voxel as V
from .geometry import Part, cuboid
from .palette import Quantiser
from .render import fit_camera, render
from .textures import Painter, parse

BASE, STRIDE = 51100, 20
SCREENS = ((800, 600), (1024, 768), (1280, 1024))
ICON_BOXES = [(8, 10), (85, 10), (162, 10), (239, 10), (316, 10)]  # top left of each 26x17 icon, 1280x1024
ICON_W, ICON_H = 26, 17
RESOURCES = ("wood", "food", "gold", "stone", "population")
GUI = {"panel": "#c6c6c6", "light": "#ffffff", "shade": "#555555", "edge": "#000000",
       "slot": "#8b8b8b", "slot_light": "#ffffff", "slot_shade": "#373737",
       "count": "#2b2b2b", "count_light": "#6b6b6b", "count_shade": "#111111"}  # where the bar's numbers are
PLANKS = ("birch_planks", "oak_planks", "jungle_planks", "acacia_planks", "spruce_planks", "dark_oak_planks")
LUMA = np.array([0.299, 0.587, 0.114])
PIXEL = 2  # screen pixels per Minecraft pixel, like Minecraft's GUI scale 2


def panels(get: Callable[[int], Optional[bytes]]) -> list[tuple[int, tuple[int, int], bytes, Optional[bytes]]]:
    """(SLP id, screen size, picture, the same civilisation's 1280x1024 picture) of every panel picture."""
    found = {}
    for sid in range(BASE + 1, BASE + STRIDE * len(SCREENS) + 1):
        data = get(sid)
        if data is None:
            continue
        try:
            w, h, _, _ = slp.info(data).sizes[0]
        except (ValueError, IndexError):
            continue
        if (w, h) in SCREENS:
            found[sid] = ((w, h), data)
    out = []
    for sid, (size, data) in sorted(found.items()):
        big = found.get(BASE + STRIDE * 2 + (sid - BASE - 1) % STRIDE + 1)
        out.append((sid, size, data, big[1] if big and big[0] == SCREENS[-1] else None))
    return out


# --------------------------------------------------------------------------- masks

def _shift(m: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """out[y, x] = m[y - dy, x - dx], False outside."""
    out = np.zeros_like(m)
    h, w = m.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = m[max(-dy, 0):h - max(dy, 0),
                                                                    max(-dx, 0):w - max(dx, 0)]
    return out


def _grow(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for d in range(1, r + 1):
        out |= _shift(m, 0, d) | _shift(m, 0, -d)
    rows = out.copy()
    for d in range(1, r + 1):
        out |= _shift(rows, d, 0) | _shift(rows, -d, 0)
    return out


def _shrink(m: np.ndarray, r: int) -> np.ndarray:
    return ~_grow(~m, r)


def _grow_across(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for d in range(1, r + 1):
        out |= _shift(m, 0, d) | _shift(m, 0, -d)
    return out


def _paper(lum: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """The parchment the game writes on: its light middle, plus the shaded parchment around it (up to 12 px; the
    unit's name is written on its top border), with the tears in its top edge filled so the panel is straight."""
    paper = _grow(_shrink(opaque & (lum > 0.62), 3), 3)
    shaded = opaque & (lum > 0.45)
    for _ in range(12):
        paper |= _grow(paper, 1) & shaded
    paper = _grow(_shrink(paper, 2), 2)  # not the frame's highlights next to it
    bridged = ~_grow_across(~_grow_across(paper, 48), 48)  # gaps up to 96 px wide...
    above = np.zeros_like(paper)
    for d in range(1, 41):
        above |= _shift(paper, -d, 0)  # ...right above the parchment: tears, not the frame between two panels
    paper |= bridged & above & opaque
    return _shrink(_grow(paper, 6), 6) & opaque  # the game's letters and logo on it


def _label(m: np.ndarray) -> tuple[np.ndarray, int]:
    """Connected parts of m (4-neighbours), numbered from 1, found run by run."""
    parent: list[int] = []

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    runs, prev = [], []
    for y in range(m.shape[0]):
        d = np.diff(np.concatenate(([0], m[y].astype(np.int8), [0])))
        cur = []
        for s, e in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            rid = len(parent)
            parent.append(rid)
            for ps, pe, pid in prev:
                if ps < e and pe > s:
                    parent[find(pid)] = find(rid)
            cur.append((s, e, rid))
            runs.append((y, s, e, rid))
        prev = cur
    lab = np.zeros(m.shape, np.int32)
    ids: dict[int, int] = {}
    for y, s, e, rid in runs:
        lab[y, s:e] = ids.setdefault(find(rid), len(ids) + 1)
    return lab, len(ids)


def _rectangles(m: np.ndarray, min_area: int = 40) -> np.ndarray:
    """Each part of m as its bounding rectangle (the small bits dropped)."""
    lab, n = _label(m)
    out = np.zeros_like(m)
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    for k in range(1, n + 1):
        if sizes[k] >= min_area:
            ys, xs = np.nonzero(lab == k)
            out[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = True
    return out


def _widen(boxes: np.ndarray, icons: Optional[list[tuple[int, int]]], more: int = 10, gap: int = 2) -> np.ndarray:
    """Each box as wide as it can be: `gap` pixels from the icon before it and from the next icon or box, at most
    `more` pixels wider on each side. Room for the game's numbers."""
    lab, n = _label(boxes)
    spans = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        spans.append((xs.min(), xs.max() + 1, ys.min(), ys.max() + 1))
    icons = icons or []
    starts = sorted([x for x, _ in icons] + [x0 for x0, _, _, _ in spans])
    ends = sorted([x + ICON_W for x, _ in icons] + [x1 for _, x1, _, _ in spans])
    out = boxes.copy()
    for x0, x1, y0, y1 in spans:
        right = min([x1 + more] + [x - gap for x in starts if x >= x1])
        left = max([x0 - more] + [x + gap for x in ends if x <= x0])
        out[y0:y1, max(0, left):max(x1, right)] = True
    return out


def _top_bar(opaque: np.ndarray) -> np.ndarray:
    """The resource bar: the rows at the top that are drawn all the way across."""
    full = opaque.mean(1) > 0.9
    rows = len(full) if full.all() else int(np.argmin(full))
    out = np.zeros_like(opaque)
    out[:rows] = True
    return out


def _near_edge(m: np.ndarray, r: int, sides: str) -> np.ndarray:
    """Pixels of m within r pixels of m's top/left ("tl") or bottom/right ("br") edge."""
    s = 1 if sides == "tl" else -1
    out = np.zeros_like(m)
    for d in range(1, r + 1):
        out |= ~_shift(m, s * d, 0) | ~_shift(m, 0, s * d)
    return m & out


# --------------------------------------------------------------------------- painting

def _tile(tex: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    big = tex[..., :3].repeat(PIXEL, 0).repeat(PIXEL, 1)
    reps = (shape[0] // big.shape[0] + 1, shape[1] // big.shape[1] + 1, 1)
    return np.tile(big, reps)[:shape[0], :shape[1]]


def _planks(target: float) -> np.ndarray:
    """The plank texture nearest in brightness to `target`, nudged to match it."""
    types = V.all_blocks()
    best = min(PLANKS, key=lambda n: abs((types[n].faces["front"][..., :3] @ LUMA).mean() - target))
    tex = types[best].faces["front"].copy()
    tex[..., :3] *= np.clip(target / max(1e-3, (tex[..., :3] @ LUMA).mean()), 0.8, 1.25)
    return np.clip(tex, 0, 1)


def _bevel(rgb: np.ndarray, m: np.ndarray, fill: str, tl: str, br: str, edge: Optional[str]) -> None:
    rgb[m] = parse(fill)[:3]
    inner = m
    if edge is not None:
        ring = _near_edge(m, PIXEL, "tl") | _near_edge(m, PIXEL, "br")
        inner = m & ~ring
    rgb[_near_edge(inner, PIXEL, "br")] = parse(br)[:3]
    rgb[_near_edge(inner, PIXEL, "tl")] = parse(tl)[:3]
    if edge is not None:
        rgb[ring] = parse(edge)[:3]


def restyle(rgb: np.ndarray, opaque: np.ndarray, icons: Optional[list[tuple[int, int]]]) -> np.ndarray:
    """A panel picture (RGB 0..1) in the Minecraft style; `icons` are the top left corners of the resource icons."""
    lum = rgb @ LUMA
    bar = _top_bar(opaque)
    paper = _paper(lum, opaque) & ~bar  # the parchment below the resource bar (its tears are filled)
    # the resource bar's boxes, each on its own (the game writes the amounts in them, in white)
    light = opaque & bar & (lum > 0.5)
    for x, y in icons or []:  # the icons themselves (gold is bright) are not boxes
        light[max(0, y - 2):y + ICON_H + 2, max(0, x - 2):x + ICON_W + 2] = False
    counts = _rectangles(_grow(_shrink(light, 2), 2)) & bar & opaque
    counts = _widen(counts, icons) & bar & opaque
    slots = _shrink(_grow(_grow(_shrink(opaque & (lum < 0.14), 3), 3), 2), 2) & opaque & ~paper & ~counts
    frame = opaque & ~paper & ~slots & ~counts
    out = np.zeros_like(rgb)
    if frame.any():
        out[frame] = _tile(_planks(float(lum[frame].mean())), opaque.shape)[frame]
    _bevel(out, slots, GUI["slot"], GUI["slot_shade"], GUI["slot_light"], None)
    _bevel(out, paper, GUI["panel"], GUI["light"], GUI["shade"], GUI["edge"])
    _bevel(out, counts, GUI["count"], GUI["count_shade"], GUI["count_light"], None)  # a dark slot, sunk in
    out[opaque & ~_shrink(opaque, PIXEL)] = parse(GUI["edge"])[:3]  # a black edge along the game view
    for (x, y), what in zip(icons or [], RESOURCES):
        icon = item(what)
        ih, iw = icon.shape[:2]
        x0, y0 = x + (ICON_W - iw) // 2, y + (ICON_H - ih) // 2
        region = out[y0:y0 + ih, x0:x0 + iw]
        solid = (icon[..., 3] > 0) & opaque[y0:y0 + ih, x0:x0 + iw]
        region[solid] = icon[..., :3][solid]
    return out


def repaint(codes: np.ndarray, palette: np.ndarray, quant: Quantiser,
            icons: Optional[list[tuple[int, int]]]) -> np.ndarray:
    """`restyle` for SLP pixel codes: in and out in the game's palette."""
    opaque = (codes >= 0) & (codes < 256)
    out = restyle(palette[np.clip(codes, 0, 255)].astype(np.float64) / 255, opaque, icons)
    new = codes.copy()
    new[opaque] = quant.indices(np.clip(out[opaque] * 255 + 0.5, 0, 255).astype(np.int64))
    return new


def find_icons(codes: np.ndarray, big: np.ndarray) -> Optional[list[tuple[int, int]]]:
    """Where the 1280x1024 picture's resource icons are in a smaller picture (its top 64 rows)."""
    from numpy.lib.stride_tricks import sliding_window_view
    top = codes[:64]
    if top.shape[0] < ICON_H or top.shape[1] < ICON_W:
        return None
    windows = sliding_window_view(top, (ICON_H, ICON_W))
    found = []
    for x, y in ICON_BOXES:
        icon = big[y:y + ICON_H, x:x + ICON_W]
        score = (windows == icon).mean(axis=(2, 3))
        yy, xx = np.unravel_index(score.argmax(), score.shape)
        if score[yy, xx] < 0.9:
            return None
        found.append((int(xx), int(yy)))
    return found


def encode(original: bytes, big: Optional[bytes], palette: np.ndarray, quant: Quantiser) -> bytes:
    """The repainted picture, same frames and sizes; raises ValueError if its resource icons can't be found."""
    frames = slp.decode(original)
    out = []
    for f in frames:
        size = (f.pixels.shape[1], f.pixels.shape[0])
        if size == SCREENS[-1]:
            icons = ICON_BOXES
        else:
            icons = find_icons(f.pixels, slp.decode(big)[0].pixels) if big else None
            if icons is None:
                raise ValueError(f"the resource icons of this {size[0]}x{size[1]} panel were not found; "
                                 "it keeps its original look")
        out.append(slp.SlpFrame(repaint(f.pixels, palette, quant, icons), f.hotspot))
    return slp.encode(out, props=slp.frame_props(original))


# --------------------------------------------------------------------------- resource icons

ART = {
    "food": (["................",
              "................",
              "................",
              "................",
              "....kkkkkkkk....",
              "..kkbbbbbbbbkk..",
              ".kbbLbbLbbLbbbk.",
              ".kbLbbLbbLbbbbk.",
              "kbbbbbbbbbbbbbbk",
              "kddddddddddddddk",
              ".kddddddddddddk.",
              "..kkkkkkkkkkkk..",
              "................"],
             {"k": "#3a2410", "b": "#b8732f", "L": "#e8b060", "d": "#8a5220"}),
    "gold": (["................",
              "................",
              "................",
              ".....kkkkkkk....",
              "....kyyyyyyyk...",
              "...kyWWWWWWyyk..",
              "..kyyyyyyyyyyyk.",
              "..kooooooooooyk.",
              "..koooooooooook.",
              "...kkkkkkkkkkk..",
              "................"],
             {"k": "#5a3e08", "y": "#f2d33a", "W": "#fff6a0", "o": "#c89a18"}),
}


@lru_cache(maxsize=None)
def item(what: str) -> np.ndarray:
    """A resource icon, RGBA 0..1: drawn items for food and gold, little blocks for the rest."""
    if what in ART:
        rows, legend = ART[what]
        tex = Painter(f"icon_{what}").grid(rows, {".": None, **legend}, noise=0.04)
        return tex[..., :4]
    if what == "population":
        from .units import VILLAGER_SKIN, villager_head
        faces, extras = villager_head(Painter("icon_villager"), VILLAGER_SKIN)
        root = Part("head", boxes=[cuboid((-4, -4, 0), (8, 8, 10), faces)] +
                    [cuboid((b.lo[0], 4, b.lo[2] - 24), b.hi - b.lo, b.faces) for b in extras])
        scale = 1.1
    else:
        s = V.Structure(what, origin=(0.5, 0.5))
        s.set(0, 0, 0, "oak_log" if what == "wood" else "cobblestone")
        root, scale = s.part(V.all_blocks()), 0.62
    cam = fit_camera(root, V.BUILDING_HEADING, scale=scale, pad=1)
    frame = render(root, V.BUILDING_HEADING, camera=cam, shadow=False)
    rgba = frame.to_rgba().astype(np.float64) / 255
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
