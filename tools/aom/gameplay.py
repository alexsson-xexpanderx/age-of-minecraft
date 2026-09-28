"""Gameplay changes in the .dat: Pac-Man can be trained at the Wonder.

The easter egg lives in Furious the Monkey Boy's slot (unit 860), so the
chat cheat still spawns him. Here every civilisation also gets him enabled,
trained at the Wonder (unit 276), which exists only once a Wonder stands.
The unit icon (frame 159 of the unit icon sheet in interfac.drs) becomes
Pac-Man too.
"""
from __future__ import annotations

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
    try:
        data = bytearray(DU.decompress(raw))
        civs = DU.read_units(bytes(data))
    except Exception as exc:  # a .dat we cannot read exactly is left alone
        return None, f"not changed: could not read the unit tables ({exc})"
    patched, notes = 0, []
    for units in civs.units:
        if len(units) <= max(PACMAN_UNIT, WONDER_UNIT):
            continue
        pac, wonder = units[PACMAN_UNIT], units[WONDER_UNIT]
        if pac is None or wonder is None or pac.type < 70 or wonder.type != 80:
            continue
        gfx = graphics.get(pac.values["standing"][0])
        if gfx is not None and not gfx.name.lower().startswith("mkyby"):
            return None, f"not changed: unit {PACMAN_UNIT} is {pac.name!r} ({gfx.name}), not Furious the Monkey Boy"
        DU.patch(data, pac, enabled=1, train_location=WONDER_UNIT, button=PACMAN_BUTTON, cost=PACMAN_COST,
                 train_time=PACMAN_TIME, hit_points=PACMAN_HP)
        patched += 1
    if not patched:
        return None, "not changed: no civilisation has both the Monkey Boy and the Wonder"
    check = DU.read_units(bytes(data))  # read everything back: same layout, new values
    for units in check.units:
        pac = units[PACMAN_UNIT] if len(units) > PACMAN_UNIT else None
        if pac is not None and pac.type >= 70 and pac.values["train_location"] != WONDER_UNIT:
            return None, "not changed: the patched file did not read back as expected"
    notes.append(f"Pac-Man (unit {PACMAN_UNIT}) trainable at the Wonder (unit {WONDER_UNIT}) for {patched} "
                 f"civilisations: {PACMAN_COST[1]} food, {PACMAN_COST[4]} gold, {PACMAN_TIME} s, {PACMAN_HP} hit points")
    return DatPatch(DU.compress(bytes(data)), patched, notes), notes[0]


def pacman_icon(size: int = 36) -> slp.SlpFrame:
    """A 36x36 unit icon: Pac-Man in a blue maze corridor, chasing dots."""
    black, blue, yellow, dark_yellow, eye, dot = 0, 1, 2, 3, 4, 5
    px = np.full((size, size), black, np.int16)
    px[0:2, :] = px[-2:, :] = px[:, 0:2] = px[:, -2:] = blue
    px[6:8, 2:30] = blue
    px[28:30, 6:34] = blue
    yy, xx = np.mgrid[0:size, 0:size]
    cx, cy, r = 14.5, 17.5, 9.5
    d = np.hypot(xx - cx, yy - cy)
    ang = np.degrees(np.arctan2(-(yy - cy), xx - cx))
    body = (d <= r) & ~((np.abs(ang) < 33) & (xx > cx))
    px[body] = yellow
    px[body & (d > r - 1.3)] = dark_yellow
    px[12:14, 14:16] = eye
    for x in (26, 31):
        px[17:19, x:x + 2] = dot
    return slp.SlpFrame(px, (0, 0))


ICON_COLOURS = {0: (8, 8, 16), 1: (40, 60, 220), 2: (255, 214, 0), 3: (214, 170, 0), 4: (16, 16, 16),
                5: (250, 200, 170)}


def icon_sheet(data: bytes, quant) -> tuple[Optional[bytes], str]:
    """The unit icon sheet with Pac-Man's icon, if the sheet looks like the real one."""
    try:
        info = slp.info(data)
    except ValueError as exc:
        return None, f"icon not changed ({exc})"
    icon = _icon_index(info)
    if icon is None:
        return None, "icon not changed: the unit icon sheet does not have the expected 36x36 frames"
    frame = pacman_icon()
    lut = {k: int(quant.indices(np.array([rgb], np.int64))[0]) for k, rgb in ICON_COLOURS.items()}
    frame.pixels = np.vectorize(lut.get)(frame.pixels).astype(np.int16)
    return slp.replace_frame(data, icon, frame), f"unit icon {icon} is now Pac-Man"


def _icon_index(info) -> Optional[int]:
    if info.num_frames <= PACMAN_ICON:
        return None
    w, h = info.sizes[PACMAN_ICON][:2]
    return PACMAN_ICON if (w, h) == (36, 36) else None
