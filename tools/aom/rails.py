"""Trains that lay their own rails: the Trade Cart becomes a train, and wherever it drives, rails appear behind it.

The game cannot place rails for a unit (only Villagers place buildings, and only where the player drags them), but
it can leave something on the ground behind a moving unit: its terrain restriction row says, per terrain, which
picture a unit walking there leaves behind (a row's "pass graphics"). That is how carts leave wheel tracks and soldiers
footprints in the snow (CARTSTPS and FOOTSTPS: a few pictures on the ground layer, 6 s each, then gone).

So `patch` keeps the train (the Trade Cart, empty 128 and loaded 204) on its own row, so it goes and finds its way
round things exactly as the Trade Cart did, and makes that row leave the cart tracks on every terrain it goes on, not
only snow. The siege weapons that shared the row move to the one foot soldiers and cavalry use, which lets units onto
exactly the same ground (in snow they leave footprints instead of wheel tracks). The cart tracks' graphic then belongs
to the trains alone: every setting as the game has it, but a new SLP (`track_slp`: a straight piece of rails, iron on
dark sleepers, as wide as the train's wheels, in the train's 8 directions) and more pictures (TRACK_FRAMES of 6 s:
5 minutes, the last 30 s fading). Each piece lies behind the train, never ahead, so rails only lie where the train
went, round buildings and trees as it went; they stay while trains keep running.

What crashed the game whenever a train was blocked by units, before this: a row of the trains' own (one no unit
used, then the sea buildings'), each time with the track drawn by a borrowed graphic (an old Galley piece, which
keeps the Galley's drawing flags: transparent selection, old colours).
"""
from __future__ import annotations

import struct
import zlib
from typing import Optional

import numpy as np

from . import datfile, slp
from . import datunits as DU
from .geometry import Part, cuboid
from .render import fit_camera, render
from .textures import Painter
from .voxel import TILE

TRAINS = (128, 204)  # the Trade Cart, empty and loaded
TRADE_CART = 19  # their unit class
HELP_STRINGS = 79000  # the .dat stores help text ids 79000 above the string's id (as gameplay.HELP_STRINGS)
TRAIN_SCALE = 1.6  # the train's size (siege.trade_cart), which the track is as wide as
GAUGE = 6.5 * TRAIN_SCALE  # from the track's middle to each rail: under the train's wheels (6.5 out, scaled)
SLEEPER, IRON, IRON_EDGE = "#6b4a2b", "#c4c4c4", "#6e6e6e"
TRACK = "CARTSTPS"  # the cart tracks' graphic: 8 directions (mirrored), 6 s a picture, the ground layer
TRACK_ANGLES = 8
TRACK_FRAMES = 50  # pictures of 6 s: 5 minutes (the game's tracks have 5: 30 s)
TRACK_FADING = 5  # the last pictures, fainter and fainter
TRACK_SPACING = 4  # how often a piece is left (the cart tracks' "replication")
TRACK_LENGTH = 0.6 * TILE  # one piece, behind the train: longer than the cart tracks', so the next one overlaps it
FRAMES_AT = 23  # where a graphic's frame count is, after its SLP id (datfile.Graphic.slp_at)
TEXTS = {"name": "Train", "creation": "Build Train",
         "help": "Build <b> Train<b> (<cost>) \nTrades by land, laying its own rails as it goes: carries goods from "
                 "your Market to another player's Market and brings back gold. The farther the Market, the higher "
                 "your profit. To trade, click the Train, then right-click an allied or neutral Market. <i> Upgrades: "
                 "more resistant to Monks (Monastery).<i> \n<hp> <attack> <armor> <piercearmor> <range>"}
SHORT_HELP = "Build <b> Train<b> (<cost>) \nTrades by land, laying its own rails."


# --------------------------------------------------------------------------- the look

def track(length: float = TRACK_LENGTH, sleepers: int = 3) -> Part:
    """A straight piece of rails behind the origin, where the train just was (model -y; it faces +y): dark sleepers
    across it, two iron rails on them under the train's wheels. It never reaches ahead of the train, so rails only lie
    where the train went, round buildings and trees as it went."""
    p = Painter("track")
    reach = GAUGE + 3.5  # a sleeper sticks out past each rail
    wood = p.skin((2 * reach, 3.5, 1), p.speckle(SLEEPER, ("#5a3c22", 0.3)))
    rail = p.skin((2, length, 1.5), p.bands((1, IRON_EDGE)), top=IRON)
    step = length / sleepers
    boxes = [cuboid((-reach, -length + (k + 0.5) * step - 1.75, 0), (2 * reach, 3.5, 1), wood)
             for k in range(sleepers)]
    boxes += [cuboid((w - 1, -length, 1), (2, length, 1.5), rail) for w in (-GAUGE, GAUGE)]
    return Part("track", boxes=boxes)


_TRACK_SLPS: dict[tuple, bytes] = {}


def track_frames(quant, frames: int = TRACK_FRAMES, angles: int = TRACK_ANGLES,
                 mirroring: bool = True) -> list[slp.SlpFrame]:
    """The track's pictures: for each stored direction, the piece of rails, fainter over its last TRACK_FADING."""
    from .export import _crop, headings
    root, out = track(), []
    fading = min(TRACK_FADING, frames - 1)
    keep = [1.0] * (frames - fading) + [1 - (k + 1) / (fading + 1) for k in range(fading)]
    for heading in headings(angles, mirroring):
        cam = fit_camera(root, heading)
        f = render(root, heading, camera=cam, shadow=False, outline=False)
        whole = _crop(quant.frame_codes(f, obstruction=False), cam.origin)
        out += [_faded(whole, k, n) for n, k in enumerate(keep)]
    return out


def _faded(frame: slp.SlpFrame, keep: float, seed: int) -> slp.SlpFrame:
    """The picture with only about `keep` of its pixels left (the same ones in every direction)."""
    if keep >= 1:
        return frame
    rng = np.random.default_rng(zlib.crc32(f"track fade {seed}".encode()))
    px = frame.pixels.copy()
    px[rng.random(px.shape) >= keep] = slp.TRANSPARENT
    return slp.SlpFrame(px, frame.hotspot)


def track_slp(quant, frames: int = TRACK_FRAMES, angles: int = TRACK_ANGLES, mirroring: bool = True) -> bytes:
    key = (np.asarray(quant.palette).tobytes(), frames, angles, bool(mirroring))
    if key not in _TRACK_SLPS:
        _TRACK_SLPS[key] = slp.encode(track_frames(quant, frames, angles, mirroring))
    return _TRACK_SLPS[key]


# --------------------------------------------------------------------------- the .dat

def siege_row(data: bytes, civs, train: int) -> Optional[int]:
    """Where the units sharing the trains' row `train` go: the row exactly like it that most units use."""
    rows = datfile.restrictions(data)
    users: dict[int, int] = {}
    for units in civs.units:
        for u in units:
            if u is not None:
                users[u.values["terrain_restriction"]] = users.get(u.values["terrain_restriction"], 0) + 1
    same = [k for k, row in enumerate(rows) if k != train and row == rows[train] and users.get(k)]
    return max(same, key=lambda k: users[k]) if same else None


def _row_at(data: bytes, row: int) -> int:
    """Offset of a restriction row's numbers (after them: its pass graphics, 16 bytes per terrain)."""
    rows, terrains = struct.unpack_from("<HH", data, 8)
    return 12 + 8 * rows + row * terrains * 20


def track_graphic(data: bytes, graphics: dict, row: int) -> Optional[int]:
    """The cart tracks' graphic, if it is as this build knows it (8 directions, mirrored, no deltas, no per-direction
    sounds) and no row but the trains' (`row`) leaves it behind."""
    gid = next((gid for gid, g in graphics.items() if g.name.upper() == TRACK), None)
    g = graphics.get(gid)
    if g is None or g.deltas or g.slp <= 0 or g.angle_count != TRACK_ANGLES or not g.mirroring or g.slp_at < 0:
        return None
    rows, terrains = struct.unpack_from("<HH", data, 8)
    for k in range(rows):
        at = _row_at(data, k) + 4 * terrains
        if k != row and any(struct.unpack_from("<iiii", data, at + 16 * t)[:3].count(gid) for t in range(terrains)):
            return None
    return gid


def patch(data: bytearray, civs, graphics: dict,
          slp_id: int) -> tuple[Optional[tuple[int, int, int]], str, Optional[dict[str, int]]]:
    """The trains (in place): the Trade Cart leaves rails behind it, drawn from SLP `slp_id`; the units that shared its
    terrain restriction row move to one exactly like it. Returns ((the track's graphic, the trains' row, the others')
    or None, what happened, the train's text ids)."""
    trains = [u for units in civs.units if len(units) > max(TRAINS) for u in (units[k] for k in TRAINS)
              if u is not None and u.type == 70 and u.values["class"] == TRADE_CART]
    if not trains:
        return None, f"Trains: not changed, units {', '.join(map(str, TRAINS))} are not the Trade Cart here", None
    rows = datfile.restrictions(bytes(data))
    row = trains[0].values["terrain_restriction"]
    if row >= len(rows) or any(u.values["terrain_restriction"] != row for u in trains):
        return None, "Trains: not changed, the Trade Carts do not all go on the same ground", None
    other = siege_row(bytes(data), civs, row)
    if other is None:
        return None, f"Trains: not changed, no other units' row is exactly like theirs ({row})", None
    gid = track_graphic(bytes(data), graphics, row)
    if gid is None:
        return None, f"Trains: not changed, the cart tracks' graphic ({TRACK}) is not the one this build knows", None
    moved = [u for units in civs.units for u in units if u is not None and u.values["terrain_restriction"] == row
             and u not in trains]
    for u in moved:
        DU.patch(data, u, terrain_restriction=other)
    terrains = len(rows[0])
    at = _row_at(bytes(data), row)
    for t, passable in enumerate(rows[row]):  # rails behind it on every bit of ground it goes on
        if passable > 0:
            struct.pack_into("<iiii", data, at + 4 * terrains + 16 * t, -1, -1, gid, TRACK_SPACING)
    g = graphics[gid]
    struct.pack_into("<i", data, g.slp_at, slp_id)  # the rails, and more of them: everything else as it was
    struct.pack_into("<H", data, g.slp_at + FRAMES_AT, TRACK_FRAMES)
    first = trains[0]
    strings = {"name": first.values["name_id"], "creation": first.values["creation_id"]}
    if first.values["help_id"] > HELP_STRINGS:
        strings["help"] = first.values["help_id"] - HELP_STRINGS
    names = sorted({u.name for u in moved})
    return (gid, row, other), (f"Trains: the Trade Carts (units {', '.join(map(str, TRAINS))}, {len(trains)} in all) "
                               f"keep their terrain restriction {row}, which now leaves rails behind them: the cart "
                               f"tracks (graphic {gid}, {g.name}) draw SLP {slp_id}, {TRACK_FRAMES} pictures of "
                               f"{g.frame_rate:g} s; the units that shared it ({', '.join(names)}) "
                               f"use {other}, exactly like it"), strings
