"""The AoE2 256-colour palette and conversion of rendered frames to palette indices.

The palette is read from the player's own game (interfac.drs, file 50500,
a JASC-PAL text file), so colours match their install exactly.
"""
from __future__ import annotations

import numpy as np

from .render import OUTLINE, PLAYER, SHADOW, SOLID, TRANSPARENT, Frame
from . import slp

# Team-colour ranges: 8 shades starting at 16, 32, ... 128. Plain pixels never
# use them, or they would look like a fixed team's colour.
PLAYER_RANGES = [range(16 * k, 16 * k + 8) for k in range(1, 9)]
OUTLINE_RGB = (22, 18, 14)


def parse_jasc(data: bytes) -> np.ndarray:
    lines = data.decode("latin-1").split()
    if lines[0] != "JASC-PAL":
        raise ValueError("not a JASC-PAL palette")
    count = int(lines[2])
    values = np.array([int(v) for v in lines[3:3 + 3 * count]], np.float64)
    return values.reshape(count, 3)


def _lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0..255) to CIE L*a*b*, for perceptual nearest-colour matching."""
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


class Quantiser:
    def __init__(self, palette: np.ndarray, extra: tuple[int, ...] = ()):
        """`extra`: player-colour indices allowed as plain colours too (in an SLP a plain pixel there keeps its colour
        whoever owns the sprite)."""
        self.palette = palette
        banned = {i for r in PLAYER_RANGES for i in r} - set(extra)
        self.allowed = np.array([i for i in range(len(palette)) if i not in banned])
        self.lab = _lab(palette[self.allowed])
        self.cache: dict[int, int] = {}

    def indices(self, rgb: np.ndarray) -> np.ndarray:
        """Nearest allowed palette index for each 0..255 RGB row."""
        keys = (rgb[:, 0].astype(np.int64) << 16) | (rgb[:, 1].astype(np.int64) << 8) | rgb[:, 2].astype(np.int64)
        uniq, inverse = np.unique(keys, return_inverse=True)
        todo = [k for k in uniq if int(k) not in self.cache]
        if todo:
            todo = np.array(todo)
            cols = np.stack([(todo >> 16) & 255, (todo >> 8) & 255, todo & 255], -1).astype(np.float64)
            d = ((_lab(cols)[:, None, :] - self.lab[None, :, :]) ** 2).sum(-1)
            for k, best in zip(todo, self.allowed[d.argmin(1)]):
                self.cache[int(k)] = int(best)
        lut = np.array([self.cache[int(k)] for k in uniq])
        return lut[inverse]

    def frame_codes(self, frame: Frame, obstruction: bool = True) -> np.ndarray:
        """Rendered frame -> SLP pixel codes (see slp.py)."""
        kind = frame.kind
        codes = np.full(kind.shape, slp.TRANSPARENT, np.int16)
        solid = kind == SOLID
        if solid.any():
            rgb = np.clip(frame.rgb[solid] * 255 + 0.5, 0, 255).astype(np.int64)
            codes[solid] = self.indices(rgb)
        pc = kind == PLAYER
        codes[pc] = slp.PLAYER + np.clip(np.round(frame.light[pc] * 7), 0, 7).astype(np.int16)
        outline = kind == OUTLINE
        if outline.any():
            codes[outline] = self.indices(np.array([OUTLINE_RGB]))[0]
        codes[kind == SHADOW] = slp.SHADOW
        if obstruction:  # team-colour silhouette ring, shown only when the unit is behind something
            body = (kind != TRANSPARENT) & (kind != SHADOW)
            ring = np.zeros_like(body)
            ring[1:, :] |= body[:-1, :]
            ring[:-1, :] |= body[1:, :]
            ring[:, 1:] |= body[:, :-1]
            ring[:, :-1] |= body[:, 1:]
            codes[ring & (kind == TRANSPARENT)] = slp.OBSTRUCTION  # never over the ground shadow
        return codes

    def to_rgb(self, codes: np.ndarray, player: int = 1, background=(96, 140, 60)) -> np.ndarray:
        """Preview of SLP pixel codes as the game would draw them."""
        out = np.empty((*codes.shape, 3), np.float64)
        out[:] = background
        normal = (codes >= 0) & (codes < slp.PLAYER)
        out[normal] = self.palette[codes[normal]]
        pc = codes >= slp.PLAYER
        out[pc] = self.palette[16 * player + (codes[pc] - slp.PLAYER)]
        sh = codes == slp.SHADOW
        out[sh] = out[sh] * 0.55
        return out.astype(np.uint8)
