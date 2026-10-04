"""Trains that lay their own rails: the Trade Cart becomes a train, and wherever it drives, rails appear behind it.

The game cannot place rails for a unit (only Villagers place buildings, and only where the player drags them), but
it can leave something on the ground behind a moving unit: its terrain restriction row says, per terrain, which
picture a unit walking there leaves behind (a row's "pass graphics"). That is how carts leave wheel tracks and soldiers
footprints in the snow (CARTSTPS: a few pictures on the ground layer, each fainter, for some seconds each, then gone).

So the train keeps the Trade Cart's own row of the terrain restriction table (its route-finding exactly the game's),
and `patch` makes that row leave a piece of track on every terrain it goes on. The siege weapons that shared it move to
the row foot soldiers and cavalry use, which lets units onto exactly the same ground (in snow they now leave footprints
instead of wheel tracks). Giving the train a row of its own crashed the game when a train was blocked by units, twice:
a row no unit used, then the sea buildings' (no one builds those; the game's route-finding seems to know only the rows
moving units have). The track is an unused graphic (one of
TRACK_GRAPHICS, an old piece of the Galley or the Trade Cog) pointed at a new SLP (`track_slp`): a straight piece of
rails, iron on dark sleepers, as wide as the train's wheels, in 8 directions (the train's), on the ground under every
unit. Right-click another player's Market and the train lays rails all the way there. The player wanted them to stay
all game, but a piece shown for a day (one picture of 86400 s) went with that crash, so a piece now keeps the cart
tracks' timing, which the game is known to handle (6 s a picture), over TRACK_FRAMES pictures: 5 minutes, the last
30 s fading. Rails stay while trains keep running; pieces pile up where they pass (TRACK_SPACING sets how many).

The trains still trade, and go, exactly where Trade Carts did, the computer players' too.
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
# graphics no unit and no other graphic uses, with an SLP of their own: old pieces of the Galley and the Trade Cog (the
# giant Pac-Man takes the first free one of gameplay.GIANT_GRAPHICS, which starts the other end)
TRACK_GRAPHICS = ("GALLY_A1", "GALLY_F1", "COGXX_W1", "COGXX_A1")
TRACK_ANGLES, TRACK_MIRRORING = 8, 6  # the train's 8 directions, the right half mirrored (as the cart tracks)
TRACK_FRAMES, TRACK_SECONDS = 50, 6.0  # pictures, each shown as long as a cart track's: 5 minutes in all
TRACK_FADING = 5  # the last pictures, fainter and fainter
TRACK_LAYER = 10  # the ground, under every unit (the cart tracks')
TRACK_SEQUENCE = 3  # played once (the cart tracks')
TRACK_SPACING = 4  # how often a piece is left (the cart tracks' "replication")
TRACK_LENGTH = 0.6 * TILE  # one piece, behind the train: longer than the cart tracks', so the next one overlaps it
NO_PASS = (-1, -1, -1, 0)  # pass graphics: nothing left behind
# where a graphic's fields are, after its SLP id (datfile.Graphic.slp_at): frame count, angle count, seconds per
# frame, replay delay, sequence type, mirroring (datfile._graphics reads them in this order)
FRAMES_AT, ANGLES_AT, RATE_AT, REPLAY_AT, SEQUENCE_AT, MIRROR_AT = 23, 25, 31, 35, 39, 42
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


def track_graphic(graphics: dict, civs, taken: set[int]) -> Optional[int]:
    """A graphic for the track: one of TRACK_GRAPHICS that no unit, no other graphic and no flame on a damaged
    building uses, with an SLP of its own, no deltas and no per-direction sounds (so its directions may change), not
    `taken` (by the giant or the fireball)."""
    used = set(taken)
    for units in civs.units:
        for u in units:
            if u is not None:
                used |= {g for k in ("standing", "dying", "walking") for g in u.values.get(k, ())}
                used |= set(u.values.get("damage_graphics", ()))
                used.add(u.values.get("attack_graphic", -1))
    used |= {d.graphic_id for g in graphics.values() for d in g.deltas}
    sharing = {}
    for g in graphics.values():
        sharing[g.slp] = sharing.get(g.slp, 0) + 1
    for name in TRACK_GRAPHICS:
        for gid, g in graphics.items():
            if (g.name.upper() == name and gid not in used and not g.deltas and g.slp > 0 and sharing[g.slp] == 1
                    and g.angle_sounds_at < 0 and g.slp_at >= 0):
                return gid
    return None


def patch(data: bytearray, civs, graphics: dict, slp_id: int,
          taken: set[int] = frozenset()) -> tuple[Optional[tuple[int, int, int]], str, Optional[dict[str, int]]]:
    """The trains (in place): the Trade Cart leaves rails behind it, drawn from SLP `slp_id`; the units that shared its
    terrain restriction row move to one exactly like it. Returns ((the track's graphic, the trains' row, the others')
    or None, what happened, the train's text ids)."""
    gid = track_graphic(graphics, civs, taken)
    if gid is None:
        return None, f"Trains: not changed, none of {', '.join(TRACK_GRAPHICS)} is free for their rails", None
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
    struct.pack_into("<i", data, g.slp_at, slp_id)
    struct.pack_into("<b", data, g.layer_at, TRACK_LAYER)
    struct.pack_into("<HH", data, g.slp_at + FRAMES_AT, TRACK_FRAMES, TRACK_ANGLES)
    struct.pack_into("<ff", data, g.slp_at + RATE_AT, TRACK_SECONDS, 0.0)
    struct.pack_into("<b", data, g.slp_at + SEQUENCE_AT, TRACK_SEQUENCE)
    struct.pack_into("<b", data, g.slp_at + MIRROR_AT, TRACK_MIRRORING)
    first = trains[0]
    strings = {"name": first.values["name_id"], "creation": first.values["creation_id"]}
    if first.values["help_id"] > HELP_STRINGS:
        strings["help"] = first.values["help_id"] - HELP_STRINGS
    names = sorted({u.name for u in moved})
    return (gid, row, other), (f"Trains: the Trade Carts (units {', '.join(map(str, TRAINS))}, {len(trains)} in all) "
                               f"keep their terrain restriction {row}, which now leaves rails behind them: graphic "
                               f"{gid} ({g.name}) draws SLP {slp_id} in {TRACK_ANGLES} directions, {TRACK_FRAMES} "
                               f"pictures of {TRACK_SECONDS:g} s; the units that shared it ({', '.join(names)}) "
                               f"use {other}, exactly like it"), strings
