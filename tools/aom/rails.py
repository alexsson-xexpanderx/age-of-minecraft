"""Rails and trains: the Trade Cart becomes a train that only drives on rails, which Villagers lay like a wall.

The game has no rails, so they are made of three leftovers in the .dat (`patch`):

- the rail is the Sea Wall (unit 788), a wall no one can build: Villagers build it (second page, next to the Gate),
  dragging a line as they drag a wall, for 1 wood and 1 gold a tile, on land, where a Palisade Wall may stand (a Sea
  Wall stood in water). It stays a wall to the game (so the dragging, and the pieces of a line), but nothing is
  stopped by it, as nothing is by a farm: its obstruction type is 0;
- under each rail it leaves gravel (its foundation terrain): terrain 16, "Old Grass", which no map uses and which
  the game draws with the Grass's texture. It gets its own, Minecraft gravel cut into the Grass's tile shapes
  (`encode`), the Road's blending and a grey on the minimap. Everyone walks and builds on it as on grass;
- the train (the Trade Cart, empty 128 and loaded 204) may only stand on that gravel: its terrain restriction becomes
  an empty row of the restriction table that no unit uses, letting it onto terrain 16 alone.

So a train goes only where rails were laid, and trades like the Trade Cart: from its Market to another player's
and back. The gravel is ground, which no player owns: any player's train can use any rail (in practice an ally's,
trading with the same Markets). The computer players never lay rails, so their trains cannot trade.

The rails are drawn by the Sea Wall's own graphics: one picture per wall piece (the game's order, see
fortifications.py), on its layer 5 piece, under every unit (`rail_piece`); its other two pieces are blanked.
"""
from __future__ import annotations

import struct
import zlib
from functools import lru_cache
from typing import Optional

import numpy as np

from . import datfile, farmland, slp
from . import datunits as DU
from . import voxel as V
from .blocks import BlockType
from .geometry import Part, cuboid
from .palette import Quantiser
from .render import Frame, fit_camera, render
from .textures import Painter, parse

RAIL_BED = 16  # "Old Grass": the gravel under the rails
GRASS, ROAD = 0, 24  # the terrain it is drawn as (its tile shapes), and the one it blends like
RAIL = 788  # the Sea Wall
PALISADE = 72  # the Palisade Wall: where it may stand (on land), the rail may too (the Sea Wall's own: water)
RAIL_NAME = "SWAL"  # its graphics' names: SWAL1N0 (layer 5), SWAL1N1 and SWAL1NN
WALL = 27  # unit class: Villagers drag walls out in lines
TRAINS = (128, 204)  # the Trade Cart, empty and loaded
TRADE_CART = 19  # their unit class
VILLAGER = 118
HELP_STRINGS = 79000  # the .dat stores help text ids 79000 above the string's id (as gameplay.HELP_STRINGS)
RAIL_BUTTON = 12  # on the Villager's second page, between the Gate (11) and the Castle (13), as the Sea Wall was
RAIL_COST = (1, 1, 1, 3, 1, 1, -1, 0, 0)  # 1 wood, 1 gold
OVER = 0  # obstruction type: others go over it (a farm's)
NO_PASS = (-1, -1, -1, 0)  # pass graphics: no tracks left on the gravel
MINIMAP = (132, 128, 124)
GRAVEL = ("#837f7d", "#6e6a68", "#9a9593", "#5c5856", "#8a7f74")  # Minecraft's gravel: greys and a brown
PLANKS, SLEEPER, IRON, IRON_EDGE = "#a0814f", "#6b4a2b", "#c4c4c4", "#6e6e6e"
TRAIN_SCALE = 1.6  # the train's size (siege.trade_cart), which the track is as wide as
GAUGE = 6.5 * TRAIN_SCALE  # from the track's middle to each rail: under the train's wheels (6.5 out, scaled)
BUILDING_ICONS = (50705, 50706, 50707, 50708)  # the building icon sheets in interfac.drs, one per icon set
ICON_COLOURS = {0: (110, 106, 104), 1: (140, 135, 132), 2: (84, 80, 78), 3: (107, 74, 43), 4: (72, 48, 26),
                5: (200, 200, 200), 6: (100, 100, 100)}
TEXTS = {"rail": {"name": "Rail", "creation": "Build Rail",
                  "help": "Build <b> Rail<b> (<cost>) \nTracks for Trains, which only drive on rails. Drag a line of "
                          "rails from your Market to another player's Market, and Trains can trade between them. "
                          "\n<hp> <attack> <armor> <piercearmor> <range>"},
         "train": {"name": "Train", "creation": "Build Train",
                   "help": "Build <b> Train<b> (<cost>) \nTrades with other players by land, on rails only: lay "
                           "rails from your Market to another player's. Carries goods there and brings back gold; the "
                           "farther the Market, the more gold. To trade, click the Train, then right-click an allied "
                           "or neutral Market. <i> Upgrades: more resistant to Monks (Monastery).<i> \n<hp> "
                           "<attack> <armor> <piercearmor> <range>"}}
SHORT_HELP = {"rail": "Build <b> Rail<b> (<cost>) \nTracks for Trains.",
              "train": "Build <b> Train<b> (<cost>) \nTrades by land. Drives only on rails."}


# --------------------------------------------------------------------------- the look

def gravel_texture(seed: str = "gravel") -> np.ndarray:
    """16x16 Minecraft gravel: grey pebbles of several shades, a few brown."""
    rng = np.random.default_rng(zlib.crc32(seed.encode()))
    pick = rng.choice(len(GRAVEL), size=(16, 16), p=[0.38, 0.24, 0.16, 0.12, 0.10])
    return np.array([parse(c) for c in GRAVEL])[pick]


@lru_cache(maxsize=None)
def texture(per_tile: int = farmland.PER_TILE) -> tuple[Frame, tuple[int, int]]:
    """Gravel blocks from the game's camera, and the screen position of the centre tile's centre."""
    n, reach = per_tile, 2
    s = V.Structure("gravel", origin=(n / 2, n / 2))
    for x in range(-reach * n, (reach + 1) * n):
        for y in range(-reach * n, (reach + 1) * n):
            s.set(x, y, -1, "rail_gravel")
    root = s.part({**V.all_blocks(), "rail_gravel": BlockType.uniform(gravel_texture())})
    cam = fit_camera(root, V.BUILDING_HEADING, scale=farmland.scale(per_tile), pad=2)
    frame = render(root, V.BUILDING_HEADING, camera=cam, shadow=False, outline=False)
    return frame, (int(cam.origin[0]), int(cam.origin[1]))


def encode(grass: bytes, quant: Quantiser) -> bytes:
    """The gravel's texture: the Grass's SLP `grass`, every tile redrawn as gravel."""
    return slp.encode(farmland.cut(*texture(), grass, quant, "the gravel"), props=slp.frame_props(grass))


def ground(w: int, h: int, x0: int = 0, y0: int = 0) -> np.ndarray:
    """RGBA gravel for a w x h picture whose corner is map pixel (x0, y0) (for previews), laid as the game lays it."""
    frame, (ox, oy) = texture()
    rgba = frame.to_rgba()
    yy, xx = np.mgrid[y0:y0 + h, x0:x0 + w].astype(float)
    i, j = (xx / 48 + yy / 24) / 2, (yy / 24 - xx / 48) / 2
    i, j = i - np.round(i), j - np.round(j)
    return rgba[(oy + (i + j) * 24).astype(int), (ox + (i - j) * 48).astype(int)]


def _track(p: Painter, name: str, length: float, sleepers: int, angle: float) -> Part:
    """A straight track through the tile's centre, `length` long, at `angle` degrees from model x: sleepers across
    it, two iron rails on them, ending just past the tile so the next tile's joins it."""
    reach = GAUGE + 3.5  # a sleeper sticks out past each rail
    wood = p.skin((3.5, 2 * reach, 1), p.speckle(SLEEPER, ("#5a3c22", 0.3)))
    rail = p.skin((length + 2, 2, 1.5), p.bands((1, IRON_EDGE)), top=IRON)
    step = length / sleepers
    boxes = [cuboid((-length / 2 + (k + 0.5) * step - 1.75, -reach, 0), (3.5, 2 * reach, 1), wood)
             for k in range(sleepers)]
    boxes += [cuboid((-length / 2 - 1, w - 1, 1), (length + 2, 2, 1.5), rail) for w in (-GAUGE, GAUGE)]
    return Part(name, rot=(0, 0, angle), boxes=boxes)


def rail_piece(piece: str) -> Part:
    """One tile of rails, in the wall pieces' meaning (fortifications.PIECES): "x" along model x, "y" along y, "h"
    and "v" corner to corner, and the post (a line's ends and bends) a plank platform, like a little station, which
    a track arriving at any side or corner meets."""
    p = Painter(f"rail_{piece}")
    t = V.TILE
    if piece == "post":
        deck = p.skin((t, t, 1), p.grid([("PPPPPPPPdPPPPPPP" if k % 4 == 3 else "PPPPPPPPPPPPPPPP") for k in range(16)],
                                        {"P": PLANKS, "d": "#6f5530"}), top=p.grid(
            [("ddddddddddddddd" if k % 4 == 3 else ("PPPPPPPdPPPPPPP" if (k // 4) % 2 else "PPPdPPPPPPPdPPP"))
             for k in range(16)], {"P": PLANKS, "d": "#6f5530"}))
        return Part("rail_post", boxes=[cuboid((-t / 2, -t / 2, 0), (t, t, 1.5), deck)])
    if piece in ("x", "y"):
        return _track(p, f"rail_{piece}", t, 6, 0 if piece == "x" else 90)
    return _track(p, f"rail_{piece}", t * 2 ** 0.5, 8, -45 if piece == "h" else 45)


def rail_icon(size: int = 36) -> np.ndarray:
    """A building icon (drawn at 36x36, scaled to `size`): a straight track on gravel, Minecraft's rail item. Colours
    are keys of ICON_COLOURS."""
    rng = np.random.default_rng(zlib.crc32(b"rail icon"))
    px = rng.choice((0, 1, 2), size=(36, 36), p=(0.6, 0.25, 0.15)).astype(np.int16)
    for y in range(2, 36, 6):  # sleepers
        px[y:y + 3, 5:31] = 3
        px[y + 2, 5:31] = 4
    for x in (9, 24):  # the rails
        px[:, x:x + 3] = 5
        px[:, x + 2] = 6
    if size != 36:
        idx = np.arange(size) * 36 // size
        px = px[idx][:, idx]
    return px


def add_icon(data: bytes, index: int, quant) -> tuple[Optional[bytes], str]:
    """A building icon sheet with the rail's icon added as icon `index` (blank icons fill any gap before it)."""
    try:
        info = slp.info(data)
    except ValueError as exc:
        return None, f"not changed ({exc})"
    if info.num_frames > index:
        return None, f"not changed: this sheet already has an icon {index}"
    sizes = [(w, h) for w, h, _, _ in info.sizes if 16 <= w <= 96 and 16 <= h <= 96]
    if not sizes:
        return None, "not changed: no icon in this sheet has a usable size"
    w, h = max(set(sizes), key=sizes.count)
    lut = {k: int(quant.indices(np.array([rgb], np.int64))[0]) for k, rgb in ICON_COLOURS.items()}
    px = np.vectorize(lut.get)(rail_icon(min(w, h))).astype(np.int16)
    if (w, h) != px.shape[::-1]:  # not square: centred on gravel
        full = np.full((h, w), lut[0], np.int16)
        y0, x0 = (h - px.shape[0]) // 2, (w - px.shape[1]) // 2
        full[y0:y0 + px.shape[0], x0:x0 + px.shape[1]] = px
        px = full
    blank = slp.SlpFrame(np.full((1, 1), slp.TRANSPARENT, np.int16), (0, 0))
    frames = [blank] * (index - info.num_frames) + [slp.SlpFrame(px, (0, 0))]
    return slp.append_frames(data, frames), f"the rail is icon {index} ({w}x{h})"


# --------------------------------------------------------------------------- the .dat

def rail_bed(data: bytes) -> tuple[Optional[datfile.Terrain], str]:
    """Terrain 16, if it is the unused old grass this build knows: (terrain or None, why not)."""
    try:
        terrains, rows = datfile.terrains_in(data), datfile.restrictions(data)
    except (ValueError, IndexError) as exc:
        return None, f"the terrain tables could not be read ({exc})"
    if len(terrains) <= max(RAIL_BED, ROAD) or not rows or len(rows[0]) <= max(RAIL_BED, ROAD):
        return None, f"there is no terrain {RAIL_BED}"
    t = terrains[RAIL_BED]
    if not t.enabled or t.slp > 0 or t.to_draw != GRASS or terrains[GRASS].slp <= 0:
        return None, f"terrain {RAIL_BED} ({t.name!r}) is not the old grass drawn as the Grass"
    if [r[RAIL_BED] > 0 for r in rows] != [r[GRASS] > 0 for r in rows]:
        return None, f"terrain {RAIL_BED} ({t.name!r}) does not let the same units through as the Grass"
    return t, ""


def train_row(data: bytes, civs) -> Optional[int]:
    """The first row of the terrain restriction table that no unit uses and that lets no unit anywhere."""
    used = {u.values["terrain_restriction"] for units in civs.units for u in units if u is not None}
    rows = datfile.restrictions(data)
    return next((k for k, row in enumerate(rows) if k not in used and not any(v > 0 for v in row)), None)


def _row_at(data: bytes, row: int) -> int:
    """Offset of a restriction row's numbers (after them: its pass graphics, 16 bytes per terrain)."""
    rows, terrains = struct.unpack_from("<HH", data, 8)
    return 12 + 8 * rows + row * terrains * 20


def patch(data: bytearray, civs, graphics: dict, slp_id: int, colour: int,
          icon: Optional[int] = None) -> tuple[bool, str, Optional[dict[str, dict[str, int]]]]:
    """The rails and the trains (in place): terrain 16 becomes gravel drawn from SLP `slp_id`, `colour` on the
    minimap; the Sea Wall becomes the rail (with icon `icon`, if given) and the Trade Cart a train that only goes on
    the gravel. Returns (done, what happened, the text ids of the rail and the train)."""
    bed, why = rail_bed(bytes(data))
    if bed is None:
        return False, f"Rails: not added, {why}", None
    row = train_row(bytes(data), civs)
    if row is None:
        return False, "Rails: not added, the terrain restriction table has no empty row for the trains", None
    rails, trains = [], []
    for units in civs.units:
        if len(units) <= max(RAIL, *TRAINS):
            continue
        u = units[RAIL]
        stand = graphics.get(u.values["standing"][0]) if u is not None else None
        if (u is None or u.type != 80 or u.values["class"] != WALL or u.values["train_location"] != -1
                or stand is None or not stand.name.upper().startswith(RAIL_NAME)):
            continue  # not the leftover this build knows
        carts, wall = [units[k] for k in TRAINS], units[PALISADE]
        if any(c is None or c.type != 70 or c.values["class"] != TRADE_CART for c in carts):
            continue
        if wall is None or wall.type != 80 or wall.values["class"] != WALL:
            continue
        rails.append((u, wall.values["terrain_restriction"]))
        trains += carts
    if not rails:
        return False, f"Rails: not added, unit {RAIL} is not the unused Sea Wall here", None
    road = datfile.terrains_in(bytes(data))[ROAD]
    struct.pack_into("<i", data, bed.at + datfile.TERRAIN_SLP, slp_id)
    struct.pack_into("<ii", data, bed.at + datfile.TERRAIN_BLEND,  # blended into its neighbours as the Road is
                     *struct.unpack_from("<ii", data, road.at + datfile.TERRAIN_BLEND))
    struct.pack_into("<BBB", data, bed.at + datfile.TERRAIN_COLOURS, colour, colour, colour)
    struct.pack_into("<h", data, bed.at + datfile.TERRAIN_TO_DRAW, -1)  # its own texture, not the Grass's
    terrains = struct.unpack_from("<H", data, 10)[0]
    at = _row_at(bytes(data), row)
    struct.pack_into("<f", data, at + 4 * RAIL_BED, 1.0)  # the trains' row: the gravel, nothing else
    struct.pack_into("<iiii", data, at + 4 * terrains + 16 * RAIL_BED, *NO_PASS)
    for u, land in rails:
        DU.patch(data, u, enabled=1, train_location=VILLAGER, button=RAIL_BUTTON, cost=RAIL_COST,
                 terrain_restriction=land,  # on land, as a Palisade Wall (as the Sea Wall, it was water only)
                 obstruction=(0, OVER, u.values["obstruction"][2]), foundation_terrain=RAIL_BED,
                 collision_size=(*u.values["collision_size"][:2], 0.0),
                 outline_size=(*u.values["outline_size"][:2], 0.0))
        if icon is not None:
            DU.patch(data, u, icon=icon)
    for u in trains:
        DU.patch(data, u, terrain_restriction=row)
    strings = {}
    for key, u in (("rail", rails[0][0]), ("train", trains[0])):
        strings[key] = {"name": u.values["name_id"], "creation": u.values["creation_id"]}
        if u.values["help_id"] > HELP_STRINGS:
            strings[key]["help"] = u.values["help_id"] - HELP_STRINGS
    return True, (f"Rails: unit {RAIL} ({rails[0][0].name}) is the rail for {len(rails)} civilisations, built by "
                  f"Villagers (button {RAIL_BUTTON}) for 1 wood and 1 gold on land (terrain restriction {rails[0][1]}, "
                  f"the Palisade Wall's), leaving terrain {RAIL_BED} ({bed.name!r}) "
                  f"under it: gravel, its texture SLP {slp_id}, minimap colour {colour}"
                  + (f", icon {icon}" if icon is not None else "")
                  + f"; the trains (units {', '.join(map(str, TRAINS))}) may only go on it (terrain restriction "
                    f"{row})"), strings

