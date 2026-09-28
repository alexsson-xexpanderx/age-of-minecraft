"""Read the graphics table from AoE2: The Conquerors' empires2_x1_p1.dat.

Only the start of the file is parsed: terrain restrictions, player colours,
sounds and then the graphics, which tell us for every sprite its SLP id,
frames per angle, angle count, mirroring and layered "delta" sprites. Layout
follows openage's datfile readers (doc/gamedata); the file is raw-deflate
compressed.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Delta:
    graphic_id: int
    offset_x: int
    offset_y: int
    display_angle: int


@dataclass
class Graphic:
    id: int
    name: str
    filename: str
    slp: int
    layer: int
    frame_count: int
    angle_count: int
    frame_rate: float
    sequence_type: int
    mirroring: int
    deltas: list[Delta] = field(default_factory=list)

    @property
    def stored_angles(self) -> int:
        """Angles actually stored in the SLP (the rest are mirrored by the game)."""
        a = max(1, self.angle_count)
        return a // 2 + 1 if self.mirroring and a > 1 else a


class Reader:
    def __init__(self, data: bytes):
        self.d, self.p = data, 0

    def take(self, fmt: str):
        vals = struct.unpack_from("<" + fmt, self.d, self.p)
        self.p += struct.calcsize("<" + fmt)
        return vals

    def one(self, fmt: str):
        return self.take(fmt)[0]

    def skip(self, n: int) -> None:
        self.p += n


def _cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("latin-1")


def decompress(raw: bytes) -> bytes:
    return zlib.decompress(raw, -15)


def read_graphics(raw_or_path) -> dict[int, Graphic]:
    raw = Path(raw_or_path).read_bytes() if not isinstance(raw_or_path, (bytes, bytearray)) else raw_or_path
    r = Reader(decompress(raw))
    version = r.take("8s")[0]
    if not version.startswith(b"VER 5."):
        raise ValueError(f"unexpected dat version {version!r}")
    restrictions, terrains = r.take("HH")
    r.skip(4 * restrictions * 2)  # float table pointers + pass-graphic pointers
    r.skip(restrictions * terrains * (4 + 16))  # damage multipliers + pass graphics
    colours = r.one("H")
    r.skip(colours * 36)
    sounds = r.one("H")
    for _ in range(sounds):
        _sid, _delay, files, _cache = r.take("hhHi")
        r.skip(files * (13 + 4 + 2 + 2 + 2))
    count = r.one("H")
    ptrs = r.take(f"{count}I")
    graphics: dict[int, Graphic] = {}
    for gid, ptr in enumerate(ptrs):
        if not ptr:
            continue
        name, filename, slp_id = r.take("21s13si")
        _loaded, _old, layer, _force, _adapt, _sel = r.take("bbbbbB")
        r.skip(8)  # coordinates
        delta_count, _sound = r.take("Hh")
        attack_sounds, frames, angles = r.take("BHH")
        _speed, rate, _replay = r.take("fff")
        seq, own_id, mirror, _editor = r.take("bhbb")
        deltas = []
        for _ in range(delta_count):
            dg, _pad, _ptr, ox, oy, angle, _pad2 = r.take("hhihhhh")
            deltas.append(Delta(dg, ox, oy, angle))
        if attack_sounds:
            r.skip(max(1, angles) * 3 * 4)
        g = Graphic(own_id if own_id >= 0 else gid, _cstr(name), _cstr(filename), slp_id, layer, frames, angles,
                    rate, seq, mirror, deltas)
        _check(g)
        graphics[gid] = g
    return graphics


def _check(g: Graphic) -> None:
    """Sanity checks so a mis-parse fails loudly instead of producing bad sprites."""
    printable = all(32 <= ord(c) < 127 for c in g.name + g.filename)
    if not printable or not (-1 <= g.slp < 70000) or not (0 <= g.frame_count < 5000) or not (0 <= g.angle_count <= 720):
        raise ValueError(f"graphics table looks wrong at graphic {g.id}: {g}")
