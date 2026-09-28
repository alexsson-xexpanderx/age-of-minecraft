"""Architecture styles: AoE2's building sets as Minecraft village styles.

AoE2 draws buildings in five regional styles (plus a shared Dark Age look).
Each becomes a Minecraft village biome style, and each age upgrades the
materials, so you can still tell civilisations and ages apart at a glance:

    G  Dark Age (all civs)         log cabins with thatched (hay) roofs
    W  West European               Plains village: oak, cobblestone, brick roofs
    E  Central/North European      Taiga village: spruce, mossy stone, slate roofs
    M  Middle Eastern              Desert village: sandstone, terracotta, domes
    F  Asian                       cherry wood, white walls, dark upturned roofs
    X  Meso-American               Jungle temple: mossy stone, jungle wood, gold

The letters are the ones used in the graphic names of the game's .dat.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Style:
    key: str
    name: str
    wood: str  # plank family: "<wood>_planks", "<wood>_log"
    base: str  # foundation course
    wall: str  # main walls
    wall_hi: str  # upper floors and gables
    trim: str  # corner pillars and beams
    roof: str  # block used for roof stairs
    roof_cap: str  # ridge / top slabs
    roof_type: str  # gable, hip, flat, pagoda
    floor: str  # ground paving around buildings
    stone: str  # military stone (towers, castles, walls)
    stone2: str  # stone detailing
    accent: str  # decorative blocks (gold, glazed...)
    glass: str
    fence: str  # fence wood
    cloth: str  # awnings, rugs
    dome: str  # domes and spires

    @property
    def planks(self) -> str:
        return f"{self.wood}_planks"

    @property
    def log(self) -> str:
        return f"{self.wood}_log"


G = Style("G", "Dark Age", "oak", "cobblestone", "oak_log", "oak_planks", "stripped_oak_log", "hay", "hay",
          "gable", "dirt_path", "cobblestone", "mossy_cobblestone", "oak_log", "glass", "oak_planks",
          "white_wool", "hay")
W = Style("W", "West European", "oak", "cobblestone", "oak_planks", "white_terracotta", "oak_log", "bricks",
          "bricks", "gable", "gravel", "stone_bricks", "cobblestone", "red_wool", "glass", "oak_planks",
          "red_wool", "bricks")
E = Style("E", "Central European", "spruce", "mossy_cobblestone", "spruce_planks", "spruce_planks",
          "spruce_log", "deepslate_tiles", "deepslate_tiles", "gable", "podzol", "stone_bricks",
          "mossy_stone_bricks", "spruce_log", "glass", "spruce_planks", "blue_wool", "deepslate_tiles")
M = Style("M", "Middle Eastern", "acacia", "cut_sandstone", "sandstone", "smooth_sandstone", "cut_sandstone",
          "smooth_sandstone", "cut_sandstone", "flat", "sand", "sandstone", "chiseled_sandstone",
          "glazed_terracotta", "glass", "acacia_planks", "orange_wool", "white_terracotta")
F = Style("F", "Asian", "cherry", "stone_bricks", "white_terracotta", "white_terracotta", "red_terracotta",
          "deepslate_tiles", "deepslate_tiles", "pagoda", "gravel", "stone_bricks", "smooth_stone",
          "red_terracotta", "glass", "bamboo_planks", "red_wool", "deepslate_tiles")
X = Style("X", "Meso-American", "jungle", "mossy_cobblestone", "jungle_planks", "mossy_stone_bricks",
          "jungle_log", "hay", "hay", "flat", "coarse_dirt", "mossy_stone_bricks", "chiseled_stone_bricks",
          "gold_block", "glass", "jungle_planks", "lime_wool", "mossy_cobblestone")

STYLES = {s.key: s for s in (G, W, E, M, F, X)}


def style_for(key: str, age: int) -> Style:
    """The style's materials for an age (1 Dark, 2 Feudal, 3 Castle, 4 Imperial)."""
    s = STYLES.get(key, W)
    if s.key == "G" or age <= 1:
        return G
    if age == 2:
        return {
            "W": replace(s, wall="oak_planks", wall_hi="oak_planks", roof="spruce_planks", roof_cap="spruce_planks"),
            "E": replace(s, base="cobblestone", roof="spruce_planks", roof_cap="spruce_planks"),
            "M": replace(s, base="sandstone", wall="sandstone", wall_hi="smooth_sandstone"),
            "F": replace(s, base="cobblestone", wall="bamboo_planks", wall_hi="white_terracotta",
                         roof="dark_oak_planks", roof_cap="dark_oak_planks"),
            "X": replace(s, base="mossy_cobblestone", wall="jungle_planks", wall_hi="jungle_planks"),
        }[s.key]
    if age == 3:
        return {
            "W": replace(s, base="stone_bricks", wall="white_terracotta", wall_hi="white_terracotta",
                         trim="dark_oak_log"),
            "E": replace(s, base="stone_bricks", wall="spruce_planks"),
            "M": s,
            "F": s,
            "X": replace(s, wall="mossy_stone_bricks", wall_hi="chiseled_stone_bricks"),
        }[s.key]
    return {  # Imperial: polished stone, gold and banners
        "W": replace(s, base="polished_andesite", wall="white_terracotta", wall_hi="white_terracotta",
                     trim="dark_oak_log", stone="polished_andesite", accent="gold_block"),
        "E": replace(s, base="polished_andesite", wall="stone_bricks", wall_hi="spruce_planks",
                     stone="deepslate_bricks", accent="gold_block"),
        "M": replace(s, base="smooth_sandstone", wall="smooth_sandstone", wall_hi="quartz", dome="oxidized_copper",
                     accent="gold_block"),
        "F": replace(s, base="polished_andesite", wall="white_terracotta", wall_hi="quartz", accent="gold_block"),
        "X": replace(s, base="chiseled_stone_bricks", wall="mossy_stone_bricks", wall_hi="chiseled_stone_bricks",
                     accent="gold_block"),
    }[s.key]
