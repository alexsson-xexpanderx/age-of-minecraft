"""The Age of Minecraft icon: a villager king (a villager's head with a golden crown).

It is rendered with the mod's own block renderer at every size an icon needs. `ico()` makes the icon file the
shortcut uses. `into_exe()` puts it into a copy of the game exe (the mod's own age_of_minecraft.exe, never the
game's): each icon picture the exe has is redrawn in place at its own size and colour depth, so no other byte of
the exe moves. `png()` also serves the build's pictures of the original menus.
"""
from __future__ import annotations

import struct
import zlib
from functools import lru_cache

import numpy as np

from . import pe
from . import voxel as V
from .geometry import Part, cuboid
from .render import fit_camera, render
from .textures import FACES, Painter, parse

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def model() -> Part:
    from .units import VILLAGER_SKIN, villager_head
    faces, extras = villager_head(Painter("icon_king"), VILLAGER_SKIN)
    boxes = [cuboid((-4, -4, 0), (8, 8, 10), faces)]
    boxes += [cuboid((b.lo[0], 4, b.lo[2] - 24), b.hi - b.lo, b.faces) for b in extras]  # the nose
    gold = {f: np.tile(parse("#f2c43a"), (2, 2, 1)) for f in FACES}
    boxes.append(cuboid((-4.5, -4.5, 10), (9, 9, 1.5), gold))  # the crown's band and its eight points
    for x, y in ((-4.5, -4.5), (2.5, -4.5), (-4.5, 2.5), (2.5, 2.5), (-1, -4.5), (-4.5, -1), (2.5, -1), (-1, 2.5)):
        boxes.append(cuboid((x, y, 11.5), (2, 2, 2.5), gold))
    return Part("king", boxes=boxes)


@lru_cache(maxsize=None)
def image(size: int) -> np.ndarray:
    """The icon at size x size, RGBA uint8, centred on a transparent background."""
    root, heading = model(), V.BUILDING_HEADING
    cam = fit_camera(root, heading, scale=1.0, pad=0)
    cam = fit_camera(root, heading, scale=(size - 2) / max(cam.width, cam.height), pad=1)
    rgba = render(root, heading, camera=cam, shadow=False).to_rgba()[:size, :size]
    out = np.zeros((size, size, 4), np.uint8)
    y0, x0 = (size - rgba.shape[0]) // 2, (size - rgba.shape[1]) // 2
    out[y0:y0 + rgba.shape[0], x0:x0 + rgba.shape[1]] = rgba
    return out


def png(pixels: np.ndarray) -> bytes:
    """A PNG file of an RGB or RGBA uint8 image."""
    h, w, c = pixels.shape

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = b"".join(b"\0" + pixels[y].tobytes() for y in range(h))
    return (PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if c == 4 else 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def _dib(rgba: np.ndarray) -> bytes:
    """A 32-bit icon picture: header, BGRA rows bottom-up, then the 1-bit transparency mask."""
    h, w = rgba.shape[:2]
    bgra = rgba[::-1][..., [2, 1, 0, 3]].tobytes()
    return struct.pack("<IiiHHIIiiII", 40, w, 2 * h, 1, 32, 0, 0, 0, 0, 0, 0) + bgra + _mask(rgba)


def _mask(rgba: np.ndarray) -> bytes:
    h, w = rgba.shape[:2]
    row = (w + 31) // 32 * 4
    bits = np.packbits(rgba[::-1, :, 3] < 128, axis=1)
    return b"".join(bits[y].tobytes().ljust(row, b"\0") for y in range(h))


def ico() -> bytes:
    """An .ico file with every size, 256 as PNG."""
    pictures = [png(image(s)) if s == 256 else _dib(image(s)) for s in ICO_SIZES]
    out = struct.pack("<HHH", 0, 1, len(pictures))
    at = 6 + 16 * len(pictures)
    for s, pic in zip(ICO_SIZES, pictures):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(pic), at)
        at += len(pic)
    return out + b"".join(pictures)


def _nearest(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    d = ((rgb[:, None, :].astype(np.int64) - palette[None, :, :].astype(np.int64)) ** 2).sum(-1)
    return d.argmin(1)


def redraw(pic: bytes) -> tuple[bytes, str]:
    """One of the exe's icon pictures redrawn with our icon, same size, depth and byte length."""
    if pic[:8] == PNG_SIGNATURE:
        return pic, "a PNG picture: left as it was"
    hsize, w, h2, _, bpp, compression, _, _, _, used, _ = struct.unpack_from("<IiiHHIIiiII", pic, 0)
    h = h2 // 2
    colours = (used or 1 << bpp) if bpp <= 8 else 0
    xor_row, and_row = (w * bpp + 31) // 32 * 4, (w + 31) // 32 * 4
    at = hsize + 4 * colours
    if compression or w != h or w <= 0 or bpp not in (1, 4, 8, 24, 32) or at + (xor_row + and_row) * h > len(pic):
        return pic, f"a {w}x{h} {bpp}-bit picture this build can't redraw: left as it was"
    rgba = image(w)[::-1]
    solid = rgba[..., 3] >= 128
    if bpp == 32:
        rows = rgba[..., [2, 1, 0, 3]]
    elif bpp == 24:
        rows = rgba[..., [2, 1, 0]]
    else:
        palette = np.frombuffer(pic, np.uint8, 4 * colours, hsize).reshape(-1, 4)[:, [2, 1, 0]]
        idx = _nearest(rgba[..., :3].reshape(-1, 3), palette).reshape(h, w)
        idx[~solid] = 0
        rows = np.packbits(np.unpackbits(idx.astype(np.uint8)[..., None], axis=2)[..., 8 - bpp:].reshape(h, -1),
                           axis=1)
    xor = b"".join(rows[y].tobytes().ljust(xor_row, b"\0") for y in range(h))
    out = pic[:at] + xor + _mask(rgba[::-1]) + pic[at + (xor_row + and_row) * h:]
    return out, f"{w}x{h} {bpp}-bit"


def into_exe(exe: bytes) -> tuple[bytes, list[str]]:
    """A copy of an exe with our icon in every icon picture it has, each redrawn in place."""
    out, notes = bytearray(exe), []
    for (rtype, name, _), (at, size, _) in sorted(pe.places(exe).items(), key=lambda kv: str(kv[0])):
        if rtype != pe.RT_ICON:
            continue
        new, note = redraw(exe[at:at + size])
        out[at:at + size] = new
        notes.append(note)
    return bytes(out), notes
