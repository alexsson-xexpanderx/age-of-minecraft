"""The "AGE OF MINECRAFT" title, built from blocks like Minecraft's own logo and rendered in 3D.

Each letter is a pixel font glyph; every pixel becomes a block. "MINECRAFT" is made of grass blocks on stone
(grass on each letter's top row, cobblestone below), "AGE OF" of gold blocks. The camera looks at the letters
from the front and a little above, so their tops and depth show.
"""
from __future__ import annotations

import numpy as np

from .geometry import Part
from .render import Camera, Frame, render
from .voxel import Structure, all_blocks

GLYPHS = {  # a bold pixel font: strokes two blocks wide
    "A": [".#####.", "##...##", "##...##", "#######", "##...##", "##...##", "##...##"],
    "C": [".#####", "##....", "##....", "##....", "##....", "##....", ".#####"],
    "E": ["######", "##....", "##....", "#####.", "##....", "##....", "######"],
    "F": ["######", "##....", "##....", "#####.", "##....", "##....", "##...."],
    "G": [".######", "##.....", "##.....", "##..###", "##...##", "##...##", ".######"],
    "I": ["####", ".##.", ".##.", ".##.", ".##.", ".##.", "####"],
    "M": ["##....##", "###..###", "########", "##.##.##", "##....##", "##....##", "##....##"],
    "N": ["##...##", "###..##", "####.##", "##.####", "##..###", "##...##", "##...##"],
    "O": [".#####.", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."],
    "R": ["######.", "##...##", "##...##", "######.", "##.##..", "##..##.", "##...##"],
    "T": ["######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##.."],
    " ": ["...", "...", "...", "...", "...", "...", "..."],
}


def word(s: Structure, text: str, x0: int, z0: int, face: str, top: str = None, depth: int = 2) -> int:
    """Lay `text` out along +x with its bottom row at height z0; returns the x after the last letter.

    `face` fills the letters, `top` (if given) replaces the block on top of each column."""
    x = x0
    for ch in text:
        glyph = GLYPHS[ch]
        h = len(glyph)
        for r, row in enumerate(glyph):
            for c, px in enumerate(row):
                if px != "#":
                    continue
                above = r > 0 and glyph[r - 1][c] == "#"
                block = top if (top and not above) else face
                for d in range(depth):
                    s.set(x + c, d, z0 + h - 1 - r, block)
        x += len(glyph[0]) + 1
    return x - 1


def line(text: str, face: str, top: str = None, depth: int = 3) -> Part:
    s = Structure("logo")
    w = word(s, text, 0, 0, face, top, depth)
    s.origin = (w / 2, depth / 2)
    return s.part(all_blocks())


def render_line(text: str, face: str, top: str = None, scale: float = 2.0, heading: float = 86.0,
                elevation: float = 24.0, depth: int = 3) -> Frame:
    """One line of the title facing the viewer (a heading of 90 turns the letters' fronts to the camera; a
    few degrees less shows their right sides too)."""
    from .geometry import Pose, place
    from .render import _corners, model_matrix
    root = line(text, face, top, depth)
    pts = np.concatenate([_corners(pb) for pb in place(root, Pose(), model_matrix(heading))])
    a = np.radians(elevation)
    x = pts[:, 0] * scale
    y = -(pts[:, 1] * np.sin(a) + pts[:, 2] * np.cos(a)) * scale
    pad = 4
    x0, x1, y0, y1 = int(x.min()) - pad, int(x.max()) + pad, int(y.min()) - pad, int(y.max()) + pad
    cam = Camera(width=x1 - x0, height=y1 - y0, origin=(-x0, -y0), scale=scale, elevation=elevation)
    return render(root, heading, camera=cam, shadow=False)


def title_image(width: int) -> np.ndarray:
    """The two-line title as an RGBA image (uint8) about `width` pixels wide, with a soft dark halo so it
    reads over any picture."""
    from PIL import Image, ImageFilter
    probe = sum(len(GLYPHS[c][0]) + 1 for c in "MINECRAFT") * 16  # model width in pixels
    s2 = width / probe
    big = render_line("MINECRAFT", "cobblestone", "grass_block", scale=s2).to_rgba(1)
    small = render_line("AGE OF", "gold_block", None, scale=s2 * 0.62, depth=2).to_rgba(1)
    gap = int(s2 * 6)
    W = max(big.shape[1], small.shape[1])
    H = small.shape[0] + gap + big.shape[0]
    out = np.zeros((H, W, 4), np.uint8)
    for img, y in ((small, 0), (big, small.shape[0] + gap)):
        x = (W - img.shape[1]) // 2
        region = out[y:y + img.shape[0], x:x + img.shape[1]]
        a = img[..., 3:4] / 255.0
        region[...] = (img * a + region * (1 - a)).astype(np.uint8)
    pad = int(s2 * 24)
    out = np.pad(out, ((pad, pad), (pad, pad), (0, 0)))
    alpha = Image.fromarray(out[..., 3]).filter(ImageFilter.GaussianBlur(s2 * 7))
    halo = (np.asarray(alpha, np.float32) / 255 * 0.55)[..., None]
    a = out[..., 3:4] / 255.0
    rgb = out[..., :3] * a  # over black
    alpha_out = a + halo * (1 - a)
    rgb = rgb / np.maximum(alpha_out, 1e-6)
    return np.concatenate([np.clip(rgb, 0, 255), alpha_out * 255], -1).astype(np.uint8)
