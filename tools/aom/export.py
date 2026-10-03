"""Render a unit animation into SLP frames laid out like the original sprite.

An AoE2 unit SLP holds, for each stored angle (clockwise from facing the
camera: S, SW, W, NW, N for the usual 8 mirrored angles), `frames_per_angle`
frames. We render exactly that layout so the game's .dat stays valid.
"""
from __future__ import annotations

import numpy as np

from . import slp
from .animation import pose
from .palette import Quantiser
from .render import OUTLINE, PLAYER, SHADOW, SOLID, TRANSPARENT, Camera, Frame, fit_camera, render
from .units import Unit

BASE_SCALE = 1.5
POSE_ACTION = {"idle": "idle", "walk": "walk", "run": "walk", "attack": "attack", "work": "attack",
               "carry": "carry", "die": "die", "decay": "die"}
ONCE = {"die", "decay"}


def headings(angle_count: int, mirroring: bool) -> list[float]:
    a = max(1, angle_count)
    stored = a // 2 + 1 if mirroring and a > 1 else a
    return [-90.0 - i * 360.0 / a for i in range(stored)]


def _time(action: str, i: int, n: int) -> float:
    return i / max(1, n - 1) if action in ONCE else i / max(1, n)


def _pose(unit: Unit, action: str, t: float):
    act = POSE_ACTION[action]
    if act == "carry" and not unit.carry:
        act = "walk"
    if action == "decay":
        t = 1.0
    elif action == "run":
        t = (t * 2) % 1.0  # same stride, twice as fast
    return pose(unit, act, t)


def _dissolve(frame: Frame, amount: float, seed: int) -> None:
    """Decay: the corpse crumbles into a puff of grey smoke, pixel by pixel."""
    if amount <= 0:
        return
    noise = np.random.default_rng(seed).random(frame.kind.shape)
    body = np.isin(frame.kind, (SOLID, PLAYER, OUTLINE))
    gone = noise < amount
    smoke = body & (noise >= amount) & (noise < amount + 0.12)
    frame.kind[body & gone] = TRANSPARENT
    frame.kind[(frame.kind == SHADOW) & gone] = TRANSPARENT
    frame.kind[smoke] = SOLID
    frame.rgb[smoke] = (0.78, 0.78, 0.76)


def camera_for(unit: Unit, action: str, hs: list[float], frames: int, pad: int = 4) -> Camera:
    """One canvas big enough for every frame of this animation."""
    left = right = up = down = 0
    samples = sorted({0, frames // 4, frames // 2, (3 * frames) // 4, max(0, frames - 1)})
    for h in hs:
        for i in samples:
            cam = fit_camera(unit.root, h, _pose(unit, action, _time(action, i, frames)),
                             scale=BASE_SCALE * unit.scale, pad=pad)
            left, up = max(left, cam.origin[0]), max(up, cam.origin[1])
            right, down = max(right, cam.width - cam.origin[0]), max(down, cam.height - cam.origin[1])
    left, right, up, down = (int(v) + 2 for v in (left, right, up, down))
    return Camera(width=left + right, height=up + down, origin=(left, up), scale=BASE_SCALE * unit.scale)


def _crop(codes: np.ndarray, origin: tuple[int, int]) -> slp.SlpFrame:
    ys, xs = np.nonzero(codes != slp.TRANSPARENT)
    if not len(ys):
        return slp.SlpFrame(np.full((1, 1), slp.TRANSPARENT, np.int16), (0, 0))
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    return slp.SlpFrame(codes[y0:y1 + 1, x0:x1 + 1].copy(), (int(origin[0]) - x0, int(origin[1]) - y0))


def render_frames(unit: Unit, action: str, frames_per_angle: int, angle_count: int, mirroring: bool,
                  quant: Quantiser, shadow: bool = True) -> list[slp.SlpFrame]:
    frames_per_angle = max(1, frames_per_angle)
    hs = headings(angle_count, mirroring)
    cam = camera_for(unit, action, hs, frames_per_angle)
    out = []
    for a, h in enumerate(hs):
        for i in range(frames_per_angle):
            t = _time(action, i, frames_per_angle)
            frame = render(unit.root, h, _pose(unit, action, t), cam, shadow=shadow)
            if action == "decay":
                _dissolve(frame, max(0.0, (t - 0.45) / 0.55), seed=1000 + a)
            out.append(_crop(quant.frame_codes(frame), cam.origin))
    return out


def blank(num_frames: int) -> bytes:
    """An SLP with the same number of frames, all empty."""
    empty = slp.SlpFrame(np.full((1, 1), slp.TRANSPARENT, np.int16), (0, 0))
    return slp.encode([empty] * max(1, num_frames))
