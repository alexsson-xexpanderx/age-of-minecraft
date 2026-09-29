"""The in-game panels: the resource bar at the top and the command, info and minimap panel at the bottom.

The Conquerors draws them from one full-screen picture per civilisation and screen size in interfac.drs, with
the game view left transparent: 51101-51120 for 800x600, 51121-51140 for 1024x768 and 51141-51160 for
1280x1024 (UserPatch's data mod format calls this uiBaseId 51100, uiStride 20). UserPatch builds its
widescreen panels from the same pictures.

Each picture is repainted in the Minecraft style, every pixel keeping its place:

* the resource bar gets one fixed layout: each resource's item in a 16x16 square, then 2 pixels on, the box the
  game writes the amount in, flat and nearly black (the player asked for no shading, and darker, so the white
  stands out), a five-digit amount in its middle; planks all around;
* the parchment the game writes on (large light areas, with their shaded border) becomes the grey of Minecraft's
  inventory, with a straight top edge, its black edge, white bevel at the top left and dark bevel at the bottom
  right;
* large dark areas become inventory slots, sunk in;
* everything else, the carved frames, becomes planks, as dark or light as the original frame was, so the
  game's white and black text stays readable on it;
* where the panels meet the game view they get a black edge, like every Minecraft window;
* the five resource icons in the top bar (wood, food, gold, stone, population) become an oak log, a leg of meat, a
  gold ingot, cobblestone and a villager's face.

Every panel picture, at every size, has its five icons every 77 pixels from x 8, each followed by a dark box
that ends 69 pixels after the icon's left edge; only the rows differ (4-21 at 800x600 and 1024x768, 10-27 at
1280x1024). The build finds those dark boxes (`places`) and lays the bar out on them; a picture whose boxes are
not there is left as it was, so no resource ever loses its icon. The game starts a five-digit amount about 23
pixels after the icon and ends it about 65 after (measured on photos of the game): the box, 20 to 68, has it in
its middle.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable, Optional

import numpy as np

from . import slp
from . import voxel as V
from .palette import Quantiser
from .render import fit_camera, render
from .textures import Painter, parse

BASE, STRIDE = 51100, 20
SCREENS = ((800, 600), (1024, 768), (1280, 1024))
FIRST, STEP = 8, 77  # the resource bar: an icon every 77 pixels from x 8, at every screen size
CELL = 16  # each resource's item is drawn in a 16x16 square, 2 pixels from the icon's left edge
BOX = (20, 68)  # the box the game writes the amount in, from the icon's left edge
RESOURCES = ("wood", "food", "gold", "stone", "population")
GUI = {"panel": "#c6c6c6", "light": "#ffffff", "shade": "#555555", "edge": "#000000",
       "slot": "#8b8b8b", "slot_light": "#ffffff", "slot_shade": "#373737",
       "count": "#1e1e1e"}  # where the bar's numbers are: flat
PLANKS = ("birch_planks", "oak_planks", "jungle_planks", "acacia_planks", "spruce_planks", "dark_oak_planks")
LUMA = np.array([0.299, 0.587, 0.114])
PIXEL = 2  # screen pixels per Minecraft pixel, like Minecraft's GUI scale 2


def panels(get: Callable[[int], Optional[bytes]]) -> list[tuple[int, tuple[int, int], bytes]]:
    """(SLP id, screen size, picture) of every panel picture."""
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
    return [(sid, size, data) for sid, (size, data) in sorted(found.items())]


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


def _longest_run(rows: np.ndarray) -> tuple[int, int]:
    """The longest stretch of True in a column of flags: (first, last + 1), or (0, 0)."""
    best, start = (0, 0), None
    for i, on in enumerate(list(rows) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return best


def places(lum: np.ndarray, opaque: np.ndarray, bar: np.ndarray) -> Optional[tuple[list[int], int, int]]:
    """The five icons' left edges and the rows of the game's dark boxes after them (where it writes the amounts),
    or None if this picture's bar is not laid out like every known one."""
    dark = opaque & bar & (lum < 0.14)
    xs = [FIRST + STEP * k for k in range(5)]
    if xs[-1] + 66 > dark.shape[1]:
        return None
    runs = [_longest_run(dark[:, x + 30:x + 66].mean(1) > 0.8) for x in xs]
    top, bottom = (int(np.median([r[i] for r in runs])) for i in (0, 1))
    if bottom - top < 12 or any(abs(a - top) > 2 or abs(b - bottom) > 2 for a, b in runs):
        return None
    return xs, top, bottom


def _top_bar(opaque: np.ndarray) -> np.ndarray:
    """The resource bar: the rows at the top that are drawn (nearly) all the way across, down to the first that
    is not (a few rows at the very top may have clear bits)."""
    full = opaque.mean(1) > 0.9
    out = np.zeros_like(opaque)
    if not full[:16].any():
        return out
    first = int(np.argmax(full))
    rest = full[first:]
    out[:first + (len(rest) if rest.all() else int(np.argmin(rest)))] = True
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


def restyle(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """A panel picture (RGB 0..1) in the Minecraft style; raises ValueError if its resource bar is not laid out
    like every known one (it then keeps its look)."""
    lum = rgb @ LUMA
    bar = _top_bar(opaque)
    found = places(lum, opaque, bar)
    if found is None:
        raise ValueError(f"the resource bar of this {rgb.shape[1]}x{rgb.shape[0]} panel is not the one this build "
                         "knows; it keeps its original look")
    xs, top, bottom = found
    paper = _paper(lum, opaque) & ~bar  # the parchment below the resource bar (its tears are filled)
    counts = np.zeros_like(opaque)
    for x in xs:  # the game writes the amounts there
        counts[top:bottom, x + BOX[0]:x + BOX[1]] = True
    counts &= opaque
    slots = _shrink(_grow(_grow(_shrink(opaque & (lum < 0.14), 3), 3), 2), 2) & opaque & ~paper & ~bar
    frame = opaque & ~paper & ~slots & ~counts
    out = np.zeros_like(rgb)
    if frame.any():
        out[frame] = _tile(_planks(float(lum[frame].mean())), opaque.shape)[frame]
    _bevel(out, slots, GUI["slot"], GUI["slot_shade"], GUI["slot_light"], None)
    _bevel(out, paper, GUI["panel"], GUI["light"], GUI["shade"], GUI["edge"])
    out[counts] = parse(GUI["count"])[:3]  # flat, no shading
    out[opaque & ~_shrink(opaque, PIXEL)] = parse(GUI["edge"])[:3]  # a black edge along the game view
    for x, what in zip(xs, RESOURCES):  # each in the same square: all in line, all as far from their box
        icon = item(what)
        ih, iw = icon.shape[:2]
        x0 = x + BOX[0] - 2 - CELL + (CELL - iw) // 2
        y0 = top + (bottom - top - CELL) // 2 + (CELL - ih) // 2
        region = out[y0:y0 + ih, x0:x0 + iw]
        solid = (icon[..., 3] > 0) & opaque[y0:y0 + ih, x0:x0 + iw]
        region[solid] = icon[..., :3][solid]
    return out


def repaint(codes: np.ndarray, palette: np.ndarray, quant: Quantiser) -> np.ndarray:
    """`restyle` for SLP pixel codes: in and out in the game's palette."""
    opaque = (codes >= 0) & (codes < 256)
    out = restyle(palette[np.clip(codes, 0, 255)].astype(np.float64) / 255, opaque)
    new = codes.copy()
    new[opaque] = quant.indices(np.clip(out[opaque] * 255 + 0.5, 0, 255).astype(np.int64))
    return new


def encode(original: bytes, palette: np.ndarray, quant: Quantiser) -> bytes:
    """The repainted picture, same frames and sizes; raises ValueError if its resource bar is not the known one."""
    frames = slp.decode(original)
    out = [slp.SlpFrame(repaint(f.pixels, palette, quant), f.hotspot) for f in frames]
    return slp.encode(out, props=slp.frame_props(original))


# --------------------------------------------------------------------------- resource icons

ART = {
    "food": (["......kkkkkk....",  # a leg of meat on the bone, the way games draw meat
              "....kkrRRrrrkk..",
              "...krRRrrrrrrrk.",
              "..krRrrrrrrrrrdk",
              "..krrrrrrrrrrrdk",
              "..krrrrrrrrrrddk",
              "..krrrrrrrrrdddk",
              "...krrrrrrrdddk.",
              "...kkrrrrddddk..",
              "..kwwkkdddkkk...",
              ".kwwwk.kkk......",
              "kwwwk...........",
              "kwkwwk..........",
              ".k.kk..........."],
             {"k": "#2e0a08", "r": "#b8402c", "R": "#e07a5c", "d": "#7e2a1c", "w": "#f2eee0"}),
    "population": (None, {"k": "#24160c", "s": "#b8866c", "b": "#4a2c22", "w": "#f0f0f0", "g": "#2f8a3a",
                          "n": "#9a6c56", "m": "#7a5040"}),
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


VILLAGER = ["sssssss", "sbbbbbs", "swgsgws", "sssnsss", "sssnsss", "ssmnmss", "sssssss"]  # 16x16 doubled, edged


def _doubled(rows: list[str]) -> list[str]:
    """A grid at twice the size: each pixel two by two."""
    return ["".join(c * 2 for c in row) for row in rows for _ in range(2)]


def _outlined(rows: list[str]) -> list[str]:
    """A grid with a one-pixel dark ("k") edge around it, so it stands out on the planks."""
    w = len(rows[0]) + 2
    return ["k" * w] + ["k" + row + "k" for row in rows] + ["k" * w]


@lru_cache(maxsize=None)
def item(what: str) -> np.ndarray:
    """A resource icon, RGBA 0..1: drawn items for food and gold, a villager's face for population, little blocks
    for the rest."""
    if what in ART:
        rows, legend = ART[what]
        if rows is None:  # population: a villager's face, like the one on the menu's Learn to Play banner
            rows = _outlined(_doubled(VILLAGER))
        tex = Painter(f"icon_{what}").grid(rows, {".": None, **legend}, noise=0.04)
        return tex[..., :4]
    s = V.Structure(what, origin=(0.5, 0.5))
    s.set(0, 0, 0, "oak_log" if what == "wood" else "cobblestone")
    root, scale = s.part(V.all_blocks()), 0.58  # a block, no bigger than the 16x16 square
    cam = fit_camera(root, V.BUILDING_HEADING, scale=scale, pad=1)
    frame = render(root, V.BUILDING_HEADING, camera=cam, shadow=False)
    rgba = frame.to_rgba().astype(np.float64) / 255
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
