"""Animation poses. `t` runs from 0 to 1 over one cycle.

AoE2 needs these sprite sets per unit: stand, walk, attack, die and decay
(the corpse); villagers also walk while carrying. Deaths use the Minecraft
look: the body tips over sideways and flashes red. Each unit names a rig
(how its body moves) and an attack style (what its attack looks like).
"""
from __future__ import annotations

import math

from .geometry import Pose

# AoE2 unit directions in SLP order (the last three are mirrored in-game),
# with the heading each one faces (degrees, 0 = east, 90 = north).
DIRECTIONS = [("S", -90), ("SW", -135), ("W", 180), ("NW", 135), ("N", 90),
              ("NE", 45), ("E", 0), ("SE", -45)]
ACTIONS = ("idle", "walk", "attack", "die")
WHEELS = [f"wheel_{i}" for i in range(1, 7)]
QUAD_LEGS = (("leg_fr", 1), ("leg_bl", 1), ("leg_fl", -1), ("leg_br", -1))


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def _pulse(t: float, start: float, end: float) -> float:
    """0 -> 1 -> 0 between start and end."""
    if not start <= t <= end:
        return 0.0
    return math.sin(math.pi * (t - start) / (end - start))


def _add(p: Pose, name: str, rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> None:
    x, y, z = p.rot.get(name, (0.0, 0.0, 0.0))
    p.rot[name] = (x + rx, y + ry, z + rz)


def _move(p: Pose, name: str, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> None:
    x, y, z = p.move.get(name, (0.0, 0.0, 0.0))
    p.move[name] = (x + dx, y + dy, z + dz)


# --------------------------------------------------------------------------- limbs

def _legs(p: Pose, t: float, amp: float = 32) -> None:
    s = math.sin(2 * math.pi * t)
    _add(p, "leg_r", amp * s)
    _add(p, "leg_l", -amp * s)


def _quad(p: Pose, t: float, amp: float = 28) -> None:
    s = math.sin(2 * math.pi * t)
    for leg, sign in QUAD_LEGS:
        _add(p, leg, sign * amp * s)


def _arm_swing(p: Pose, t: float, style: str) -> None:
    s = math.sin(2 * math.pi * t)
    if style in ("crossbow", "gun", "punch", "slam"):
        _add(p, "arm_r", 4 * s)
        _add(p, "arm_l", -4 * s)
    else:
        _add(p, "arm_r", -20 * s)
        _add(p, "arm_l", 28 * s)


def _attack_arms(p: Pose, t: float, style: str) -> None:
    """Upper-body attack motion, shared by foot units and riders."""
    if style == "chop":
        if t < 0.45:
            a = 145 * _ease(t / 0.45)
        elif t < 0.6:
            a = 145 - 150 * _ease((t - 0.45) / 0.15)
        else:
            a = -5 + 5 * _ease((t - 0.6) / 0.4)
        _add(p, "arm_r", a)
        _add(p, "torso", rz=8 * math.sin(math.pi * t))
    elif style == "thrust":
        a = -25 * _ease(t / 0.4) if t < 0.4 else (-25 + 85 * _ease((t - 0.4) / 0.15) if t < 0.55
                                                  else 60 * (1 - _ease((t - 0.55) / 0.45)))
        _add(p, "arm_r", a)
        _move(p, "torso", dy=2 * _pulse(t, 0.4, 0.8))
    elif style == "bow":
        raise_ = _ease(t / 0.3) * (1 - _ease((t - 0.8) / 0.2))
        _add(p, "arm_l", 90 * raise_)
        _add(p, "item_l", -90 * raise_)
        draw = raise_ * (1 - _pulse(t, 0.6, 0.7))
        _add(p, "arm_r", 90 * draw, rz=25 * draw)
    elif style in ("crossbow", "gun"):
        kick = _pulse(t, 0.45, 0.7)
        _add(p, "arm_r", 18 * kick)
        _add(p, "arm_l", 18 * kick)
        _add(p, "torso", -6 * kick)
        _move(p, "item_c", dy=-1.5 * kick)
    elif style == "throw":
        a = -60 * _ease(t / 0.4) if t < 0.4 else (-60 + 210 * _ease((t - 0.4) / 0.15) if t < 0.55
                                                  else 150 * (1 - _ease((t - 0.55) / 0.45)))
        _add(p, "arm_r", a)
    elif style == "cast":
        up = _ease(t / 0.3) * (1 - _ease((t - 0.8) / 0.2))
        wave = 12 * math.sin(4 * math.pi * t)
        _add(p, "arm_r", 120 * up + wave)
        _add(p, "arm_l", 120 * up - wave)
    elif style == "punch":
        a = -40 * _pulse(t, 0.0, 0.5) + 25 * _pulse(t, 0.5, 1.0)
        _add(p, "arm_r", a)
        _add(p, "arm_l", a)
    elif style == "slam":
        a = 110 * _ease(t / 0.45) if t < 0.45 else 110 * (1 - _ease((t - 0.45) / 0.2))
        _add(p, "arm_r", a)
        _add(p, "arm_l", a)
    elif style == "fish":
        cast = _ease(t / 0.2) * (1 - _ease((t - 0.3) / 0.15))
        _add(p, "arm_r", 70 * cast + 25 + 3 * math.sin(6 * math.pi * t))
    elif style == "gather":
        bend = _pulse(t, 0.0, 1.0)
        _add(p, "torso", -25 * bend)
        _add(p, "arm_r", 55 * bend)
        _add(p, "arm_l", 40 * bend)
    elif style == "shear":
        _add(p, "arm_r", 45 + 8 * math.sin(8 * math.pi * t))
        _add(p, "arm_l", 30)
        _add(p, "torso", -12)


# --------------------------------------------------------------------------- rigs

def pose(unit, action: str, t: float) -> Pose:
    p = Pose()
    rig, style = unit.rig, unit.attack
    s = math.sin(2 * math.pi * t)
    breathe = 2 * s

    if unit.carry:
        p.hidden |= {"item_r", "item_l"} if action == "carry" else {"carry"}

    if action == "die" and rig == "pacman":  # the arcade death: the mouth opens all the way, then a pop
        opening = 60 + 300 * _ease(min(1.0, t / 0.8))
        _add(p, "jaw_top", rx=opening / 2)
        _add(p, "jaw_bottom", rx=-opening / 2)
        p.hidden |= {"body"} if t >= 0.85 else {"pop"}
        return p
    if action == "die":
        fall = _ease(t / 0.6)
        if rig == "ship":
            _move(p, "root", dz=-18 * _ease(t))
            _add(p, "root", 25 * fall, 15 * fall)
        elif rig in ("wheeled", "trebuchet"):
            _add(p, "root", ry=25 * fall)
            _move(p, "root", dz=-2 * fall)
            p.tint = (0.1, 0.08, 0.06, 0.5 * min(1.0, t * 3))  # burnt
        else:
            _add(p, "root", ry=90 * fall)
            p.tint = (1.0, 0.15, 0.15, 0.35 * min(1.0, t * 3))
        return p

    if rig in ("biped", "golem"):
        if action == "idle":
            if style not in ("crossbow", "gun"):
                _add(p, "arm_r", breathe)
                _add(p, "arm_l", -breathe)
            _add(p, "head", breathe / 2)
        elif action in ("walk", "carry"):
            _legs(p, t, 25 if rig == "golem" else 32)
            _add(p, "cape", -4 - 6 * abs(s))
            if action == "carry":
                _add(p, "arm_r", 40)
                _add(p, "arm_l", 60)
            else:
                _arm_swing(p, t, style if rig == "biped" else "chop")
        elif action == "attack":
            _attack_arms(p, t, style)
    elif rig == "villager":
        if action in ("walk", "carry"):
            _legs(p, t)
            _add(p, "head", 3 * s)
        else:
            _add(p, "head", breathe / 2)
    elif rig == "biped_animal":
        if action == "walk":
            _legs(p, t, 40)
        _add(p, "head", 6 * math.sin(4 * math.pi * t) if action != "walk" else 3 * s)
    elif rig == "quadruped":
        if action == "walk":
            _quad(p, t)
            _add(p, "head", 3 * s)
        elif action == "attack":
            if style == "explode":  # creeper swelling and flashing
                p.tint = (1.0, 1.0, 1.0, 0.5 * _pulse((t * 2) % 1.0, 0.0, 1.0))
                _move(p, "torso", dz=0.5 * _pulse(t, 0.0, 1.0))
            else:
                lunge = _pulse(t, 0.3, 0.7)
                _add(p, "head", -15 * lunge)
                _move(p, "head", dy=3 * lunge)
        else:
            _add(p, "head", breathe)
        _add(p, "tail", rz=10 * s)
    elif rig in ("cavalry", "horse_archer"):
        if action in ("walk", "carry"):
            _quad(p, t, 30)
            _add(p, "horse_head", 5 * s)
            _move(p, "rider", dz=0.6 * abs(s))
            _add(p, "tail", -8 * abs(s))
        else:
            _add(p, "horse_head", breathe / 2)
            _add(p, "tail", rz=6 * s)
            if action == "attack":
                _attack_arms(p, t, style)
    elif rig == "snow_golem":
        if action == "walk":
            _add(p, "torso", rz=6 * s)
            _move(p, "torso", dz=0.8 * abs(s))
        elif action == "attack":
            a = -40 * _ease(t / 0.4) if t < 0.4 else (-40 + 120 * _ease((t - 0.4) / 0.15) if t < 0.55
                                                      else 80 * (1 - _ease((t - 0.55) / 0.45)))
            _add(p, "arm_r", a)
        _add(p, "head", breathe / 2)
    elif rig == "blaze":
        speed = 2.0 if action == "attack" else 1.0
        _add(p, "rods_top", rz=360 * t * speed)
        _add(p, "rods_mid", rz=-360 * t * speed)
        _add(p, "rods_low", rz=360 * t * speed)
        _move(p, "torso", dz=6 + 1.5 * s)
        if action == "walk":
            _add(p, "torso", 8)
        if action == "attack":
            _add(p, "head", -10 * _pulse(t, 0.4, 0.7))
    elif rig == "ravager":
        if action == "walk":
            _quad(p, t, 22)
            _add(p, "head", 4 * s)
        elif action == "attack":  # head down, then ram forward
            down = _ease(t / 0.4) * (1 - _ease((t - 0.7) / 0.3))
            _add(p, "head", -18 * down)
            _move(p, "head", dy=5 * _pulse(t, 0.4, 0.65))
        else:
            _add(p, "head", breathe / 2)
    elif rig == "wheeled":
        if action == "walk":
            for w in WHEELS:
                _add(p, w, -360 * t)
            _move(p, "body", dz=0.3 * abs(s))
            _quad(p, t, 25)  # draught animals, if any
            _add(p, "horse_head", 4 * s)
        elif action == "attack":
            kick = _pulse(t, 0.3, 0.6)
            _add(p, "weapon", 8 * kick)
            _move(p, "weapon", dy=-2 * kick)
    elif rig == "trebuchet":
        if action == "walk":  # packed for travel: frame laid flat, crate and payload stowed on top
            _add(p, "frame", -90)
            _add(p, "arm", 90)
            _add(p, "counterweight", 180)
            _add(p, "sling", 180)
            for w in WHEELS:
                _add(p, w, -360 * t)
        else:
            if action == "attack":  # counterweight drops, arm throws over the top, then winds back
                a = 55 - 175 * _ease((t - 0.15) / 0.3) if t < 0.45 else -120 + 175 * _ease((t - 0.55) / 0.45)
                a = 55 if t < 0.15 else (-120 if 0.45 <= t < 0.55 else a)
            else:
                a = 55  # loaded
            _add(p, "arm", a)
            _add(p, "counterweight", -a)
            _add(p, "sling", -a)
    elif rig == "flyer":  # flapping flight; gliding holds the wings out and banks
        if action == "attack" or action == "idle":  # gliding
            _add(p, "wing_r", ry=-8 + 3 * s)
            _add(p, "wing_l", ry=8 - 3 * s)
            _add(p, "torso", ry=10 * s)
        else:
            flap = 45 * s
            _add(p, "wing_r", ry=-flap)
            _add(p, "wing_l", ry=flap)
            _add(p, "tip_r", ry=-0.5 * flap)
            _add(p, "tip_l", ry=0.5 * flap)
            _move(p, "torso", dz=-2 * s)
    elif rig == "swimmer":  # a fish circling under the surface, leaping now and then
        a = 2 * math.pi * t
        _move(p, "root", dx=10 * math.cos(a), dy=10 * math.sin(a))
        _add(p, "root", rz=math.degrees(a))
        _add(p, "tail", rz=25 * math.sin(4 * a))
        u = (t - 0.55) / 0.3
        if 0 <= u <= 1:
            _move(p, "root", dz=-2 + 22 * math.sin(math.pi * u))
            _add(p, "torso", rx=40 * math.cos(math.pi * u))
        else:
            _move(p, "root", dz=-2)
    elif rig == "pacman":  # chomp, chomp
        p.hidden |= {"pop"}
        if action == "idle":
            opening, bob = 8 + 30 * (0.5 - 0.5 * math.cos(2 * math.pi * t)), 0.8 * s
        elif action == "attack":
            opening, bob = 5 + 75 * (0.5 - 0.5 * math.cos(4 * math.pi * t)), 0.0
            _move(p, "root", dy=3 * _pulse(t, 0.0, 0.5) + 3 * _pulse(t, 0.5, 1.0))
        else:
            opening, bob = 5 + 55 * (0.5 - 0.5 * math.cos(4 * math.pi * t)), 1.2 * abs(s)
        _add(p, "jaw_top", rx=opening / 2)
        _add(p, "jaw_bottom", rx=-opening / 2)
        _move(p, "body", dz=bob)
    elif rig == "ghost":  # floating, the skirt rippling
        _move(p, "body", dz=0.8 * s)
        for k in range(8):
            _move(p, f"foot{k % 2}_{k}", dz=(1 if k % 2 else -1) * 1.2 * math.sin(4 * math.pi * t) + 0.8 * s)
    elif rig == "ship":
        _add(p, "root", ry=3 * s)
        _move(p, "root", dz=0.6 * s)
        if action == "attack":
            kick = _pulse(t, 0.3, 0.6)
            _add(p, "weapon", 8 * kick)
            _move(p, "weapon", dy=-2 * kick)
        _add(p, "sail", -3 - 3 * abs(s) if action == "walk" else -1)
    return p
