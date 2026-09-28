"""Render buildings, walls, trees and other static sprites into SLP frames.

A static sprite is described by a `spec` dict: which model to build and how
the original SLP's frames are organised:

    mode "variants"  each frame is a different variant (trees in a forest, house styles)
    mode "anim"      frames are an animation (flags, torches), angles are variants
    mode "facing"    angles are directions the object faces (signposts, the relic)
    mode "match"     each frame is one of several pieces; pick the one whose outline
                     matches the original frame (wall pieces)
    mode "overlay"   an animated layer drawn over a static base (mill sails, forge smoke):
                     only the pixels that differ from the base are kept

Models are built with their footprint centre on the sprite's hotspot, from
the fixed building view (their +x and +y walls facing the camera).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import fortifications as FT
from . import gaia as GA
from . import nature as NA
from . import projectiles as PR
from . import slp
from . import structures as ST
from . import wonders as WO
from . import voxel as V
from .export import _crop, headings
from .geometry import Part
from .palette import Quantiser
from .render import Camera, Frame, fit_camera, render

HEADING = V.BUILDING_HEADING
BUILDINGS = {
    "ARRG": ST.archery_range, "BRKS": ST.barracks, "STBL": ST.stable, "MRKT": ST.market,
    "SIWS": ST.siege_workshop, "DOCK": ST.dock, "PORT": ST.dock, "TDWS": ST.market,
}
TREE_MIX = {  # forest type -> Minecraft trees mixed in it
    "oak": ("oak", "oak", "birch", "oak", "dark_oak"),
    "forest": ("oak", "dark_oak", "oak", "birch", "azalea"),
    "pine": ("spruce",), "snow": ("snowy_spruce",), "palm": ("palm",), "jungle": ("jungle", "jungle", "acacia"),
    "bamboo": ("bamboo",),
}

def _part(m) -> Part:
    return m.part(V.all_blocks()) if isinstance(m, V.Structure) else m


# --------------------------------------------------------------------------- the model registry

def build(spec: dict, variant: int = 0, count: int = 1, t: float = 0.0, fit: Optional[dict] = None,
          part: str = None) -> Part:
    """The model for one frame. `fit` holds the original frame's size (height/width in screen pixels)."""
    m = spec["model"]
    style, age = spec.get("style", "W"), spec.get("age", 2)
    fit = fit or {}
    part = part or spec.get("part", "all")
    if m == "building":
        code = spec["code"]
        if code == "HOUS":
            return _part(ST.house(style, age, variant))
        if code == "RTWC":
            return _part(ST.town_center(style, age))
        if code == "MILL":
            return _part(ST.mill(style, age, t, part))
        if code == "BLAC":
            return _part(ST.blacksmith(style, age, t, part))
        if code == "UNIV":
            return _part(ST.university(style, age, t, part))
        if code == "SMIL":
            return _part(ST.lumber_camp(style, age))
        if code == "MINE":
            return _part(ST.mining_camp(style, age))
        if code == "CRCH":
            return _part(ST.monastery(style, age))
        if code == "CSTL":
            return _part(FT.castle(style, age))
        if code == "WCTW":
            return _part(FT.watch_tower(style, spec["level"]))
        if code == "FARM":
            return _part(ST.farm(spec.get("stage", 1.0 - variant / max(1, count - 1))))
        return _part(BUILDINGS[code](style, age))
    if m == "outpost":
        return _part(FT.outpost())
    if m == "wonder":
        return _part(WO.wonder(spec["letter"]))
    if m == "monument":
        return _part(getattr(WO, spec["name"])())
    if m == "wall":
        piece = spec.get("piece") or FT.PIECES[variant % 5]
        return _part(FT.wall_piece(spec["kind"], style, piece, spec.get("damage", 0), spec.get("progress", 1.0)))
    if m == "gate":
        return FT.gate_section(style, age, spec["direction"], spec["open"], spec.get("half"))
    if m == "gate_tower":
        return _part(FT.gate_tower(style, age))
    if m == "gate_site":
        s = ST.construction(1.5, variant)
        return Part("gate_site", children=[FT.gate_section(style, age, spec["direction"], False, spec.get("half")),
                                           _part(s)]) if variant >= count - 1 else _part(s)
    if m == "fish_trap":
        return _part(ST.fish_trap(spec.get("stage", 1.0 - variant / max(1, count - 1))))
    if m == "construction":
        tiles = spec.get("tiles") or max(1.0, fit.get("width", 96) / 96.0)
        return _part(ST.construction(tiles, variant))
    if m == "rubble":
        tiles = spec.get("tiles") or max(1.0, fit.get("width", 96) / 96.0)
        return _part(ST.rubble(tiles, variant))
    if m == "tree":
        mix = TREE_MIX.get(spec.get("forest", ""), (spec.get("kind", "oak"),))
        kind = mix[(variant * 7 + 3) % len(mix)] if len(mix) > 1 else mix[0]
        return _part(NA.tree(kind, fit.get("height", spec.get("height", 110)), variant, part))
    if m == "stump":
        return _part(NA.stump(spec.get("kind", "oak"), variant, spec.get("felled", True)))
    if m == "ore":
        return _part(NA.ore_pile(spec["kind"], fit.get("width", 90), variant))
    if m == "berry_bush":
        return _part(NA.berry_bush(variant))
    if m == "rock":
        return _part(NA.boulder(variant, fit.get("width", 60)))
    if m == "plants":
        return _part(NA.plants(variant, spec.get("flowers", False)))
    if m == "cactus":
        return _part(NA.cactus(variant))
    if m == "haystack":
        return _part(NA.haystack(variant))
    if m == "projectile":
        return PR.projectile(spec["kind"], t, spin=spec.get("pitched", False) or spec["kind"] in ("axe", "sword"))
    if m == "gaia":
        fn = getattr(GA, spec["name"])
        kwargs = {k: v for k, v in spec.items() if k in ("variant",)}
        if spec["name"] in ("yurt", "pavilion", "ruins", "stone_head", "graves", "heads", "rug", "crater",
                            "sea_rock"):
            return _part(fn(spec.get("variant", variant)))
        if spec["name"] in ("banner_flag",):
            return _part(fn(spec.get("variant", 0), t))
        if spec["name"] in ("standing_torch",):
            return _part(fn(t))
        if spec["name"] in ("relic",):
            return _part(fn(t))
        return _part(fn(**kwargs))
    raise KeyError(m)


def candidates(spec: dict, t: float = 0.0) -> list[Part]:
    """Pieces to choose from in `match` mode."""
    return [build({**spec, "piece": piece, "progress": spec.get("progress", 1.0) if "stages" not in spec
                   else max(0.25, t)}) for piece in FT.PIECES]


# --------------------------------------------------------------------------- rendering

SHADOWS = {"on": True}


def _render(root: Part, heading: float, pad: int = 6) -> tuple[Frame, Camera]:
    cam = fit_camera(root, heading, pad=pad)
    return render(root, heading, camera=cam, shadow=SHADOWS["on"]), cam


def _codes(frame: Frame, quant: Quantiser) -> np.ndarray:
    return quant.frame_codes(frame, obstruction=False)


def solid_mask(frame: slp.SlpFrame) -> tuple[np.ndarray, tuple[int, int]]:
    return frame.pixels >= 0, frame.hotspot


def frame_fit(frame: slp.SlpFrame) -> dict:
    """Size of the original frame's drawing, relative to its hotspot."""
    m, (hx, hy) = solid_mask(frame)
    ys, xs = np.nonzero(m)
    if not len(ys):
        return {}
    return {"height": float(hy - ys.min()), "width": float(xs.max() - xs.min() + 1),
            "left": float(hx - xs.min()), "right": float(xs.max() - hx)}


def _iou(a: np.ndarray, ah: tuple, b: np.ndarray, bh: tuple) -> float:
    """Overlap of two masks aligned on their hotspots."""
    x0 = min(-ah[0], -bh[0])
    y0 = min(-ah[1], -bh[1])
    x1 = max(a.shape[1] - ah[0], b.shape[1] - bh[0])
    y1 = max(a.shape[0] - ah[1], b.shape[0] - bh[1])
    A = np.zeros((y1 - y0, x1 - x0), bool)
    Bm = np.zeros_like(A)
    A[-ah[1] - y0:-ah[1] - y0 + a.shape[0], -ah[0] - x0:-ah[0] - x0 + a.shape[1]] = a
    Bm[-bh[1] - y0:-bh[1] - y0 + b.shape[0], -bh[0] - x0:-bh[0] - x0 + b.shape[1]] = b
    union = (A | Bm).sum()
    return float((A & Bm).sum() / union) if union else 0.0


def _shifted(frame: slp.SlpFrame, shift) -> slp.SlpFrame:
    if not shift:
        return frame
    return slp.SlpFrame(frame.pixels, (frame.hotspot[0] - int(round(shift[0])), frame.hotspot[1] - int(round(shift[1]))))


def _match_pieces(spec, orig, used, F, stored, quant, cache) -> list[slp.SlpFrame]:
    """For every frame, the wall piece whose outline best matches the original frame.

    Frames that form one complete set of pieces (5 angles, one per piece) are
    matched one-to-one, so every piece is used exactly once per set.
    """
    from itertools import permutations

    def rendered_at(t):
        key = round(t, 3)
        if key not in cache:
            outs = []
            for c in candidates(spec, t):
                f, cam = _render(c, HEADING)
                outs.append(_crop(_codes(f, quant), cam.origin))
            cache[key] = outs
        return cache[key]

    picks: list = [None] * used
    groups: dict[float, list[int]] = {}
    for k in range(used):
        a, fi = divmod(k, F)
        t = fi / max(1, F - 1) if F > 1 and k < F * stored else 1.0
        groups.setdefault(round(t, 3), []).append(k)
    for t, ks in groups.items():
        pieces = rendered_at(t)
        if orig is None:
            for i, k in enumerate(ks):
                picks[k] = pieces[i % len(pieces)]
            continue
        scores = np.zeros((len(ks), len(pieces)))
        for i, k in enumerate(ks):
            if k < len(orig):
                om, oh = solid_mask(orig[k])
                scores[i] = [_iou(om, oh, r.pixels >= 0, r.hotspot) for r in pieces]
        if len(ks) == len(pieces):
            best = max(permutations(range(len(pieces))), key=lambda perm: sum(scores[i, j] for i, j in enumerate(perm)))
            for i, k in enumerate(ks):
                picks[k] = pieces[best[i]]
        else:
            for i, k in enumerate(ks):
                picks[k] = pieces[int(np.argmax(scores[i]))]
    return picks


def render_static(spec: dict, num_frames: int, frames_per_angle: int, angle_count: int, mirroring: bool,
                  quant: Quantiser, original: Optional[bytes] = None) -> list[slp.SlpFrame]:
    """All frames of a static sprite, in the original's layout (padded to `num_frames`)."""
    mode = spec.get("mode", "variants")
    F = max(1, frames_per_angle)
    hs = headings(angle_count, mirroring)
    stored = len(hs)
    used = num_frames if mode in ("variants", "match", "static") else min(num_frames, F * stored)
    orig = slp.decode(original) if original and (spec.get("fit") or mode == "match") else None
    shift = spec.get("shift")
    SHADOWS["on"] = spec.get("shadow", True)  # projectiles fly: the game draws their shadows separately
    out: list[slp.SlpFrame] = []
    cache: dict = {}

    def emit(root: Part, heading: float = HEADING):
        f, cam = _render(root, heading)
        out.append(_shifted(_crop(_codes(f, quant), cam.origin), shift))

    if mode == "overlay":
        base = build(spec, part="body")
        for k in range(used):
            a, fi = divmod(k, F)
            full = build(spec, variant=a, count=stored, t=fi / F, part="all")
            cam = fit_camera(full, HEADING, pad=6)
            fb, ff = render(base, HEADING, camera=cam), render(full, HEADING, camera=cam)
            codes_f, codes_b = _codes(ff, quant), _codes(fb, quant)
            layer = np.where(codes_f != codes_b, codes_f, slp.TRANSPARENT).astype(np.int16)
            out.append(_shifted(_crop(layer, cam.origin), shift))
    elif mode == "match":
        picks = _match_pieces(spec, orig, used, F, stored, quant, cache)
        for k in range(used):
            out.append(_shifted(picks[k], shift))
    else:
        for k in range(used):
            a, fi = divmod(k, F)
            fit = frame_fit(orig[k]) if orig is not None and k < len(orig) else None
            if mode == "variants":
                root = build(spec, variant=k, count=used, t=0.0, fit=fit)
                emit(root)
            elif mode == "anim":
                root = build(spec, variant=a, count=stored, t=fi / F, fit=fit)
                emit(root)
            elif mode == "facing":
                root = build(spec, variant=0, count=1, t=fi / (F - 1) if F > 1 else 0.5, fit=fit)
                emit(Part("turn", children=[root]), heading=hs[a])
            else:  # static: the same picture in every frame
                if "static" not in cache:
                    f, cam = _render(build(spec, fit=fit), HEADING)
                    cache["static"] = _shifted(_crop(_codes(f, quant), cam.origin), shift)
                out.append(cache["static"])
    while len(out) < num_frames:
        out.append(out[-1] if out else slp.SlpFrame(np.full((1, 1), slp.TRANSPARENT, np.int16), (0, 0)))
    return out[:num_frames]
