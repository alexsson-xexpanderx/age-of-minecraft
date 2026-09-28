"""Animation poses per rig. `t` runs from 0 to 1 over one cycle.

AoE2 needs these sprite sets per unit: stand, walk, attack, die and decay
(the corpse). Deaths use the Minecraft look: the body tips over sideways
and flashes red.
"""
from __future__ import annotations

import math

from .geometry import Pose

# AoE2 unit directions in SLP order (the last three are mirrored in-game),
# with the heading each one faces (degrees, 0 = east, 90 = north).
DIRECTIONS = [("S", -90), ("SW", -135), ("W", 180), ("NW", 135), ("N", 90),
              ("NE", 45), ("E", 0), ("SE", -45)]


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def pose(rig: str, action: str, t: float) -> Pose:
    p = Pose()
    s = math.sin(2 * math.pi * t)
    held = {"arm_r": (15, 0, 0)} if rig == "biped" else {}

    if action == "idle":
        breathe = 2 * math.sin(2 * math.pi * t)
        p.rot.update(held)
        if rig == "biped":
            p.rot["arm_r"] = (15 + breathe, 0, 0)
            p.rot["arm_l"] = (-breathe, 0, 0)
        p.rot["head"] = (breathe, 0, 0)
    elif action == "walk":
        if rig in ("biped", "villager"):
            p.rot["leg_r"] = (32 * s, 0, 0)
            p.rot["leg_l"] = (-32 * s, 0, 0)
        if rig == "biped":
            p.rot["arm_r"] = (15 - 20 * s, 0, 0)
            p.rot["arm_l"] = (28 * s, 0, 0)
            p.rot["cape"] = (-10 - 6 * abs(s), 0, 0)
        if rig == "villager":
            p.rot["head"] = (3 * s, 0, 0)
        if rig == "quadruped":
            for leg, sign in (("leg_fr", 1), ("leg_bl", 1), ("leg_fl", -1), ("leg_br", -1)):
                p.rot[leg] = (sign * 28 * s, 0, 0)
    elif action == "attack":
        p.rot.update(held)
        if rig == "biped":
            if t < 0.45:  # wind up
                a = 15 + 145 * _ease(t / 0.45)
            elif t < 0.6:  # strike
                a = 160 - 150 * _ease((t - 0.45) / 0.15)
            else:  # recover
                a = 10 + 5 * _ease((t - 0.6) / 0.4)
            p.rot["arm_r"] = (a, 0, 0)
            p.rot["torso"] = (0, 0, 8 * math.sin(math.pi * t))
    elif action == "die":
        p.rot.update(held)
        fall = _ease(t / 0.6)
        p.rot["root"] = (0, 90 * fall, 0)
        p.tint = (1.0, 0.15, 0.15, 0.35 * min(1.0, t * 3))
    else:
        raise ValueError(action)
    return p
