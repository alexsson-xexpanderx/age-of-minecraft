"""Wonders (5x5 tiles -> 14x14 blocks): each civilisation's wonder as a Minecraft build.

The letter is the one used in the game's graphic names (WNDR0NN<letter>).
Scenario monuments (pyramids, Dome of the Rock, cathedral, mosque...) are
here too.
"""
from __future__ import annotations

import numpy as np

from . import voxel as V
from .structures import lantern, team_banner, torch

N = 14


def _w(name: str, n: int = N) -> V.Structure:
    return V.Structure(name, origin=(n / 2, n / 2))


def _plinth(s: V.Structure, block: str, n: int = N, steps: int = 1) -> None:
    for k in range(steps):
        s.fill(k, k, k, n - 1 - k, n - 1 - k, k, block)


# --------------------------------------------------------------------------- templates

def cathedral(name: str, stone: str, roof: str, spires: int = 1, trim: str = "chiseled_stone_bricks",
              glass=("red_stained_glass", "blue_stained_glass", "yellow_stained_glass")) -> V.Structure:
    """A gothic cathedral: a long nave with a steep roof and one or two front spire towers."""
    s = _w(name)
    _plinth(s, "polished_andesite")
    s.fill(3, 1, 1, 10, 12, 6, stone)
    for y in range(2, 12, 2):
        s.set(10, y, 3, glass[y % 3])
        s.set(10, y, 4, glass[(y + 1) % 3])
    V.gable_roof(s, 3, 10, 1, 12, 7, roof, stone, axis="y", overhang=0)
    # transept
    s.fill(1, 5, 1, 12, 8, 6, stone)
    V.gable_roof(s, 1, 12, 5, 8, 7, roof, stone, axis="x", overhang=0)
    s.set(12, 6, 5, "purple_stained_glass")
    s.set(12, 7, 5, "purple_stained_glass")
    towers = [(4, 11)] if spires == 1 else [(3, 11), (8, 11)]
    for x, y in towers:
        s.fill(x, y, 1, x + 2, y + 2, 12, stone)
        s.fill(x, y, 12, x + 2, y + 2, 12, trim)
        s.cone(x + 1.5, y + 1.5, 13, 1.6, roof, step=0.3)
        V.window(s, x + 1, y + 2, 9, "+y", "yellow_stained_glass")
    V.door(s, 6, 13, 1, "+y", "dark_oak", double=True) if spires == 2 else V.door(s, 5, 13, 1, "+y", "dark_oak")
    s.set(6, 12, 5, "red_stained_glass")
    team_banner(s, 12.95, 5.5, 6, "+x", seed=name, height=26)
    return s


def domed(name: str, wall: str, dome: str, minarets: int, trim: str, accent: str = "gold_block",
          half_domes: bool = False) -> V.Structure:
    """A great mosque / basilica: a square hall under a big dome, with minarets."""
    s = _w(name)
    _plinth(s, trim)
    s.fill(2, 2, 1, 11, 11, 6, wall)
    for k in range(3, 11, 2):
        V.window(s, 11, k, 3, "+x", "light_blue_stained_glass")
        V.window(s, k, 11, 3, "+y", "light_blue_stained_glass")
    V.door(s, 6, 11, 1, "+y", "acacia", double=True)
    s.fill(2, 2, 7, 11, 11, 7, trim)
    s.dome(7.0, 7.0, 8, 4.3, dome)
    s.set(6, 6, 12, accent)
    s.set(6, 6, 13, accent, "post")
    if half_domes:
        s.dome(7.0, 11.0, 7, 2.5, dome)
        s.dome(11.0, 7.0, 7, 2.5, dome)
    spots = [(0, 0), (12, 12), (0, 12), (12, 0)][:minarets]
    for x, y in spots:
        s.fill(x, y, 0, x + 1, y + 1, 13, wall)
        s.fill(x, y, 10, x + 1, y + 1, 10, trim)
        s.cone(x + 1.0, y + 1.0, 14, 1.2, dome, step=0.35)
    return s


def pagoda(name: str, tiers: int, wall: str, roof: str, pillar: str, base: str, n: int = N,
           round_temple: bool = False) -> V.Structure:
    """A tiered pagoda (or the round Temple of Heaven), each tier smaller than the last."""
    s = _w(name, n)
    _plinth(s, base, n, steps=2)
    lo, hi, z = 2, n - 3, 2
    tier_h = 2 if tiers > 5 else 3
    for t in range(tiers):
        if hi - lo < 1:
            break
        if round_temple:
            c, r = (lo + hi + 1) / 2, (hi - lo + 1) / 2
            s.cylinder(c, c, r - 0.3, z, z + tier_h - 1, wall)
            s.cylinder(c, c, r + 0.8, z + tier_h, z + tier_h, roof)
            s.cylinder(c, c, r - 0.2, z + tier_h + 1, z + tier_h + 1, roof)
        else:
            s.fill(lo, lo, z, hi, hi, z + tier_h - 1, wall)
            for x, y in ((lo, lo), (lo, hi), (hi, lo), (hi, hi)):
                s.fill(x, y, z, x, y, z + tier_h - 1, pillar)
            V.window(s, hi, (lo + hi) // 2, z + 1, "+x")
            V.window(s, (lo + hi) // 2, hi, z + 1, "+y")
            V.pagoda_roof(s, lo, hi, lo, hi, z + tier_h, roof, pillar)
        z += tier_h + (2 if round_temple else 1)
        lo, hi = lo + (2 if tiers <= 4 else 1), hi - (2 if tiers <= 4 else 1)
    c = n / 2
    s.fill(int(c) - 1, int(c) - 1, z, int(c) - 1, int(c) - 1, z + 2, "gold_block", "post")
    s.set(int(c) - 1, int(c) - 1, z + 3, "gold_block", "cube_small")
    return s


def step_pyramid(name: str, stone: str, top: str, shrines: int = 1, steps: int = 6, stair: str = None,
                 n: int = N, comb: bool = False, rise: int = 2) -> V.Structure:
    """A Mesoamerican step pyramid with a stairway on the +y face and temples on top."""
    s = _w(name, n)
    for k in range(steps):
        s.fill(k, k, k * rise, n - 1 - k, n - 1 - k, k * rise + rise - 1, stone if k % 2 == 0 else top)
    z = steps * rise
    mid = n // 2
    for zz in range(z):  # the grand stairway
        y = n - 1 - zz // rise
        for x in (mid - 1, mid):
            s.set(x, y, zz, stair or stone, "stair_+y")
            if zz % rise:
                s.set(x, y + 1, zz - 1, stair or stone, "stair_+y")
    k0, k1 = steps, n - 1 - steps
    if shrines == 2:
        half = max(1, (k1 - k0 + 1) // 2)
        for x0, col in ((k0, "red_terracotta"), (k0 + half, "blue_terracotta")):
            s.fill(x0, k0, z, x0 + half - 1, k1, z + 2, col)
            s.carve(x0 + half // 2, k1, z, x0 + half // 2, k1, z + 1)
            s.fill(x0, k0, z + 3, x0 + half - 1, k1, z + 3, "gold_block", "slab")
    else:
        s.fill(k0, k0, z, k1, k1, z + 2, top)
        s.carve(mid - 1, k1, z, mid, k1, z + 1)
        s.fill(k0, k0, z + 3, k1, k1, z + 3, "gold_block" if not comb else top, "slab")
        if comb:  # the roof comb of Tikal's temples
            s.fill(k0, k0, z + 3, k1, k0, z + 6, stone)
            s.set(mid - 1, k0, z + 7, "gold_block")
    torch(s, mid - 1.5, n - 0.5, 0)
    torch(s, mid + 1.5, n - 0.5, 0)
    return s


def smooth_pyramid(name: str, n: int, block: str = "sandstone", cap: str = "gold_block") -> V.Structure:
    s = _w(name, n)
    k = 0
    while n - 2 * k > 1:
        for x in range(k, n - k):
            s.set(x, k, k, block, "stair_-y")
            s.set(x, n - 1 - k, k, block, "stair_+y")
        for y in range(k + 1, n - 1 - k):
            s.set(k, y, k, block, "stair_-x")
            s.set(n - 1 - k, y, k, block, "stair_+x")
        s.fill(k + 1, k + 1, k, n - 2 - k, n - 2 - k, k, block)
        k += 1
    s.set(k, k, k, cap)
    s.set(n // 2 - 1, n - 1, 0, "chiseled_sandstone")
    return s


# --------------------------------------------------------------------------- the eighteen wonders

def britons() -> V.Structure:  # Westminster / a gothic cathedral with one great tower
    return cathedral("wonder_britons", "stone_bricks", "deepslate_tiles", spires=1)


def franks() -> V.Structure:  # Chartres: twin spires
    return cathedral("wonder_franks", "smooth_stone", "oxidized_cut_copper", spires=2)


def goths() -> V.Structure:  # a massive Germanic basilica with a round tower
    s = cathedral("wonder_goths", "bricks", "dark_oak_planks", spires=1, trim="stone_bricks")
    s.cylinder(12.0, 12.0, 1.6, 1, 10, "stone_bricks")
    s.cone(12.0, 12.0, 11, 1.8, "dark_oak_planks", step=0.4)
    return s


def teutons() -> V.Structure:  # Aachen: an octagonal chapel under a domed tower
    s = _w("wonder_teutons")
    _plinth(s, "stone_bricks")
    s.cylinder(7.0, 7.0, 5.6, 1, 6, "white_terracotta")
    for k in range(8):
        a = k * np.pi / 4
        x, y = int(7 + 5.2 * np.cos(a)), int(7 + 5.2 * np.sin(a))
        s.fill(x, y, 1, x, y, 7, "stone_bricks")
    s.cylinder(7.0, 7.0, 5.9, 7, 7, "deepslate_tiles")
    s.cylinder(7.0, 7.0, 3.6, 8, 11, "white_terracotta")
    s.dome(7.0, 7.0, 12, 3.2, "oxidized_copper")
    s.fill(6, 6, 15, 6, 6, 17, "gold_block", "post")
    for y in (4, 7, 10):
        V.window(s, 12, y, 4, "+x", "yellow_stained_glass")
    V.door(s, 6, 12, 1, "+y", "dark_oak", double=True)
    return s


def vikings() -> V.Structure:  # Borgund stave church: stacked dark shingle roofs
    s = _w("wonder_vikings")
    _plinth(s, "cobblestone")
    s.fill(3, 3, 1, 10, 10, 4, "dark_oak_planks")
    for x, y in ((3, 3), (3, 10), (10, 3), (10, 10)):
        s.fill(x, y, 1, x, y, 4, "dark_oak_log")
    V.door(s, 6, 10, 1, "+y", "dark_oak", double=True)
    z = 5
    for lo, hi in ((2, 11), (3, 10), (4, 9), (5, 8)):
        V.hip_roof(s, lo, hi, lo, hi, z, "spruce_planks", overhang=0)
        z += 2
        s.fill(lo + 1, lo + 1, z - 1, hi - 1, hi - 1, z, "dark_oak_planks")
    s.cone(6.5, 6.5, z + 1, 1.5, "spruce_planks", step=0.3)
    for x, y in ((2, 2), (11, 2), (2, 11), (11, 11)):  # dragon heads on the eaves
        s.set(x, y, 6, "dark_oak_log")
        s.set(x, y, 7, "dark_oak_planks", "post")
    team_banner(s, 10.95, 6.5, 4, "+x", seed="vk", height=20)
    return s


def celts() -> V.Structure:  # Rock of Cashel: a ruined keep-church on a crag with a round tower
    s = _w("wonder_celts")
    for x in range(N):
        for y in range(N):
            h = 1 + int(2 * np.exp(-((x - 6) ** 2 + (y - 6) ** 2) / 40))
            s.fill(x, y, 0, x, y, h - 1, "stone" if (x + y) % 5 else "mossy_cobblestone")
    s.fill(3, 2, 3, 10, 7, 8, "mossy_stone_bricks")
    V.gable_roof(s, 3, 10, 2, 7, 9, "deepslate_tiles", "mossy_stone_bricks", axis="x", overhang=0)
    s.fill(4, 8, 3, 8, 11, 7, "stone_bricks")
    V.crenellate(s, 4, 8, 8, 11, 8, "mossy_stone_bricks")
    s.cylinder(11.5, 11.5, 1.4, 3, 14, "cobblestone")
    s.cone(11.5, 11.5, 15, 1.5, "deepslate_tiles", step=0.4)
    V.window(s, 12, 11, 11, "+x")
    return s


def byzantines() -> V.Structure:  # Hagia Sophia: great dome, half domes, four minarets
    return domed("wonder_byzantines", "orange_terracotta", "light_gray_terracotta", 4, "smooth_stone",
                 half_domes=True)


def persians() -> V.Structure:  # Taq Kasra: the great brick arch between arcaded wings
    s = _w("wonder_persians")
    _plinth(s, "smooth_sandstone")
    s.fill(3, 3, 1, 10, 11, 12, "cut_sandstone")  # the arch block
    s.carve(5, 5, 1, 8, 11, 8)  # the vault
    for x in (5, 8):
        s.set(x, 11, 8, "smooth_sandstone", "ustair_" + ("+x" if x == 5 else "-x"))
    s.set(6, 11, 9, "smooth_sandstone", "ustair_+x")
    s.set(7, 11, 9, "smooth_sandstone", "ustair_-x")
    s.carve(6, 5, 9, 7, 11, 9)
    s.set(6, 11, 9, "smooth_sandstone", "ustair_+x")
    s.set(7, 11, 9, "smooth_sandstone", "ustair_-x")
    for x0, x1 in ((0, 2), (11, 13)):  # lower wings with a blind arcade
        s.fill(x0, 5, 1, x1, 11, 7, "sandstone")
        for x in range(x0, x1 + 1):
            if x % 2 == 0:
                s.set(x, 11, 3, "chiseled_sandstone")
                s.set(x, 11, 6, "chiseled_sandstone")
        for y in range(5, 12, 2):
            s.set(x1, y, 4, "chiseled_sandstone")
    for x in range(3, 11, 2):
        s.set(x, 11, 11, "chiseled_sandstone")
    for y in range(3, 12, 2):
        s.set(10, y, 10, "chiseled_sandstone")
    s.fill(5, 5, 1, 8, 9, 1, "blue_wool", "carpet")
    lantern(s, 6.5, 8.5, 7)
    return s


def saracens() -> V.Structure:  # the spiral minaret of Samarra beside a courtyard mosque
    s = _w("wonder_saracens")
    _plinth(s, "sandstone")
    s.ring(0, 0, 13, 13, 1, 3, "cut_sandstone")
    V.crenellate(s, 0, 13, 0, 13, 4, "smooth_sandstone")
    V.door(s, 6, 13, 1, "+y", "acacia", double=True)
    z = 1
    for r in (4.6, 4.0, 3.4, 2.8, 2.2, 1.7, 1.2):
        s.cylinder(7.0, 7.0, r, z, z + 1, "sandstone")
        s.cylinder(7.0, 7.0, r + 0.6, z + 1, z + 1, "smooth_sandstone")
        z += 2
    s.cylinder(7.0, 7.0, 1.0, z, z + 1, "cut_sandstone")
    s.set(6, 6, z + 2, "gold_block")
    return s


def turks() -> V.Structure:  # Selimiye: a great dome with four needle minarets
    return domed("wonder_turks", "smooth_stone", "deepslate_tiles", 4, "polished_andesite", accent="gold_block")


def japanese() -> V.Structure:  # Todai-ji: a vast two-roofed hall
    s = _w("wonder_japanese")
    _plinth(s, "stone_bricks", steps=2)
    s.fill(2, 3, 2, 11, 10, 5, "white_terracotta")
    for x in range(2, 12, 3):
        s.fill(x, 10, 2, x, 10, 5, "dark_oak_log")
        s.fill(11, x + 1, 2, 11, x + 1, 5, "dark_oak_log")
    V.door(s, 6, 10, 2, "+y", "dark_oak", double=True)
    V.pagoda_roof(s, 2, 11, 3, 10, 6, "deepslate_tiles", "gold_block")
    s.fill(4, 5, 7, 9, 8, 8, "white_terracotta")
    V.pagoda_roof(s, 4, 9, 5, 8, 9, "deepslate_tiles", "gold_block")
    V.hip_roof(s, 4, 9, 5, 8, 10, "deepslate_tiles", overhang=0)
    for x, y in ((1, 12), (12, 1)):
        lantern(s, x + 0.5, y + 0.5, 1)
    return s


def chinese() -> V.Structure:  # the Temple of Heaven: a round hall under three blue roofs
    return pagoda("wonder_chinese", 3, "red_terracotta", "lapis_block", "gold_block", "quartz", round_temple=True)


def mongols() -> V.Structure:  # a white stupa with a golden spire
    s = _w("wonder_mongols")
    _plinth(s, "smooth_stone", steps=2)
    s.fill(2, 2, 2, 11, 11, 3, "quartz")
    s.dome(7.0, 7.0, 4, 4.4, "white_concrete", squash=0.9)
    s.fill(5, 5, 8, 8, 8, 8, "gold_block")
    for z, r in zip(range(9, 14), (1.8, 1.5, 1.2, 0.9, 0.6)):
        s.cylinder(7.0, 7.0, r, z, z, "gold_block")
    for x, y in ((1, 1), (12, 1), (1, 12), (12, 12)):
        s.fill(x, y, 2, x, y, 4, "white_concrete")
        s.set(x, y, 5, "gold_block", "cube_small")
    for x in range(2, 12, 2):  # prayer flags
        s.set(x, 12, 4, ["red_wool", "blue_wool", "yellow_wool", "green_wool", "white_wool"][x % 5], "carpet")
    return s


def koreans() -> V.Structure:  # Hwangnyongsa: a nine-storey wooden pagoda
    return pagoda("wonder_koreans", 9, "spruce_planks", "deepslate_tiles", "red_terracotta", "stone_bricks")


def spanish() -> V.Structure:  # Torre del Oro: a many-sided golden tower
    s = _w("wonder_spanish")
    _plinth(s, "smooth_sandstone")
    s.cylinder(7.0, 7.0, 5.8, 1, 8, "cut_sandstone")
    V.crenellate(s, 1, 12, 1, 12, 9, "sandstone")
    s.cylinder(7.0, 7.0, 3.4, 9, 14, "yellow_terracotta")
    s.cylinder(7.0, 7.0, 3.8, 15, 15, "smooth_sandstone")
    s.cylinder(7.0, 7.0, 2.0, 16, 17, "yellow_terracotta")
    s.dome(7.0, 7.0, 18, 2.0, "gold_block")
    for y in (4, 7, 10):
        V.window(s, 12, y, 5, "+x")
    V.door(s, 6, 12, 1, "+y", "spruce", double=True)
    return s


def huns() -> V.Structure:  # a great timber hall with a tall tent roof
    s = _w("wonder_huns")
    _plinth(s, "coarse_dirt")
    s.fill(2, 2, 1, 11, 11, 5, "spruce_log")
    s.fill(3, 3, 1, 10, 10, 5, "spruce_planks")
    V.door(s, 6, 11, 1, "+y", "spruce", double=True)
    s.cone(7.0, 7.0, 6, 6.8, "brown_wool", step=0.75)
    s.fill(6, 6, 15, 6, 6, 17, "spruce_log", "post")
    for x, y in ((0, 0), (13, 0), (0, 13), (13, 13)):
        s.fill(x, y, 0, x, y, 3, "spruce_log", "post")
        s.set(x, y, 4, "bone_block", "cube_small")
    for x in (3, 10):
        team_banner(s, x, 11.95, 5, "+y", seed=f"hun{x}", height=26, pattern="stripe")
    return s


def aztecs() -> V.Structure:  # Templo Mayor: twin shrines on a step pyramid
    return step_pyramid("wonder_aztecs", "stone_bricks", "cracked_stone_bricks", shrines=2, steps=5,
                        stair="stone_bricks")


def mayans() -> V.Structure:  # the Temple of the Great Jaguar: steep, with a roof comb
    return step_pyramid("wonder_mayans", "mossy_stone_bricks", "stone_bricks", shrines=1, steps=6,
                        stair="mossy_stone_bricks", comb=True)


WONDERS = {"B": britons, "R": franks, "H": goths, "U": teutons, "I": vikings, "L": celts, "Y": byzantines,
           "P": persians, "S": saracens, "T": turks, "J": japanese, "Z": chinese, "N": mongols, "K": koreans,
           "C": spanish, "G": huns, "A": aztecs, "M": mayans}


def wonder(letter: str) -> V.Structure:
    return WONDERS.get(letter, britons)()


# --------------------------------------------------------------------------- scenario monuments

def dome_of_the_rock() -> V.Structure:
    s = _w("dome_of_the_rock", 11)
    _plinth(s, "smooth_stone", 11)
    s.cylinder(5.5, 5.5, 5.0, 1, 4, "light_blue_terracotta")
    s.cylinder(5.5, 5.5, 5.3, 5, 5, "white_terracotta")
    s.cylinder(5.5, 5.5, 2.8, 6, 7, "blue_terracotta")
    s.dome(5.5, 5.5, 8, 3.0, "gold_block")
    V.door(s, 5, 10, 1, "+y", "acacia")
    return s


def small_pyramid() -> V.Structure:
    return smooth_pyramid("small_pyramid", 11)


def large_pyramid() -> V.Structure:
    return smooth_pyramid("large_pyramid", 17)


def cathedral_monument() -> V.Structure:
    return cathedral("cathedral", "stone_bricks", "deepslate_tiles", spires=2)


def mosque(minarets: int = 2) -> V.Structure:
    return domed("mosque", "sandstone", "white_terracotta", minarets, "cut_sandstone")


def tower_of_flies() -> V.Structure:
    """A tall lighthouse-like tower (the Tower of Flies)."""
    s = _w("tower_of_flies", 8)
    s.fill(0, 0, 0, 7, 7, 0, "stone_bricks")
    s.cylinder(4.0, 4.0, 3.0, 1, 12, "stone_bricks")
    s.cylinder(4.0, 4.0, 3.5, 13, 13, "chiseled_stone_bricks")
    s.cylinder(4.0, 4.0, 2.0, 14, 15, "glowstone")
    s.cone(4.0, 4.0, 16, 2.2, "deepslate_tiles", step=0.5)
    for z in (4, 8):
        V.window(s, 7, 4, z, "+x")
    return s
