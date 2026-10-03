"""Read the graphics and terrain tables from AoE2: The Conquerors' empires2_x1_p1.dat.

Only the start of the file is parsed: terrain restrictions, player colours,
sounds and then the graphics, which tell us for every sprite its SLP id,
frames per angle, angle count, mirroring and layered "delta" sprites. The
terrains come right after the graphics: their textures are SLPs in
terrain.drs (farms are terrain too). Layout follows openage's datfile
readers (doc/gamedata); the file is raw-deflate compressed.
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
    sound: int = -1
    sound_at: int = -1  # offset of the sound id in the decompressed file
    angle_sounds_at: int = -1  # offset of the per-angle sounds (3 x (delay, sound id) per angle), if any
    slp_at: int = -1  # offset of the SLP id in the decompressed file

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


SOUND_FILE = struct.Struct("<13sihhh")  # file name, resource id in the DRS archives, probability, civ, icon set


@dataclass
class SoundTable:
    count_at: int  # offset of the sound count
    end: int  # offset just past the last sound (where the graphics begin)
    count: int


def _to_sounds(data: bytes) -> Reader:
    r = Reader(data)
    version = r.take("8s")[0]
    if not version.startswith(b"VER 5."):
        raise ValueError(f"unexpected dat version {version!r}")
    restrictions, terrains = r.take("HH")
    r.skip(4 * restrictions * 2)  # float table pointers + pass-graphic pointers
    r.skip(restrictions * terrains * (4 + 16))  # damage multipliers + pass graphics
    colours = r.one("H")
    r.skip(colours * 36)
    return r


def sound_table(data: bytes) -> SoundTable:
    """Where the sounds are in the decompressed file. A sound: id, play delay, file count, cache time, files."""
    r = _to_sounds(data)
    at = r.p
    count = r.one("H")
    for _ in range(count):
        _sid, _delay, files, _cache = r.take("hhHi")
        r.skip(files * SOUND_FILE.size)
    return SoundTable(at, r.p, count)


def sound_entry(sid: int, files: list[tuple[str, int, int]]) -> bytes:
    """One sound: files as (name, resource id, probability), for every civilisation."""
    out = struct.pack("<hhHi", sid, 0, len(files), 300000)
    for name, rid, prob in files:
        out += SOUND_FILE.pack(name.encode("latin-1")[:12], rid, prob, -1, -1)
    return out


def _raw(raw_or_path) -> bytes:
    return Path(raw_or_path).read_bytes() if not isinstance(raw_or_path, (bytes, bytearray)) else raw_or_path


def read_graphics(raw_or_path) -> dict[int, Graphic]:
    return _graphics(decompress(_raw(raw_or_path)))[0]


def _graphics(data: bytes) -> tuple[dict[int, Graphic], int]:
    """The graphics, and the offset just past them (where the terrain block begins)."""
    r = Reader(data)
    r.p = sound_table(data).end
    count = r.one("H")
    ptrs = r.take(f"{count}I")
    graphics: dict[int, Graphic] = {}
    for gid, ptr in enumerate(ptrs):
        if not ptr:
            continue
        slp_at = r.p + 34
        name, filename, slp_id = r.take("21s13si")
        _loaded, _old, layer, _force, _adapt, _sel = r.take("bbbbbB")
        r.skip(8)  # coordinates
        sound_at = r.p + 2
        delta_count, sound = r.take("Hh")
        attack_sounds, frames, angles = r.take("BHH")
        _speed, rate, _replay = r.take("fff")
        seq, own_id, mirror, _editor = r.take("bhbb")
        deltas = []
        for _ in range(delta_count):
            dg, _pad, _ptr, ox, oy, angle, _pad2 = r.take("hhihhhh")
            deltas.append(Delta(dg, ox, oy, angle))
        angle_sounds_at = r.p if attack_sounds else -1
        if attack_sounds:
            r.skip(max(1, angles) * 3 * 4)
        g = Graphic(own_id if own_id >= 0 else gid, _cstr(name), _cstr(filename), slp_id, layer, frames, angles,
                    rate, seq, mirror, deltas, sound, sound_at, angle_sounds_at, slp_at)
        _check(g)
        graphics[gid] = g
    return graphics, r.p


def _check(g: Graphic) -> None:
    """Sanity checks so a mis-parse fails loudly instead of producing bad sprites."""
    printable = all(32 <= ord(c) < 127 for c in g.name + g.filename)
    if not printable or not (-1 <= g.slp < 70000) or not (0 <= g.frame_count < 5000) or not (0 <= g.angle_count <= 720):
        raise ValueError(f"graphics table looks wrong at graphic {g.id}: {g}")


# The terrain block: map pointers and sizes (6 int32), 19 tile sizes (width, height, delta z), padding, then a
# fixed number of terrain records, used or not (openage datfile/empiresdat.py and terrain.py, game "AOC").
TERRAIN_HEAD = 6 * 4 + 19 * 3 * 2 + 2
TERRAIN_SLOTS = 42
TERRAIN_SIZE = 436  # enabled, random, 2 names, SLP, ..., 19 frame data, 42 borders, 30 terrain units, phantom


@dataclass
class Terrain:
    id: int
    enabled: bool
    name: str
    filename: str
    slp: int  # the texture in terrain.drs: one diamond-shaped frame per tile
    rows: int
    cols: int


def read_terrains(raw_or_path) -> list[Terrain]:
    data = decompress(_raw(raw_or_path))
    at = _graphics(data)[1]
    sizes = struct.unpack_from("<57h", data, at + 24)
    if not all(0 <= v <= 512 for v in sizes[0::3] + sizes[1::3]):
        raise ValueError(f"terrain block looks wrong: tile sizes {sizes[:6]}...")
    terrains = []
    for i in range(TERRAIN_SLOTS):
        base = at + TERRAIN_HEAD + i * TERRAIN_SIZE
        enabled, _random, name, filename, slp_id = struct.unpack_from("<bb13s13si", data, base)
        _to_draw, rows, cols = struct.unpack_from("<hhh", data, base + 192)
        t = Terrain(i, bool(enabled), _cstr(name), _cstr(filename), slp_id, rows, cols)
        printable = all(32 <= ord(c) < 127 for c in t.name + t.filename)
        if not printable or not (-1 <= t.slp < 100000) or not (-1 <= rows <= 100 and -1 <= cols <= 100):
            raise ValueError(f"terrain table looks wrong at terrain {i}: {t}")
        terrains.append(t)
    if not any(t.name for t in terrains):
        raise ValueError("terrain table looks wrong: no terrain has a name")
    return terrains
