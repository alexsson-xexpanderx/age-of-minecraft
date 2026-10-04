"""Lava, and Team Lava Islands: Team Islands on a sea of lava.

The game has no lava. Its terrain 15, "Old Water", is a leftover no map uses: it has no texture of its own (the game
draws it with the Water's, `to_draw` 1), and every unit treats it exactly as it treats Water 3, the medium water:
ships sail on it, fish and fish traps live in it, soldiers cannot walk on it. So it becomes the lava (`patch`):

- its own texture, dark lava: plates of dark red crust with glowing cracks between them, orange round a yellow-hot
  middle, 2 blocks to a tile like the farms, cut into the tile shapes of the Water's texture, which it was drawn with
  (`encode`). The palette's plain colours have no red (they turn dark lava brown), so the red player's shades and the
  yellow player's are used as plain colours too (`SHADES`), as the giant red Pac-Man's are: a plain pixel there keeps
  its colour, and terrain has no owner anyway;
- orange on the minimap, and blended into the ground around it the way the Water is;
- Docks may be built on it. A Dock may only stand on Water or Shallows (its placement terrains) next to a beach,
  so its Shallows becomes the lava: no standard map has a Dock in shallow water (the fords are a tile wide).

The map (`script`, in `MAP_FILE`) is written from scratch in the random map script language, close to the game's
Team Islands: each team's players share an island (their lands joined by `create_connect_teams_lands`), on a map
that is all lava. The islands start as sand and are filled with ground all but one tile at the lava (as the game's
own Moats map fills its land), so every island has a beach to build Docks on. Nothing lives in lava: no fish, and
more berries, deer, boar and sheep on the islands instead. It goes into the mod's Script.RM folder, where the game
lists it under the custom maps (with `--mode direct` into the game's Random folder, which `--restore` empties of it).
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
from .palette import Quantiser
from .render import Frame, fit_camera, render
from .textures import parse

LAVA = 15  # "Old Water"
MEDIUM_WATER = 23  # the terrain it must behave like
WATER, SHALLOWS = 1, 4  # where a Dock may stand: (Water, Shallows) becomes (Water, lava)
COLOURS = ("#410000", "#5a0800", "#690b00", "#a01500", "#d06010", "#ffc700")  # the crust, then a crack's glow
SHADES = tuple(range(32, 40)) + tuple(range(64, 72))  # the red and the yellow player's colours, as plain colours
MINIMAP = (226, 98, 14)
MAP_NAME = "Team Lava Islands"
MAP_FILE = MAP_NAME + ".rms"
MARK = "Age of Minecraft"  # in the map's first lines: --restore removes only a map that has it


# --------------------------------------------------------------------------- the look

def lava_texture(seed: str = "lava", plates: int = 5) -> np.ndarray:
    """16x16 lava: a plate of dark crust round each of a few points, cracked where plates meet, the cracks glowing red
    to yellow-hot. The distances wrap round the block's edges, so the blocks join up."""
    rng = np.random.default_rng(zlib.crc32(seed.encode()))
    points = rng.uniform(0, 16, (plates, 2))
    yy, xx = np.mgrid[0:16, 0:16] + 0.5
    dist = []
    for py, px in points:
        dy, dx = np.abs(yy - py), np.abs(xx - px)
        dist.append(np.hypot(np.minimum(dy, 16 - dy), np.minimum(dx, 16 - dx)))
    near = np.sort(np.array(dist), axis=0)
    edge = near[1] - near[0]  # 0 where two plates meet
    heat = 1 - (edge / edge.max()) ** 0.6 + rng.normal(0, 0.06, edge.shape)  # 1 on the cracks
    return np.array([parse(c) for c in COLOURS])[np.digitize(heat, [0.35, 0.55, 0.7, 0.8, 0.9])]


@lru_cache(maxsize=None)
def texture(per_tile: int = farmland.PER_TILE) -> tuple[Frame, tuple[int, int]]:
    """A sea of lava blocks from the game's camera, and the screen position of the centre tile's centre."""
    n, reach = per_tile, 2
    s = V.Structure("lava", origin=(n / 2, n / 2))
    for x in range(-reach * n, (reach + 1) * n):
        for y in range(-reach * n, (reach + 1) * n):
            s.set(x, y, -1, "lava_sea")
    root = s.part({**V.all_blocks(), "lava_sea": BlockType.uniform(lava_texture())})
    cam = fit_camera(root, V.BUILDING_HEADING, scale=farmland.scale(per_tile), pad=2)
    frame = render(root, V.BUILDING_HEADING, camera=cam, shadow=False, outline=False)
    return frame, (int(cam.origin[0]), int(cam.origin[1]))


def encode(water: bytes, quant: Quantiser) -> bytes:
    """The lava's texture: the Water's SLP `water`, every tile redrawn as lava (in `quant`'s palette)."""
    reds = Quantiser(quant.palette, SHADES)
    return slp.encode(farmland.cut(*texture(), water, reds, "the lava"), props=slp.frame_props(water))


def ground(w: int, h: int, x0: int = 0, y0: int = 0) -> np.ndarray:
    """RGBA lava for a w x h picture whose corner is map pixel (x0, y0) (for previews): the texture repeats every
    tile (96 x 48 pixels), as the game lays it."""
    frame, (ox, oy) = texture()
    rgba = frame.to_rgba()
    yy, xx = np.mgrid[y0:y0 + h, x0:x0 + w].astype(float)
    i, j = (xx / 48 + yy / 24) / 2, (yy / 24 - xx / 48) / 2
    i, j = i - np.round(i), j - np.round(j)  # where in its tile the pixel is
    return rgba[(oy + (i + j) * 24).astype(int), (ox + (i - j) * 48).astype(int)]


# --------------------------------------------------------------------------- the .dat

def lava_terrain(data: bytes) -> tuple[Optional[datfile.Terrain], str]:
    """Terrain 15, if it is the unused old water this build knows: (terrain or None, why not)."""
    try:
        terrains, rows = datfile.terrains_in(data), datfile.restrictions(data)
    except (ValueError, IndexError) as exc:
        return None, f"the terrain tables could not be read ({exc})"
    if len(terrains) <= max(LAVA, MEDIUM_WATER) or not rows or len(rows[0]) <= max(LAVA, MEDIUM_WATER):
        return None, f"there is no terrain {LAVA}"
    t = terrains[LAVA]
    if not t.enabled or t.slp > 0 or t.to_draw != WATER or terrains[WATER].slp <= 0:
        return None, f"terrain {LAVA} ({t.name!r}) is not the old water drawn as the Water"
    if [r[LAVA] > 0 for r in rows] != [r[MEDIUM_WATER] > 0 for r in rows]:
        return None, f"terrain {LAVA} ({t.name!r}) does not let the same units through as terrain {MEDIUM_WATER}"
    return t, ""


def patch(data: bytearray, civs, slp_id: int, colour: int) -> tuple[bool, str]:
    """Terrain 15 becomes lava drawn from SLP `slp_id`, `colour` on the minimap, and Docks may stand on it (in
    place). Returns (done, what happened)."""
    t, why = lava_terrain(bytes(data))
    if t is None:
        return False, f"Lava: not added, {why}"
    water = datfile.terrains_in(bytes(data))[WATER]
    struct.pack_into("<i", data, t.at + datfile.TERRAIN_SLP, slp_id)
    struct.pack_into("<ii", data, t.at + datfile.TERRAIN_BLEND,  # blended into its neighbours as the Water is
                     *struct.unpack_from("<ii", data, water.at + datfile.TERRAIN_BLEND))
    struct.pack_into("<BBB", data, t.at + datfile.TERRAIN_COLOURS, colour, colour, colour)
    struct.pack_into("<h", data, t.at + datfile.TERRAIN_TO_DRAW, -1)  # its own texture, not the Water's
    docks = set()
    for units in civs.units:
        for u in units:
            if u is not None and u.type == 80 and u.values.get("placement_terrain") == (WATER, SHALLOWS):
                DU.patch(data, u, placement_terrain=(WATER, LAVA))
                docks.add(u.id)
    return True, (f"Lava: terrain {LAVA} ({t.name!r}) is lava, its texture SLP {slp_id}, minimap colour {colour}; "
                  f"Docks (units {', '.join(map(str, sorted(docks))) or 'none'}) may be built on it instead of in "
                  f"Shallows")


# --------------------------------------------------------------------------- the map

# the ground of each kind of map: the land, its forests, its patches
VARIANTS = (
    ("DESERT_MAP", "DIRT", ("PALM_DESERT", "FOREST"), ("DESERT", "DIRT3", "GRASS3"), "PALMTREE"),
    ("ALPINE_MAP", "GRASS2", ("PINE_FOREST", "FOREST"), ("GRASS3", "DIRT3", "GRASS"), "PINETREE"),
    ("FROZEN_MAP", "SNOW", ("SNOW_FOREST", "PINE_FOREST"), ("GRASS_SNOW", "DIRT_SNOW", "GRASS2"), "SNOWPINETREE"),
    (None, "GRASS", ("FOREST", "PALM_DESERT"), ("DIRT", "GRASS3", "DIRT3"), "OAKTREE"),
)


def _by_variant(write) -> list[str]:
    """`write(land, forests, patches, tree)` for each kind of map, in an if/elseif/else."""
    out = []
    for k, (define, land, forests, patches, tree) in enumerate(VARIANTS):
        out.append(("if " if k == 0 else "elseif " if define else "else") + (define or ""))
        out += write(land, forests, patches, tree)
    return out + ["endif"]


def _block(head: str, *lines: str) -> list[str]:
    return [head, "{", *(f"  {line}" for line in lines), "}"]


def script() -> str:
    """The map script (Windows line endings)."""
    out = [f"/* ************ {MAP_NAME.upper()} ************ */",
           f"/* {MARK}: Team Islands on a sea of lava. Each team shares an island; ships sail on the lava and",
           "   Docks stand on it, but nothing lives in it: no fish, more berries, deer, boar and sheep instead. */",
           "/* The lava is terrain 15, the game's unused \"Old Water\", which every unit treats as water. */",
           "",
           "#include_drs random_map.def 54000",
           f"#const LAVA {LAVA}",
           "",
           "<PLAYER_SETUP>",
           "  random_placement",
           "",
           "<LAND_GENERATION>",
           "base_terrain LAVA",
           "start_random",
           "  percent_chance 20",
           "  #define DESERT_MAP",
           "  percent_chance 20",
           "  #define ALPINE_MAP",
           "  percent_chance 20",
           "  #define FROZEN_MAP",
           "end_random",
           "/* the islands start as sand: the ground fills them later, all but a beach along the lava */",
           "create_player_lands",
           "{",
           "  terrain_type BEACH",
           "  land_percent 45",
           "  base_size 12",
           "  border_fuzziness 15"]
    for a, b in (("left_border", "right_border"), ("top_border", "bottom_border")):
        out += ["  start_random",
                "    percent_chance 50", f"    {a} 7", f"    {b} 9",
                "    percent_chance 50", f"    {a} 9", f"    {b} 7",
                "  end_random"]
    out += ["  set_zone_by_team",
            "  other_zone_avoidance_distance 22",
            "}",
            "",
            "<TERRAIN_GENERATION>",
            "/* the ground, leaving one tile of beach along the lava (Docks need one beside them) */"]
    out += _by_variant(lambda land, forests, patches, tree: _block(
        f"create_terrain {land}", "base_terrain BEACH", "number_of_clumps 64", "spacing_to_other_terrain_types 1",
        "land_percent 100"))
    out += ["/* forests */"]
    out += _by_variant(lambda land, forests, patches, tree: [
        *_block(f"create_terrain {forests[0]}", f"base_terrain {land}", "spacing_to_other_terrain_types 5",
                "land_percent 8", "number_of_clumps 8", "set_avoid_player_start_areas", "set_scale_by_groups"),
        *_block(f"create_terrain {forests[1]}", f"base_terrain {land}", "spacing_to_other_terrain_types 3",
                "land_percent 1", "number_of_clumps 3", "set_avoid_player_start_areas", "set_scale_by_groups")])
    out += ["/* patches of other ground */"]
    out += _by_variant(lambda land, forests, patches, tree: [
        line for k, (patch_, clumps, percent) in enumerate(zip(patches, (10, 24, 30), (6, 2, 2)))
        for line in _block(f"create_terrain {patch_}", f"base_terrain {land}", f"number_of_clumps {clumps}",
                           "spacing_to_other_terrain_types 1", f"land_percent {percent}", "set_scale_by_size")])
    out += ["",
            "<OBJECTS_GENERATION>",
            "/* the Town Center, villagers, scout, relics, berries, gold, stone, sheep, deer, boar and wolves */",
            "#include_drs land_and_water_resources.inc 54102",
            *_block("create_object DEER", "number_of_objects 6", "number_of_groups 2", "set_loose_grouping",
                    "set_gaia_object_only", "set_place_for_every_player", "min_distance_to_players 35",
                    "min_distance_group_placement 5"),
            *_block("create_object BOAR", "number_of_objects 2", "set_loose_grouping", "set_gaia_object_only",
                    "set_place_for_every_player", "min_distance_to_players 35", "min_distance_group_placement 5"),
            "/* instead of fish: more food on every island */",
            *_block("create_object FORAGE", "number_of_objects 5", "group_placement_radius 3", "set_tight_grouping",
                    "set_gaia_object_only", "set_place_for_every_player", "min_distance_to_players 18",
                    "max_distance_to_players 26", "min_distance_group_placement 6"),
            *_block("create_object DEER", "number_of_objects 4", "group_placement_radius 3", "set_loose_grouping",
                    "set_gaia_object_only", "set_place_for_every_player", "min_distance_to_players 18",
                    "max_distance_to_players 30", "min_distance_group_placement 5"),
            *_block("create_object BOAR", "number_of_objects 1", "set_gaia_object_only",
                    "set_place_for_every_player", "min_distance_to_players 20", "max_distance_to_players 28",
                    "min_distance_group_placement 5"),
            *_block("create_object SHEEP", "number_of_objects 4", "set_loose_grouping", "set_gaia_object_only",
                    "set_place_for_every_player", "min_distance_to_players 14", "max_distance_to_players 30",
                    "min_distance_group_placement 5"),
            "/* lone trees */"]
    out += _by_variant(lambda land, forests, patches, tree: _block(
        f"create_object {tree}", "number_of_objects 20", "set_gaia_object_only", "set_scaling_to_map_size",
        "min_distance_to_players 8"))
    out += ["",
            "<ELEVATION_GENERATION>",
            "/* hills come before the ground fills the islands: they are still sand */",
            *_block("create_elevation 7", "base_terrain BEACH", "number_of_clumps 14", "number_of_tiles 1200",
                    "set_scale_by_groups", "set_scale_by_size"),
            "",
            "<CLIFF_GENERATION>",
            "min_number_of_cliffs 3",
            "max_number_of_cliffs 5",
            "min_length_of_cliff 4",
            "max_length_of_cliff 8",
            "cliff_curliness 10",
            "min_distance_cliffs 3",
            "",
            "<CONNECTION_GENERATION>",
            "/* a team's lands become one island: ground across the lava between them, roads across the ground */"]
    lands = ("GRASS", "GRASS2", "GRASS3", "GRASS_SNOW", "DIRT_SNOW", "SNOW", "DESERT", "DIRT", "DIRT2", "DIRT3")
    forests = ("FOREST", "PALM_DESERT", "PINE_FOREST", "SNOW_FOREST")
    out += _block("create_connect_teams_lands",
                  "replace_terrain LAVA GRASS", "replace_terrain BEACH GRASS",
                  *(f"replace_terrain {t} ROAD2" for t in lands + forests),
                  "terrain_cost LAVA 5", "terrain_cost BEACH 4", "terrain_cost ROAD2 1",
                  *(f"terrain_cost {t} {7 if t in forests else 5 if t.startswith(('DIRT', 'DESERT')) else 2}"
                    for t in lands + forests),
                  "terrain_size LAVA 6 1", "terrain_size BEACH 1 0", "terrain_size ROAD2 0 0",
                  *(f"terrain_size {t} {3 if t in forests else 0 if t.startswith(('DIRT', 'DESERT')) else 1} "
                    f"{1 if t in forests else 0}" for t in lands + forests))
    return "\r\n".join(out) + "\r\n"
