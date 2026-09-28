"""Tiny pixel-art texture toolkit for box models.

A texture is a float32 array of shape (h, w, 5) holding r, g, b, alpha and a
player-colour flag. Pixels flagged as player colour are drawn in the owning
player's colour; their r/g/b channels hold a lightness (0 dark .. 1 light)
instead of a colour.
"""
from __future__ import annotations

import zlib
from typing import Callable, Union

import numpy as np


class PC:
    """Player colour at the given lightness (0 = darkest, 1 = lightest)."""

    __slots__ = ("lightness",)

    def __init__(self, lightness: float = 0.6):
        self.lightness = lightness


Spec = Union[str, PC, None]  # "#rrggbb", player colour, or transparent
Paint = Union[Spec, np.ndarray, Callable[[int, int], np.ndarray]]

FACES = ("front", "back", "right", "left", "top", "bottom")


def parse(spec: Spec) -> np.ndarray:
    if spec is None:
        return np.zeros(5, np.float32)
    if isinstance(spec, PC):
        l = spec.lightness
        return np.array([l, l, l, 1, 1], np.float32)
    s = spec.lstrip("#")
    r, g, b = (int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return np.array([r, g, b, 1, 0], np.float32)


def over(base: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Composite `top` onto `base` wherever `top` is opaque (same size)."""
    return np.where(top[..., 3:4] > 0, top, base)


class Painter:
    """Deterministic texture factory: the same seed always paints the same pixels."""

    def __init__(self, seed: Union[str, int]):
        self.rng = np.random.default_rng(zlib.crc32(str(seed).encode()))

    def jitter(self, tex: np.ndarray, amount: float) -> np.ndarray:
        """Minecraft-style per-pixel brightness noise."""
        if amount:
            steps = self.rng.choice([-1.0, 0.0, 0.0, 1.0], size=tex.shape[:2]) * amount
            tex[..., :3] = np.clip(tex[..., :3] * (1 + steps[..., None]), 0, 1)
        return tex

    def fill(self, w: int, h: int, spec: Spec, noise: float = 0.07) -> np.ndarray:
        return self.jitter(np.tile(parse(spec), (h, w, 1)), noise)

    def grid(self, rows: list[str], legend: dict[str, Spec], noise: float = 0.05) -> np.ndarray:
        """Paint from ASCII art; each character is looked up in `legend`."""
        w = len(rows[0])
        assert all(len(r) == w for r in rows), rows
        tex = np.array([[parse(legend[ch]) for ch in row] for row in rows], np.float32)
        return self.jitter(tex, noise)

    def bands(self, *bands: tuple[int, Paint], noise: float = 0.07) -> Callable[[int, int], np.ndarray]:
        """Horizontal bands from the top: [(rows, paint), ...]; the last band takes the rest."""

        def paint(w: int, h: int) -> np.ndarray:
            out, y = [], 0
            for i, (n, p) in enumerate(bands):
                n = h - y if i == len(bands) - 1 else min(n, h - y)
                if n > 0:
                    out.append(self.resolve(p, w, n, noise))
                    y += n
            return np.concatenate(out, axis=0)

        return paint

    def speckle(self, base: Spec, *others: tuple[Spec, float], noise: float = 0.05):
        """Base colour sprinkled with other colours at the given probabilities."""

        def paint(w: int, h: int) -> np.ndarray:
            tex = self.fill(w, h, base, noise)
            for spec, p in others:
                mask = self.rng.random((h, w)) < p
                tex[mask] = parse(spec)
            return tex

        return paint

    def resolve(self, paint: Paint, w: int, h: int, noise: float = 0.07) -> np.ndarray:
        if callable(paint):
            return paint(w, h)
        if isinstance(paint, np.ndarray):
            return paint.copy()
        return self.fill(w, h, paint, noise)

    def skin(self, size: tuple[float, float, float], sides: Paint, top: Paint = "same",
             bottom: Paint = "same", *, noise: float = 0.07, mirror: bool = True,
             **faces: Paint) -> dict[str, np.ndarray]:
        """Face textures for a w x d x h box.

        `sides` paints every side face not given explicitly; `top`/`bottom`
        default to the same paint. With `mirror`, an explicit `right` face is
        mirrored onto `left` so asymmetric side art (e.g. hair) lines up.
        """
        w, d, h = (max(1, int(round(v))) for v in size)
        dims = {"front": (w, h), "back": (w, h), "right": (d, h), "left": (d, h),
                "top": (w, d), "bottom": (w, d)}
        paints = {"front": sides, "back": sides, "right": sides, "left": sides,
                  "top": sides if _same(top) else top,
                  "bottom": sides if _same(bottom) else bottom}
        paints.update(faces)
        out = {f: self.resolve(paints[f], *dims[f], noise=noise) for f in FACES}
        if mirror and "right" in faces and "left" not in faces:
            out["left"] = out["right"][:, ::-1].copy()
        return out


def _same(paint) -> bool:
    return isinstance(paint, str) and paint == "same"


def layered(base: dict[str, np.ndarray], *layers: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Stack overlay skins (e.g. armour) on top of a base skin, face by face."""
    out = dict(base)
    for layer in layers:
        for face, tex in layer.items():
            b = out[face]
            if tex.shape != b.shape:  # resample overlay to the base resolution
                ys = (np.arange(b.shape[0]) * tex.shape[0] // b.shape[0])
                xs = (np.arange(b.shape[1]) * tex.shape[1] // b.shape[1])
                tex = tex[ys][:, xs]
            out[face] = over(b, tex)
    return out
