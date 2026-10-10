"""Volcanoes on the lava: Villagers build one on the lava sea (terrain 15, lava.py) by their island's beach, and it
erupts at the enemies that come within its range, raining lava bombs on ships, units and buildings.

The game has a tower made for the sea that it never lets anyone build: the Sea Tower (unit 785). It is still a tower
(unit class 52), so the tower upgrades reach it: Fletching, Bodkin Arrow and Bracer, Masonry and Architecture, and
Heated Shot against ships. `patch` makes it the volcano, in place, for every civilisation:

- Villagers build it (`BUTTON` on their military build page), from the start of the game, on the lava by a beach: it takes
  the Dock's rules (the beach next to it, the ground it may cover, how level), with the tile under its middle on the
  lava (its placement terrain, the rule that keeps a Dock on water). Fishing Ships cannot build it: the game lets a
  Fishing Ship build the Fish Trap alone (it checks for the Fish Trap's unit, 004b9b8f among others), and a test
  game with three more test volcanoes for Fishing Ships, on the Dock's rules, the Fish Trap's and its own, placed
  none of them.
- It is three tiles across, as big as a Barracks, built on the Barracks' building site, and it sinks like a Dock when
  destroyed.
- It shoots its own shots (786, and 787: the game left both unused, the Sea Tower shot the towers' arrow), which
  become lava bombs, lobbed high (`ARC`) from its crater: piercing damage for everything, more against ships and
  buildings (`ATTACK`).
- It has three pictures of its own, new SLPs written next to the others: the volcano at rest (its own graphic,
  STWR1NN), the eruption it plays each time it fires (787's graphic, MFSTW, made one picture of `ERUPTION_FRAMES`:
  its attack graphic, with the Trebuchet's firing boom), and the lava bomb (786's graphic, MRSTW, a tumbling glowing
  rock of `BOMB_FRAMES`). Both shot graphics drew the old arrows in 32 directions; a volcano and a ball of rock look
  the same from every side, so they become one direction.
- Its icon is added at the end of the four building icon sheets (one per age), and its texts name it the Volcano.
"""
from __future__ import annotations

import math
import struct
import zlib
from typing import Optional

import numpy as np

from . import datfile, slp
from . import datunits as DU
from . import voxel as V
from .geometry import Part, cuboid
from .units import Unit

SEA_TOWER = 785
SHOTS = (786, 787)  # the Sea Tower's own shots, which nothing shoots (it shot the towers' arrow): both lava bombs
LOOK = "STWR"  # the Sea Tower's graphics' names
VILLAGER = 118  # where buildings say Villagers build them
DOCK = "DOCK"  # the Dock's unit name: the volcano takes its placement rules
# in a Villager's build menu, on the page its interface kind picks (10, a tower's: the military buildings; 2 is
# the economic ones), where 5 is free: the Siege Workshop has 4, the Outpost 6 (a 14th button did not show)
BUTTON = 5
LAVA = 15  # the terrain (lava.LAVA)
COST = (2, 150, 1, 3, 100, 1, -1, 0, 0)  # 150 stone, 100 gold
TIME = 60  # seconds to build
HP = 1500
# (class, amount): pierce for everything, extra against ships (armour class 16) and buildings (11)
ATTACK = [(3, 12), (16, 18), (11, 15)]
ARMOUR = {4: 3, 3: 10}  # melee, pierce: its other armour classes (as a building and a tower) stay
RANGE = 8.0  # tiles, a tower's
SIGHT = 10.0
RELOAD = 3.0  # seconds between eruptions
ARC = 0.6  # how high the bombs lob: a tower's arrow 0.05, a Mangonel's stone 0.4
SIZE = 1.5  # tiles from its centre to its edge: three tiles across
FRAME = 4  # the eruption's picture its bomb leaves on
ERUPTION_FRAMES = 12
ERUPTION_SECONDS = 0.1  # a picture: the eruption plays 1.2 s of its 3 s reload
BOMB_FRAMES = 8
BOMB_SECONDS = 0.08
BUILDING_LAYER, SHOT_LAYER = 20, 30
SITE, SINKING = "CNST3_NN", "DEXP3_NN"  # the Barracks' building site; the Dock's going down
BOOM = "trebfire.wav"  # the Trebuchet's firing boom, on each eruption
BUILDING_ICONS = (50705, 50706, 50707, 50708)  # in interfac.drs: one sheet per age
HELP_STRINGS = 79000  # as gameplay.HELP_STRINGS
TEXTS = {"name": "Volcano", "creation": "Build Volcano",
         "help": "Build <b> Volcano<b> (<cost>) \nA volcano on the lava, by your island's beach. It erupts at "
                 "enemies within range, raining lava bombs on ships, units and buildings. Build it on lava next to "
                 "a beach, like a Dock. \n<hp> <attack> <armor> <piercearmor> <range>"}
SHORT_HELP = "Build <b> Volcano<b> (<cost>) \nErupts at enemies, raining lava bombs on them."

# the volcano's model, in blocks: a cone of dark rock on an 8x8 footprint (three tiles), steeper towards its peak,
# with a small crater of lava
HEIGHT = 10
RADIUS = 4.7
STEEP = 1.6  # how much steeper the cone gets towards its peak
CRATER = 1.15
POOL = round(HEIGHT * (1 - 0.45 / (RADIUS - CRATER)) ** STEEP) - 1  # the crater's lava: a block below its rim
ROCK = ("blackstone", "blackstone", "cobbled_deepslate", "blackstone", "deepslate_tiles")
RIM = "nether_bricks"


# --------------------------------------------------------------------------- the look

def _rock(x: int, y: int, z: int) -> str:
    return ROCK[zlib.crc32(f"volcano {x} {y} {z}".encode()) % len(ROCK)]


def _streams(x: int, y: int) -> bool:
    """The lava running down from the crater: two streams, down the two sides facing the camera."""
    return (x >= 4 and y == 4) or (y >= 5 and x == 3)


def volcano(t: Optional[float] = None) -> V.Structure:
    """The volcano: a cone of dark rock with a pool of lava in its crater, lava running down the two sides facing the
    camera, a thin smoke plume and a team flag on its front slope. With `t` (0..1), erupting: a fountain of lava
    thrown up out of the crater, highest as the bomb leaves (`FRAME`), and a dark cloud billowing over it."""
    s = V.Structure("volcano", origin=(4.0, 4.0))
    c = 4.0  # its peak, over the footprint's centre
    tops = {}
    for x in range(-1, 9):
        for y in range(-1, 9):
            d = math.hypot(x + 0.5 - c, y + 0.5 - c)
            if CRATER < d <= RADIUS:  # highest at the crater's rim
                tops[(x, y)] = int(round(HEIGHT * (1 - (d - CRATER) / (RADIUS - CRATER)) ** STEEP))
    pool = POOL
    for x in range(-1, 9):
        for y in range(-1, 9):
            if math.hypot(x + 0.5 - c, y + 0.5 - c) <= CRATER:  # the crater a block below its rim
                tops[(x, y)] = pool
    for (x, y), top in tops.items():
        d = math.hypot(x + 0.5 - c, y + 0.5 - c)
        for z in range(top + 1):
            s.set(x, y, z, _rock(x, y, z))
        if d <= CRATER:
            s.set(x, y, top, "lava")
        elif d <= CRATER + 1.0 and not _streams(x, y):
            s.set(x, y, top, RIM)
        elif _streams(x, y):  # down the step below it too, so a stream runs on unbroken
            below = min((tops.get((x + dx, y + dy), -1) for dx, dy in ((1, 0), (0, 1))), default=-1)
            s.fill(x, y, max(0, below + 1), x, y, top, "lava")
    ox, oy = s.origin
    B = V.BLOCK
    rng = np.random.default_rng(zlib.crc32(b"volcano smoke"))
    erupting = t is not None
    for k in range(4):  # the smoke
        size = (14 + k * 6) if erupting else (6 + k * 2.5)
        grey = (0.28 if erupting else 0.62) + 0.05 * k
        col = f"#{int(grey * 255):02x}{int(grey * 250):02x}{int(grey * 245):02x}"
        drift = (rng.uniform(-3, 3), rng.uniform(-3, 3))
        s.extras.append(cuboid(((c - ox) * B + drift[0] + k * 3 - size / 2, (c - oy) * B + drift[1] - k * 2 - size / 2,
                                (HEIGHT + 1) * B + k * (16 if erupting else 9) + (40 if erupting else 0)),
                               (size, size, size * 0.8), V.solid(col)))
    if erupting:
        s.extras += eruption(t, ((c - ox) * B, (c - oy) * B, (POOL + 1) * B))
    from .structures import flag
    flag(s, 6.3, 6.3, tops[(6, 6)] + 1, height=24, seed="volcano")
    return s


def eruption(t: float, at: tuple[float, float, float]) -> list:
    """A fountain of lava thrown up out of the crater at `at` (pixels), a moment `t` (0..1) of an eruption: blobs
    flying up and out and falling back, bursting highest as the bomb leaves, and dark rocks flung out with them."""
    x0, y0, z0 = at
    rng = np.random.default_rng(zlib.crc32(b"volcano eruption"))
    peak = (FRAME + 0.5) / ERUPTION_FRAMES
    burst = math.exp(-((t - peak) / 0.22) ** 2)  # 1 as the bomb leaves, low at the start and the end
    out = [cuboid((x0 - 9, y0 - 9, z0 + 6), (18, 18, 4 + 20 * burst), V.solid("#ffb21e"))]  # the jet's base
    for k in range(48):
        phase = (t * 1.5 + k / 48) % 1
        angle = rng.uniform(0, 2 * math.pi)
        reach = rng.uniform(6, 34)
        rise = rng.uniform(60, 150) * (0.35 + 0.65 * burst)
        z = z0 + 10 + 4 * rise * phase * (1 - phase)
        r = reach * phase
        size = rng.uniform(4, 9) * (1.15 - 0.55 * phase)
        dark = k % 7 == 0  # a rock flung out with the lava
        colour = "#3a302c" if dark else ("#ffe066", "#ffb21e", "#ff7a10", "#d8400c")[min(3, int(phase * 4))]
        out.append(cuboid((x0 + r * math.cos(angle) - size / 2, y0 + r * math.sin(angle) - size / 2, z),
                          (size, size, size), V.solid(colour)))
    return out


def bomb() -> Unit:
    """A lava bomb: a ball of dark rock cracked through with glowing lava, sparks trailing off it, tumbling as the
    fireball does (animation rig "fireball")."""
    rng = np.random.default_rng(zlib.crc32(b"lava bomb"))
    colours = ["#2b2420"] * 6 + ["#4a3a32"] * 2 + ["#ff7a10"] * 7 + ["#ffd24a"] * 3 + ["#c8380c"] * 2
    ball = []
    r = 5.4  # bigger than the dragon's fireball: it must show from afar
    for x in range(-6, 6):
        for y in range(-6, 6):
            for z in range(-6, 6):
                if (x + 0.5) ** 2 + (y + 0.5) ** 2 + (z + 0.5) ** 2 <= r * r:
                    ball.append(cuboid((x, y, z), (1, 1, 1), V.solid(colours[int(rng.integers(len(colours)))])))
    sparks = [cuboid((x, y, z), (1.5, 1.5, 1.5), V.solid(col)) for x, y, z, col in (
        (5.5, 1, 1, "#ffb21e"), (-7, -1, 0, "#ff6a10"), (0, 5.5, -4, "#ffd24a"), (-1, -7, 3, "#ff6a10"))]
    root = Part("root").add(Part("ball", boxes=ball), Part("flame_a", boxes=sparks[:2]),
                            Part("flame_b", boxes=sparks[2:]))
    return Unit("lava_bomb", "Lava bomb", "the volcano's shot", "fireball", root, group="easter", attack="none")


def _building_frames(models: list, quant) -> list[slp.SlpFrame]:
    """Pictures of building models from the building view, all through one camera (so they line up), each with the
    footprint's centre on its hotspot."""
    from .export import _crop
    from .render import fit_camera, render
    parts = [m.part(V.all_blocks()) for m in models]
    whole = Part("all", children=parts)
    cam = fit_camera(whole, V.BUILDING_HEADING, pad=6)
    return [_crop(quant.frame_codes(render(p, V.BUILDING_HEADING, camera=cam), obstruction=False), cam.origin)
            for p in parts]


_SLPS: dict[tuple, bytes] = {}


def volcano_slp(quant) -> bytes:
    """The volcano at rest: one picture."""
    key = ("rest", np.asarray(quant.palette).tobytes())
    if key not in _SLPS:
        _SLPS[key] = slp.encode(_building_frames([volcano()], quant))
    return _SLPS[key]


def eruption_slp(quant, frames: int = ERUPTION_FRAMES) -> bytes:
    """The eruption: `frames` pictures of the volcano throwing up lava, one direction."""
    key = ("erupt", np.asarray(quant.palette).tobytes(), frames)
    if key not in _SLPS:
        _SLPS[key] = slp.encode(_building_frames([volcano(k / frames) for k in range(frames)], quant))
    return _SLPS[key]


def bomb_slp(quant, frames: int = BOMB_FRAMES) -> bytes:
    """The lava bomb: `frames` pictures of it tumbling, one direction, no shadow (it is in the air)."""
    key = ("bomb", np.asarray(quant.palette).tobytes(), frames)
    if key not in _SLPS:
        from .export import render_frames
        _SLPS[key] = slp.encode(render_frames(bomb(), "idle", frames, 1, False, quant, shadow=False))
    return _SLPS[key]


def crater() -> tuple[float, float, float]:
    """Where its bombs leave it (tiles across, forward and up): its crater."""
    from .export import BASE_SCALE
    from .gameplay import HEIGHT_PIXELS
    return 0.0, 0.0, round((POOL + 1) * V.BLOCK * math.cos(math.radians(30)) * BASE_SCALE / HEIGHT_PIXELS, 2)


# --------------------------------------------------------------------------- its icon

ICON_COLOURS = {0: (24, 22, 30), 1: (62, 56, 58), 2: (38, 34, 36), 3: (255, 122, 16), 4: (255, 214, 74),
                5: (200, 56, 12), 6: (120, 116, 120), 7: (170, 166, 168)}


def icon(size: int = 36) -> np.ndarray:
    """A building icon (drawn at 36x36, scaled to `size`): the volcano erupting against a night sky, lava running
    down it into a sea of lava. Colours are keys of ICON_COLOURS."""
    sky, rock, dark, lava, glow, red, smoke, light = range(8)
    px = np.full((36, 36), sky, np.int16)
    for y in range(36):  # the cone
        half = max(0, (y - 11) * 0.62)
        x0, x1 = int(round(18 - half)), int(round(18 + half))
        if y >= 11:
            px[y, max(0, x0):min(36, x1 + 1)] = rock
            px[y, max(0, x0):min(36, x0 + 3)] = dark
    px[30:36, :] = lava  # the lava sea
    px[33:36:2, 2:36:5] = glow
    px[11:14, 14:23] = lava  # the crater
    for y in range(13, 31):  # lava running down
        px[y, 18 + (y - 13) // 3] = lava
        px[y, 17 - (y - 13) // 5] = red
    for y, x in ((8, 18), (6, 15), (5, 21), (3, 17), (7, 23), (9, 12), (4, 25)):  # thrown up
        px[y:y + 2, x:x + 2] = glow if (x + y) % 2 else lava
    px[0:4, 6:13] = smoke
    px[1:5, 22:31] = smoke
    px[1:3, 8:11] = light
    if size != 36:
        idx = np.arange(size) * 36 // size
        px = px[idx][:, idx]
    return px


def add_icon(data: bytes, index: int, quant) -> tuple[Optional[bytes], str]:
    """A building icon sheet with the volcano's icon added as icon `index` (blank icons fill any gap before it)."""
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
    px = np.vectorize(lut.get)(icon(min(w, h))).astype(np.int16)
    if (w, h) != px.shape[::-1]:  # not square: centred on the sky
        full = np.full((h, w), lut[0], np.int16)
        y0, x0 = (h - px.shape[0]) // 2, (w - px.shape[1]) // 2
        full[y0:y0 + px.shape[0], x0:x0 + px.shape[1]] = px
        px = full
    blank = slp.SlpFrame(np.full((1, 1), slp.TRANSPARENT, np.int16), (0, 0))
    frames = [blank] * (index - info.num_frames) + [slp.SlpFrame(px, (0, 0))]
    return slp.append_frames(data, frames), f"the volcano is icon {index} ({w}x{h})"


def icon_sheets(archives: list[tuple[str, object]]) -> list[tuple[str, object, int, bytes]]:
    """Every copy of the building icon sheets, in load order: (archive name, archive, sheet id, sheet)."""
    return [(name, drs, sid, drs.get(sid)) for name, drs in archives if drs is not None
            for sid in BUILDING_ICONS if sid in drs.ids()]


# --------------------------------------------------------------------------- the .dat

def dock(civs):
    """The Dock (as the game calls it: its unit name), whose placement rules the volcano takes."""
    return next((u for units in civs.units for u in units if u is not None and u.type == 80 and u.name == DOCK
                 and u.values["placement_side"][0] >= 0), None)


def _own_graphic(graphics: dict, civs, gid: int, owners: set[int]) -> bool:
    """True if graphic `gid` is drawn by the `owners` units alone, from an SLP of its own, with no per-angle sounds
    (so its angle count may change)."""
    g = graphics.get(gid)
    if g is None or g.slp <= 0 or g.slp_at < 0 or g.angle_sounds_at >= 0:
        return False
    if sum(1 for o in graphics.values() if o.slp == g.slp) != 1 or any(
            d.graphic_id == gid for o in graphics.values() for d in o.deltas):
        return False
    for units in civs.units:
        for u in units:
            if u is None or u.id in owners:
                continue
            looks = {*u.values.get("standing", ()), *u.values.get("dying", ()), *u.values.get("walking", ()),
                     *u.values.get("damage_graphics", ()), u.values.get("attack_graphic", -1)}
            if gid in looks:
                return False
    return True


def _redraw(data: bytearray, g, slp_id: int, frames: int, seconds: float, layer: int, sound: int) -> None:
    """Graphic `g` draws SLP `slp_id`, in one direction, and nothing else with it: its old extra layers (the Sea
    Tower's shadow, the arrows' shadow on the ground) become the picture itself (delta -1); the new pictures have
    their own shadows."""
    for k, d in enumerate(g.deltas):
        if d.graphic_id != -1:
            struct.pack_into("<h", data, g.delta_at(k), -1)
    struct.pack_into("<i", data, g.slp_at, slp_id)
    struct.pack_into("<b", data, g.layer_at, layer)
    struct.pack_into("<HH", data, g.frames_at, frames, 1)  # one direction
    struct.pack_into("<f", data, g.frame_rate_at, seconds)
    struct.pack_into("<b", data, g.mirroring_at, 0)
    struct.pack_into("<h", data, g.sound_at, sound)


def patch(data: bytearray, civs, graphics: dict, slps: tuple[int, int, int],
          icon_index: Optional[int] = None) -> tuple[Optional[dict], str, Optional[dict[str, int]]]:
    """The Sea Tower becomes the volcano (in place), drawn from SLPs `slps` (at rest, erupting, its bomb), with icon
    `icon_index` if given. Returns (what changed: its row and graphics, or None; what happened; its text ids)."""
    first = next((units[SEA_TOWER] for units in civs.units if len(units) > max(SEA_TOWER, *SHOTS)
                  and units[SEA_TOWER] is not None), None)
    stand = graphics.get(first.values["standing"][0]) if first is not None else None
    if first is None or first.type != 80 or stand is None or not stand.name.upper().startswith(LOOK):
        return None, f"Volcano: not changed, unit {SEA_TOWER} is not the Sea Tower here", None
    harbour = dock(civs)
    if harbour is None:
        return None, "Volcano: not changed, there is no Dock to take the placement rules of", None
    row, side, hill = (harbour.values[k] for k in ("terrain_restriction", "placement_side", "hill_mode"))
    shots = [units[s] for units in civs.units if len(units) > max(SHOTS) for s in SHOTS if units[s] is not None]
    if not shots or any(s.type != 60 for s in shots):
        return None, f"Volcano: not changed, units {SHOTS[0]} and {SHOTS[1]} are not the Sea Tower's shots here", None
    rest = first.values["standing"][0]
    erupt, flight = (next(s for s in shots if s.id == k).values["standing"][0] for k in reversed(SHOTS))
    owners = {SEA_TOWER, *SHOTS}
    if len({rest, erupt, flight}) != 3 or not all(_own_graphic(graphics, civs, g, owners) for g in (rest, erupt, flight)):
        return None, "Volcano: not changed, the Sea Tower's pictures are not its own here", None
    try:
        sounds = datfile.sound_files(bytes(data))
    except (ValueError, struct.error):
        sounds = {}
    boom = next((sid for sid, files in sounds.items() if BOOM in (f.lower() for f in files)), -1)
    by_name = {g.name.upper(): gid for gid, g in graphics.items()}
    site, sinking = by_name.get(SITE), by_name.get(SINKING)
    patched = 0
    for units in civs.units:
        if len(units) <= max(SEA_TOWER, *SHOTS) or units[SEA_TOWER] is None or units[SEA_TOWER].type != 80:
            continue
        u = units[SEA_TOWER]
        armours = [(c, ARMOUR.get(c, a)) for c, a in u.values["armours"]]
        attacks = ATTACK if len(u.values["attacks"]) == len(ATTACK) else None
        DU.patch(data, u, enabled=1, train_location=VILLAGER, button=BUTTON, cost=COST, train_time=TIME,
                 hit_points=HP, terrain_restriction=row, placement_side=side, hill_mode=hill,
                 projectile=SHOTS[0], placement_terrain=(LAVA, LAVA), armours=armours,
                 max_range=RANGE, line_of_sight=SIGHT, reload=RELOAD, attack_graphic=erupt, frame_delay=FRAME,
                 displacement=crater(), collision_size=(SIZE, SIZE, u.values["collision_size"][2]),
                 outline_size=(SIZE, SIZE, u.values["outline_size"][2]), clearance_size=(SIZE, SIZE),
                 displayed=(ARMOUR[4], ATTACK[0][1], RANGE, RELOAD), displayed_pierce=ARMOUR[3])
        if attacks:
            DU.patch(data, u, attacks=attacks)
        if site is not None:
            DU.patch(data, u, construction_graphic=site)
        if sinking is not None:
            DU.patch(data, u, dying=(sinking, -1))
        if icon_index is not None:
            DU.patch(data, u, icon=icon_index)
        for s in (units[k] for k in SHOTS):
            if s is not None and s.type == 60:
                DU.patch(data, s, standing=(flight, -1), walking=(flight, -1), projectile_arc=ARC)
        patched += 1
    _redraw(data, graphics[rest], slps[0], 1, 0.0, BUILDING_LAYER, -1)
    _redraw(data, graphics[erupt], slps[1], ERUPTION_FRAMES, ERUPTION_SECONDS, BUILDING_LAYER, boom)
    _redraw(data, graphics[flight], slps[2], BOMB_FRAMES, BOMB_SECONDS, SHOT_LAYER, -1)
    strings = {"name": first.values["name_id"], "creation": first.values["creation_id"]}
    if first.values["help_id"] > HELP_STRINGS:
        strings["help"] = first.values["help_id"] - HELP_STRINGS
    done = {"row": row, "rest": rest, "erupt": erupt, "flight": flight}
    return done, (f"Volcano: the Sea Tower (unit {SEA_TOWER}) for {patched} civilisations, built by Villagers "
                  f"(button {BUTTON}) on the lava by a beach, on the Dock's rules (unit {harbour.id}: beside terrains "
                  f"{side[0]}, {side[1]}, terrain restriction {row}, hill mode {hill}) with lava (terrain {LAVA}) "
                  f"under its middle: "
                  f"{COST[1]} stone, {COST[4]} gold, {TIME} s, {HP} hit points, 3x3 tiles, lava bombs "
                  f"{'/'.join(str(a) for _, a in ATTACK)} (pierce/ships/buildings) at range {RANGE:g} every "
                  f"{RELOAD:g} s" + (f", icon {icon_index}" if icon_index is not None else "")
                  + f"; at rest SLP {slps[0]} (graphic {rest}), erupting SLP {slps[1]} (graphic {erupt}, "
                    f"{ERUPTION_FRAMES} pictures" + (f", sound {boom}" if boom >= 0 else "") + f"), its bombs "
                    f"(units {SHOTS[0]}, {SHOTS[1]}) SLP {slps[2]} (graphic {flight})"), strings

