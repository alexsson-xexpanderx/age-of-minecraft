"""Gameplay changes in the .dat: Pac-Man can be trained at the Wonder.

The easter egg lives in Furious the Monkey Boy's slot (unit 860), so the
chat cheat still spawns him. Here every civilisation also gets him enabled,
trained at the Wonder (unit 276), which exists only once a Wonder stands.
The unit icon (frame 159 of the unit icon sheet in interfac.drs) becomes
Pac-Man too.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import datunits as DU
from . import slp

PACMAN_UNIT = 860
WONDER_UNIT = 276
PACMAN_COST = (0, 200, 1, 3, 100, 1, 4, 1, 0)  # 200 food, 100 gold, 1 population
PACMAN_TIME = 30  # seconds
PACMAN_BUTTON = 1
PACMAN_HP = 250  # the Monkey Boy has 50; a unit from a Wonder should last a bit longer
UNIT_ICONS = 50730  # the unit icon sheet in interfac.drs
PACMAN_ICON = 159  # the Monkey Boy's icon in that sheet


@dataclass
class DatPatch:
    data: bytes  # the recompressed .dat
    civs: int  # civilisations patched
    notes: list[str]


def wonder_pacman(raw: bytes, graphics: dict) -> tuple[Optional[DatPatch], str]:
    """Make Pac-Man trainable at the Wonder. Returns (patch or None, what happened)."""
    patch, notes = patch_dat(raw, graphics, pacman=True, javelina=False)
    return patch, notes[0]


def patch_dat(raw: bytes, graphics: dict, pacman: bool = True, javelina: bool = True
              ) -> tuple[Optional[DatPatch], list[str]]:
    """All .dat changes: Pac-Man at the Wonder, and the Javelina's own sprites. Returns (patch, notes)."""
    try:
        data = bytearray(DU.decompress(raw))
        civs = DU.read_units(bytes(data))
    except Exception as exc:  # a .dat we cannot read exactly is left alone
        return None, [f"not changed: could not read the unit tables ({exc})"]
    notes, changed, pac_done = [], False, False
    if pacman:
        msg = _pacman(data, civs, graphics)
        pac_done = msg.startswith("Pac-Man (unit")
        changed |= pac_done
        notes.append(msg)
    if javelina:
        msg = _javelina(data, civs, graphics)
        changed |= msg.startswith("Javelina: its own")
        notes.append(msg)
    if not changed:
        return None, notes
    check = DU.read_units(bytes(data))  # read everything back: same layout, new values
    for units in check.units:
        pac = units[PACMAN_UNIT] if len(units) > PACMAN_UNIT else None
        if pac_done and pac is not None and pac.type >= 70 and pac.values["train_location"] != WONDER_UNIT:
            return None, notes + ["not changed: the patched file did not read back as expected"]
    return DatPatch(DU.compress(bytes(data)), len(civs.units), notes), notes


def _pacman(data: bytearray, civs, graphics: dict) -> str:
    patched = 0
    for units in civs.units:
        if len(units) <= max(PACMAN_UNIT, WONDER_UNIT):
            continue
        pac, wonder = units[PACMAN_UNIT], units[WONDER_UNIT]
        if pac is None or wonder is None or pac.type < 70 or wonder.type != 80:
            continue
        gfx = graphics.get(pac.values["standing"][0])
        if gfx is not None and not gfx.name.lower().startswith("mkyby"):
            return f"Pac-Man at the Wonder: not changed, unit {PACMAN_UNIT} is {pac.name!r} ({gfx.name})"
        DU.patch(data, pac, enabled=1, train_location=WONDER_UNIT, button=PACMAN_BUTTON, cost=PACMAN_COST,
                 train_time=PACMAN_TIME, hit_points=PACMAN_HP)
        patched += 1
    if not patched:
        return "Pac-Man at the Wonder: not changed, no civilisation has both the Monkey Boy and the Wonder"
    return (f"Pac-Man (unit {PACMAN_UNIT}) trainable at the Wonder (unit {WONDER_UNIT}) for {patched} "
            f"civilisations: {PACMAN_COST[1]} food, {PACMAN_COST[4]} gold, {PACMAN_TIME} s, {PACMAN_HP} hit points")


# The Javelina (unit 822) borrows the Wild Boar's sprites in The Conquerors; its own graphics
# (BOARJ_*) are in the .dat, but their sprite files were never shipped. The build renders those
# files (as a pig) and points the Javelina at them. Its carcass becomes a copy of the boar's
# carcass (same food) with the pig's decay sprite.
JAVELINA, JAVELINA_DEAD, BOAR_DEAD = 822, 823, 356
JAVELINA_ACTIONS = {"BOARJ_AN": "attack", "BOARJ_DN": "die", "BOARJ_FN": "idle", "BOARJ_RN": "run",
                    "BOARJ_SN": "decay", "BOARJ_WN": "walk"}


def javelina_graphics(graphics: dict) -> Optional[dict[str, object]]:
    """The Javelina's own graphics in the .dat, by name, if all six are there."""
    by_name = {g.name.upper(): g for g in graphics.values()}
    found = {name: by_name.get(name) for name in JAVELINA_ACTIONS}
    if any(g is None or g.slp <= 0 for g in found.values()):
        return None
    return found


def _javelina(data: bytearray, civs, graphics: dict) -> str:
    gfx = javelina_graphics(graphics)
    if gfx is None:
        return "Javelina: not changed, its own graphics are not in the .dat"
    gid = {name: next(k for k, g in graphics.items() if g is gfx[name]) for name in gfx}
    patched = corpses = 0
    for units in civs.units:
        if len(units) <= JAVELINA:
            continue
        jav = units[JAVELINA]
        if jav is None or jav.type < 70:
            continue
        stand = graphics.get(jav.values["standing"][0])
        if stand is None or not stand.name.upper().startswith(("BOARX", "BOARJ")):
            continue
        DU.patch(data, jav, standing=(gid["BOARJ_FN"], -1), dying=(gid["BOARJ_DN"], -1),
                 walking=(gid["BOARJ_WN"], gid["BOARJ_RN"]), attack_graphic=gid["BOARJ_AN"])
        patched += 1
        dead, boar_dead = units[JAVELINA_DEAD], units[BOAR_DEAD]
        if (dead is not None and boar_dead is not None and dead.type == boar_dead.type
                and dead.end - dead.offset == boar_dead.end - boar_dead.offset
                and jav.values["dead_unit"] == BOAR_DEAD):
            name = bytes(data[dead.fields["name"]:dead.fields["name"] + len(dead.name)])
            data[dead.offset:dead.end] = data[boar_dead.offset:boar_dead.end]  # same food, same behaviour
            struct.pack_into("<h", data, dead.offset + 3, JAVELINA_DEAD)
            data[dead.fields["name"]:dead.fields["name"] + len(name)] = name
            DU.patch(data, dead, standing=(gid["BOARJ_SN"], -1))
            DU.patch(data, jav, dead_unit=JAVELINA_DEAD)
            corpses += 1
    if not patched:
        return "Javelina: not changed, it does not use the Wild Boar's sprites here"
    return f"Javelina: its own (pig) sprites for {patched} civilisations, with its own carcass for {corpses}"


def pacman_icon(size: int = 36) -> slp.SlpFrame:
    """A unit icon (drawn at 36x36, scaled to `size`): Pac-Man in a blue maze corridor, chasing dots."""
    black, blue, yellow, dark_yellow, eye, dot = 0, 1, 2, 3, 4, 5
    px = np.full((36, 36), black, np.int16)
    px[0:2, :] = px[-2:, :] = px[:, 0:2] = px[:, -2:] = blue
    px[6:8, 2:30] = blue
    px[28:30, 6:34] = blue
    yy, xx = np.mgrid[0:36, 0:36]
    cx, cy, r = 14.5, 17.5, 9.5
    d = np.hypot(xx - cx, yy - cy)
    ang = np.degrees(np.arctan2(-(yy - cy), xx - cx))
    body = (d <= r) & ~((np.abs(ang) < 33) & (xx > cx))
    px[body] = yellow
    px[body & (d > r - 1.3)] = dark_yellow
    px[12:14, 14:16] = eye
    for x in (26, 31):
        px[17:19, x:x + 2] = dot
    if size != 36:
        idx = (np.arange(size) * 36 // size)
        px = px[idx][:, idx]
    return slp.SlpFrame(px, (0, 0))


ICON_COLOURS = {0: (8, 8, 16), 1: (40, 60, 220), 2: (255, 214, 0), 3: (214, 170, 0), 4: (16, 16, 16),
                5: (250, 200, 170)}


def icon_sheets(archives: list[tuple[str, object]]) -> list[tuple[str, object, bytes]]:
    """Every copy of the unit icon sheet, in load order: (archive name, archive, sheet)."""
    out = []
    for name, drs in archives:
        if drs is not None and UNIT_ICONS in drs.ids():
            out.append((name, drs, drs.get(UNIT_ICONS)))
    return out


def icon_sheet(data: bytes, quant) -> tuple[Optional[bytes], str]:
    """The unit icon sheet with Pac-Man's icon in the Monkey Boy's slot."""
    try:
        info = slp.info(data)
    except ValueError as exc:
        return None, f"not changed ({exc})"
    if info.num_frames <= PACMAN_ICON:
        return None, f"not changed: this sheet has {info.num_frames} icons, not {PACMAN_ICON + 1}"
    w, h = info.sizes[PACMAN_ICON][:2]
    if not (16 <= w <= 96 and 16 <= h <= 96):
        return None, f"not changed: icon {PACMAN_ICON} is {w}x{h} pixels"
    frame = pacman_icon(min(w, h))
    lut = {k: int(quant.indices(np.array([rgb], np.int64))[0]) for k, rgb in ICON_COLOURS.items()}
    px = np.vectorize(lut.get)(frame.pixels).astype(np.int16)
    if (w, h) != px.shape[::-1]:  # not square: centre the icon on a black frame
        full = np.full((h, w), lut[0], np.int16)
        y0, x0 = (h - px.shape[0]) // 2, (w - px.shape[1]) // 2
        full[y0:y0 + px.shape[0], x0:x0 + px.shape[1]] = px
        px = full
    return slp.replace_frame(data, PACMAN_ICON, slp.SlpFrame(px, (0, 0))), f"icon {PACMAN_ICON} ({w}x{h}) is now Pac-Man"
