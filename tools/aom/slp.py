"""SLP 2.0N sprites, the graphics format of AoE2 up to The Conquerors.

Layout (see openage's doc/media/slp-files.md):

    header      "2.0N", int32 frame count, 24-byte comment
    frame info  32 bytes per frame: command table offset, outline table
                offset, palette offset, properties, width, height, hotspot x, y
    per frame   outline table (left/right transparent margins per row),
                command offset table (uint32 per row), row commands

A frame is given here as an int array of pixel codes:

    TRANSPARENT (-1), SHADOW (-2), OBSTRUCTION (-3; the team-colour outline
    shown when the unit is behind a building), 0..255 palette index,
    PLAYER + 0..7 (team colour shade, 0 darkest).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

TRANSPARENT, SHADOW, OBSTRUCTION = -1, -2, -3
PLAYER = 0x100
COMMENT = b"Age of Minecraft".ljust(24, b"\0")


@dataclass
class SlpFrame:
    pixels: np.ndarray  # (h, w) int16 pixel codes
    hotspot: tuple[int, int]


def _count_cmd(code: int, n: int) -> bytes:
    """Commands whose count lives in the high nibble, or in the next byte when it does not fit."""
    return bytes([(n << 4) | code]) if n < 16 else bytes([code, n])


def _encode_row(row: np.ndarray) -> bytes:
    out = bytearray()
    i, n = 0, len(row)
    while i < n:
        v = int(row[i])
        j = i + 1
        if v == TRANSPARENT or v == SHADOW or v == OBSTRUCTION:
            while j < n and row[j] == v:
                j += 1
        elif v >= PLAYER:
            while j < n and row[j] >= PLAYER:
                j += 1
        else:
            while j < n and 0 <= row[j] < PLAYER:
                j += 1
        run = row[i:j]
        while len(run):
            if v == TRANSPARENT:
                k = min(len(run), 4095)
                out += bytes([(k << 2) | 0x01]) if k < 64 else bytes([((k >> 8) << 4) | 0x03, k & 0xFF])
            elif v == SHADOW:
                k = min(len(run), 255)
                out += _count_cmd(0x0B, k)
            elif v == OBSTRUCTION:
                k = min(len(run), 255)
                out += bytes([0x4E]) if k == 1 else bytes([0x5E, k])
            elif v >= PLAYER:
                k = min(len(run), 255)
                out += _count_cmd(0x06, k) + bytes(int(x) - PLAYER for x in run[:k])
            else:
                k = min(len(run), 4095)
                head = bytes([k << 2]) if k < 64 else bytes([((k >> 8) << 4) | 0x02, k & 0xFF])
                out += head + bytes(int(x) for x in run[:k])
            run = run[k:]
        i = j
    out.append(0x0F)
    return bytes(out)


def _encode_frame(frame: SlpFrame) -> tuple[bytes, bytes]:
    """Outline table and row commands (command offsets are filled in by the caller)."""
    px = frame.pixels
    edges = bytearray()
    rows = []
    for row in px:
        filled = np.nonzero(row != TRANSPARENT)[0]
        if not len(filled):
            edges += struct.pack("<HH", 0x8000, 0x8000)
            rows.append(b"")
            continue
        left, right = int(filled[0]), int(filled[-1])
        edges += struct.pack("<HH", left, len(row) - 1 - right)
        rows.append(_encode_row(row[left:right + 1]))
    return bytes(edges), rows


def encode(frames: list[SlpFrame]) -> bytes:
    header = b"2.0N" + struct.pack("<i", len(frames)) + COMMENT
    infos = bytearray()
    body = bytearray()
    pos = 32 + 32 * len(frames)
    for f in frames:
        h, w = f.pixels.shape
        edges, rows = _encode_frame(f)
        outline_off = pos
        cmd_table_off = outline_off + len(edges)
        data_off = cmd_table_off + 4 * h
        offsets, commands = bytearray(), bytearray()
        for r in rows:
            offsets += struct.pack("<I", data_off + len(commands))
            commands += r
        infos += struct.pack("<IIIIiiii", cmd_table_off, outline_off, 0, 0, w, h, f.hotspot[0], f.hotspot[1])
        chunk = edges + offsets + commands
        body += chunk
        pos += len(chunk)
    return header + bytes(infos) + bytes(body)


def replace_frame(data: bytes, index: int, frame: SlpFrame) -> bytes:
    """A copy of an SLP with one frame swapped; every other frame keeps its original bytes."""
    version, n = struct.unpack_from("<4si", data, 0)
    if version != b"2.0N" or not 0 <= index < n:
        raise ValueError("cannot replace that frame")
    h, w = frame.pixels.shape
    edges, rows = _encode_frame(frame)
    outline_off = len(data)
    cmd_table_off = outline_off + len(edges)
    data_off = cmd_table_off + 4 * h
    offsets, commands = bytearray(), bytearray()
    for r in rows:
        offsets += struct.pack("<I", data_off + len(commands))
        commands += r
    out = bytearray(data)
    old_palette, old_props = struct.unpack_from("<II", data, 32 + 32 * index + 8)
    struct.pack_into("<IIIIiiii", out, 32 + 32 * index, cmd_table_off, outline_off, old_palette, old_props, w, h,
                     frame.hotspot[0], frame.hotspot[1])
    return bytes(out + edges + offsets + commands)


# --------------------------------------------------------------------------- reading

@dataclass
class SlpInfo:
    num_frames: int
    sizes: list[tuple[int, int, int, int]]  # width, height, hotspot x, hotspot y


def info(data: bytes) -> SlpInfo:
    """Header and frame sizes only (cheap; used to match the original frame counts)."""
    version, n = struct.unpack_from("<4si", data, 0)
    if version != b"2.0N":
        raise ValueError(f"unsupported SLP version {version!r}")
    sizes = [struct.unpack_from("<iiii", data, 32 + 32 * i + 16) for i in range(n)]
    return SlpInfo(n, sizes)


def decode(data: bytes) -> list[SlpFrame]:
    """Full decode into pixel codes (used by tests and previews)."""
    n = struct.unpack_from("<i", data, 4)[0]
    frames = []
    for fi in range(n):
        cmd_off, outline_off, _, _, w, h, hx, hy = struct.unpack_from("<IIIIiiii", data, 32 + 32 * fi)
        px = np.full((h, w), TRANSPARENT, np.int16)
        for y in range(h):
            left, right = struct.unpack_from("<HH", data, outline_off + 4 * y)
            if left == 0x8000 or right == 0x8000:
                continue
            p = struct.unpack_from("<I", data, cmd_off + 4 * y)[0]
            x = left
            while True:
                c = data[p]
                p += 1
                low2, low4 = c & 0x03, c & 0x0F
                if c == 0x0F:
                    break
                if low2 == 0x00:  # lesser draw
                    k = c >> 2
                    px[y, x:x + k] = np.frombuffer(data, np.uint8, k, p)
                    p += k
                    x += k
                elif low2 == 0x01:  # lesser skip
                    k = c >> 2 or data[p]
                    if not c >> 2:
                        p += 1
                    x += k
                elif low4 == 0x02:  # greater draw
                    k = ((c & 0xF0) << 4) + data[p]
                    p += 1
                    px[y, x:x + k] = np.frombuffer(data, np.uint8, k, p)
                    p += k
                    x += k
                elif low4 == 0x03:  # greater skip
                    k = ((c & 0xF0) << 4) + data[p]
                    p += 1
                    x += k
                elif low4 in (0x06, 0x07, 0x0A, 0x0B):
                    k = c >> 4
                    if not k:
                        k = data[p]
                        p += 1
                    if low4 == 0x06:
                        px[y, x:x + k] = np.frombuffer(data, np.uint8, k, p).astype(np.int16) + PLAYER
                        p += k
                    elif low4 == 0x07:
                        px[y, x:x + k] = data[p]
                        p += 1
                    elif low4 == 0x0A:
                        px[y, x:x + k] = data[p] + PLAYER
                        p += 1
                    else:
                        px[y, x:x + k] = SHADOW
                    x += k
                elif low4 == 0x0E:
                    if c == 0x4E or c == 0x6E:
                        px[y, x] = OBSTRUCTION
                        x += 1
                    elif c == 0x5E or c == 0x7E:
                        k = data[p]
                        p += 1
                        px[y, x:x + k] = OBSTRUCTION
                        x += k
                else:
                    raise ValueError(f"unknown SLP command 0x{c:02x}")
        frames.append(SlpFrame(px, (hx, hy)))
    return frames
