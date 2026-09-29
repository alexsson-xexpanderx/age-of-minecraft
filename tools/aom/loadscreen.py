"""The loading screen (interfac.drs 50163), as a Minecraft title screen.

A blue sky with Minecraft's flat blocky clouds and square sun, a floating island of blocks (grass, a pond, oak
trees, flowers and a small house) rendered with the mod's own block renderer, the gold and grass block logo from
the main menu, with a dark shadow so it stands out from the sky. The bottom of the screen is light sky only: the
game writes its loading text there, in black.

Only this screen uses its palette (50563), and the original is mostly greys: the mod gives it a palette of its own,
made from the new picture (`palette`), keeping the twenty Windows colours at 0-9 and 246-255 where they are.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import slp
from . import voxel as V
from .palette import _lab

W, H = 800, 600
RESERVED = list(range(10)) + list(range(246, 256))  # the Windows colours: kept as they are
SKY_TOP, SKY_LOW = np.array([0x6f, 0x9b, 0xf7]) / 255, np.array([0xdc, 0xea, 0xff]) / 255
TEXT_BAND = 128  # the bottom of the screen is light sky only: the game writes its loading text there, in black
def island() -> V.Structure:
    """A floating island: grass on dirt, stone and ores under it, a pond, oak trees, flowers and a small house."""
    from .nature import flower_sprite, grass_sprite, tree
    s = V.Structure("island", origin=(9, 9))
    rng = np.random.default_rng(20)
    n = 18
    for x in range(n):
        for y in range(n):
            r = np.hypot(x - 8.5, y - 8.5)
            if r > 9.2:
                continue
            depth = int(max(1, (9.2 - r) * 0.9 + rng.integers(0, 2)))  # thicker in the middle
            for z in range(-depth, 0):
                block = "dirt" if z >= -2 else ("stone" if rng.random() > 0.12 else "coal_ore")
                s.set(x, y, z, block)
            s.set(x, y, 0, "grass_block")
    for x, y in ((11, 4), (12, 4), (13, 5), (12, 5), (11, 5), (12, 6), (13, 6)):  # the pond
        s.set(x, y, 0, "water")
        s.set(x, y, -1, "sand")
    for x, y in ((10, 4), (14, 5), (13, 7), (11, 6), (10, 5)):
        s.set(x, y, 0, "sand")
    # the house, at the front on the right: cobblestone below, oak planks above, a gabled roof, a door and windows
    # facing the camera (the camera looks from +x, +y; nothing stands in front of it)
    x0, x1, y0, y1 = 4, 8, 10, 14
    s.fill(x0, y0, 1, x1, y1, 1, "cobblestone")
    s.ring(x0, y0, x1, y1, 2, 3, "oak_planks")
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        s.fill(x, y, 1, x, y, 3, "oak_log")
    V.door(s, 6, y1, 2, "+y")
    V.window(s, x1, 12, 3, "+x")
    V.window(s, 5, y1, 3, "+y")
    V.gable_roof(s, x0, x1, y0, y1, 4, "spruce_planks", "oak_planks", axis="x")
    for (tx, ty), seed in (((4, 3), 1), ((9, 2), 2), ((2, 11), 3)):  # at the back: the pond and house show
        s.merge(tree("oak", 150.0, seed), tx - 1, ty - 1, 1)
    names = ("poppy", "dandelion", "cornflower", "allium", "oxeye", "tulip", None, None)
    for name, (fx, fy) in zip(names, ((10.4, 12.6), (9.3, 8.2), (13.6, 14.4), (7.2, 6.5), (14.5, 8.4), (2.4, 7.6),
                                      (11.8, 10.8), (6.6, 8.2))):
        s.plant(fx, fy, 1, flower_sprite(name) if name else grass_sprite(), 12)
    return s


def _over(img: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    h, w = rgba.shape[:2]
    region = img[y:y + h, x:x + w]
    a = rgba[:region.shape[0], :region.shape[1], 3:4]
    region[...] = rgba[:region.shape[0], :region.shape[1], :3] * a + region * (1 - a)


@lru_cache(maxsize=None)
def picture() -> np.ndarray:
    """The loading screen, RGB 0..1, 800x600."""
    from .menu import logo
    from .render import fit_camera, render
    yy = np.linspace(0, 1, H)[:, None, None]
    img = np.broadcast_to(SKY_TOP * (1 - yy) + SKY_LOW * yy, (H, W, 3)).copy()
    img[46:94, 640:688] = (1.0, 0.98, 0.8)  # the square sun
    img[52:88, 646:682] = (1.0, 1.0, 0.92)
    rng = np.random.default_rng(7)
    for _ in range(9):  # flat, blocky clouds
        cx, cy = int(rng.integers(0, W)), int(rng.integers(240, 330))  # partly behind the island, above the text
        for _ in range(4):
            bw, bh = int(rng.integers(3, 8)) * 16, int(rng.integers(1, 3)) * 12
            x, y = cx + int(rng.integers(-3, 4)) * 16, cy + int(rng.integers(-1, 2)) * 12
            img[max(0, y):y + bh, max(0, x):x + bw] = img[max(0, y):y + bh, max(0, x):x + bw] * 0.2 + 0.8
    root, heading = island().part(V.all_blocks()), V.BUILDING_HEADING
    cam = fit_camera(root, heading, scale=1.0, pad=0)
    cam = fit_camera(root, heading, scale=min(480 / cam.width, 270 / cam.height), pad=2)
    rgba = render(root, heading, camera=cam, shadow=False).to_rgba(1).astype(np.float64) / 255
    _over(img, rgba, (W - rgba.shape[1]) // 2, H - TEXT_BAND - rgba.shape[0])
    mark = logo(560)
    shadow = mark.copy()
    shadow[..., :3] = 0.05
    shadow[..., 3] *= 0.6
    lx, ly = (W - mark.shape[1]) // 2, 30
    _over(img, shadow, lx + 5, ly + 6)
    _over(img, mark, lx, ly)
    return np.clip(img, 0, 1)


def palette(original: np.ndarray, rgb: np.ndarray = None) -> np.ndarray:
    """A palette for the picture: its 236 most telling colours (median cut) at 10-245, the Windows colours kept."""
    rgb = picture() if rgb is None else rgb
    flat = np.clip(rgb.reshape(-1, 3) * 255 + 0.5, 0, 255).astype(np.int64)
    colours, counts = np.unique(flat, axis=0, return_counts=True)
    boxes = [(colours, counts)]
    free = 256 - len(RESERVED)
    while len(boxes) < free:
        k = max(range(len(boxes)), key=lambda i: (np.ptp(boxes[i][0], axis=0).max() * np.sqrt(boxes[i][1].sum())
                                                   if len(boxes[i][0]) > 1 else -1))
        cols, cnt = boxes.pop(k)
        if len(cols) < 2:
            boxes.append((cols, cnt))
            break
        axis = int(np.argmax(np.ptp(cols, axis=0)))
        order = np.argsort(cols[:, axis], kind="stable")
        cols, cnt = cols[order], cnt[order]
        half = int(np.searchsorted(np.cumsum(cnt), cnt.sum() / 2)) + 1
        half = min(max(half, 1), len(cols) - 1)
        boxes += [(cols[:half], cnt[:half]), (cols[half:], cnt[half:])]
    out = np.asarray(original, np.int64)[:256].copy()
    free_idx = [i for i in range(256) if i not in RESERVED]
    for i, (cols, cnt) in zip(free_idx, boxes):
        out[i] = np.round((cols * cnt[:, None]).sum(0) / cnt.sum())
    for i in free_idx[len(boxes):]:
        out[i] = out[free_idx[0]]
    return out


def jasc(pal: np.ndarray) -> bytes:
    """A palette as the game stores it: JASC-PAL text."""
    lines = ["JASC-PAL", "0100", str(len(pal))] + [f"{r} {g} {b}" for r, g, b in np.asarray(pal, int)]
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def encode(original: bytes, original_palette: np.ndarray) -> tuple[bytes, np.ndarray]:
    """The new loading screen SLP (same frame and hotspot) and its palette."""
    frame = slp.decode(original)[0]
    rgb = picture()
    pal = palette(original_palette, rgb)
    free = np.array([i for i in range(256) if i not in RESERVED])
    flat = np.clip(rgb.reshape(-1, 3) * 255 + 0.5, 0, 255).astype(np.int64)
    keys = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    uniq, inverse = np.unique(keys, return_inverse=True)
    cols = _lab(np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64))
    lab = _lab(pal[free].astype(np.float64))
    best = free[((cols[:, None] - lab[None]) ** 2).sum(-1).argmin(1)]
    px = best[inverse].reshape(H, W).astype(np.int16)
    return slp.encode([slp.SlpFrame(px, frame.hotspot)], props=slp.frame_props(original)), pal
