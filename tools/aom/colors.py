"""Player colours.

AoE2 stores player colour as 8 shades per player in its 256-colour palette,
so lightness is snapped to 8 steps here as well. The base colours are close
approximations for previews; the real values come from the game palette at
export time.
"""
from __future__ import annotations

import numpy as np

PLAYER_COLORS = {
    1: ("Blue", (0.18, 0.30, 1.00)),
    2: ("Red", (0.90, 0.08, 0.06)),
    3: ("Green", (0.10, 0.62, 0.10)),
    4: ("Yellow", (1.00, 0.92, 0.10)),
    5: ("Cyan", (0.10, 0.80, 0.80)),
    6: ("Purple", (0.62, 0.15, 0.85)),
    7: ("Grey", (0.62, 0.62, 0.62)),
    8: ("Orange", (1.00, 0.52, 0.05)),
}

SHADES = 8


def player_rgb(player: int, lightness: np.ndarray) -> np.ndarray:
    """Map lightness (0..1) onto the player's 8-step colour ramp."""
    base = np.array(PLAYER_COLORS[player][1])
    level = np.clip(np.round(np.asarray(lightness) * (SHADES - 1)), 0, SHADES - 1) / (SHADES - 1)
    level = level[..., None]
    dark = base * 0.18
    light = base + (1 - base) * 0.55
    lower = dark + (base - dark) * (level / 0.55)
    upper = base + (light - base) * ((level - 0.55) / 0.45)
    return np.where(level < 0.55, lower, upper)
