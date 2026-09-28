"""Which original AoE2 sprite (SLP id in graphics.drs) each of our renders replaces.

Ids come from the community SLP list documented by openage
(doc/media/aoc-slp-list.md); most unit sets follow the pattern
attack X, dying X+3, standing X+6, decaying X+7, moving X+10. At build time
every id is checked against the player's own game files, and frame and
angle counts are always taken from the game, never from this table.

Composite sprites (ram heads and wheels, ship sails, fishing nets...) are
listed in BLANK: they are replaced by empty frames so only our model shows.
The build also blanks deltas found in the .dat for the sprites we replace.
"""
from __future__ import annotations

from typing import NamedTuple


class Target(NamedTuple):
    slp: int
    unit: str
    action: str  # idle, walk, run, attack, work, carry, die, decay
    note: str = ""


def _set(unit: str, attack: int, die: int, idle: int, decay: int, walk: int) -> list[Target]:
    return [Target(attack, unit, "attack"), Target(die, unit, "die"), Target(idle, unit, "idle"),
            Target(decay, unit, "decay"), Target(walk, unit, "walk")]


def _std(unit: str, x: int) -> list[Target]:
    """The common numbering: attack x, die x+3, idle x+6, decay x+7, walk x+10."""
    return _set(unit, x, x + 3, x + 6, x + 7, x + 10)


TARGETS: list[Target] = [
    # ---------------------------------------------------------------- villagers (male and female share a model)
    Target(1479, "villager", "idle", "male"), Target(1484, "villager", "walk", "male"),
    Target(1473, "villager_repairer", "attack", "male fighting"), Target(1476, "villager", "die", "male"),
    Target(1481, "villager", "decay", "male"),
    Target(1388, "villager", "idle", "female"), Target(1392, "villager", "walk", "female"),
    Target(1382, "villager_repairer", "attack", "female fighting"), Target(1385, "villager", "die", "female"),
    Target(1389, "villager", "decay", "female"),
    # builder / repairer
    *_set("villager_builder", 1496, 1490, 1493, 1495, 1499),
    Target(1874, "villager_builder", "work", "female"), Target(1398, "villager_builder", "die", "female"),
    Target(1401, "villager_builder", "idle", "female"), Target(1402, "villager_builder", "decay", "female"),
    Target(1405, "villager_builder", "walk", "female"),
    # farmer
    *_set("villager_farmer", 1512, 1506, 1509, 1511, 1515),
    Target(3842, "villager_farmer", "work", "male sowing"), Target(3840, "villager_farmer", "work", "female sowing"),
    # hunter
    *_set("villager_hunter", 1518, 1522, 1525, 1527, 1531),
    Target(1519, "villager_hunter", "carry", "male meat"), Target(1528, "villager_hunter", "work", "male butcher"),
    Target(1421, "villager_hunter", "attack", "female"), Target(1424, "villager_hunter", "die", "female"),
    Target(1427, "villager_hunter", "idle", "female"), Target(1428, "villager_hunter", "decay", "female"),
    Target(1431, "villager_hunter", "walk", "female"), Target(1877, "villager_hunter", "carry", "female meat"),
    Target(1878, "villager_hunter", "work", "female butcher"),
    # miners (gold and stone share the pick; only the carried block differs)
    *_set("villager_stone_miner", 1560, 1555, 1558, 1559, 1563),
    Target(2117, "villager_gold_miner", "carry", "male gold"), Target(1552, "villager_stone_miner", "carry", "male stone"),
    Target(1880, "villager_stone_miner", "attack", "female"), Target(1450, "villager_stone_miner", "die", "female"),
    Target(1453, "villager_stone_miner", "idle", "female"), Target(1454, "villager_stone_miner", "decay", "female"),
    Target(1457, "villager_stone_miner", "walk", "female"), Target(2218, "villager_gold_miner", "carry", "female gold"),
    Target(1879, "villager_stone_miner", "carry", "female stone"),
    Target(3425, "villager_gold_miner", "die", "male"), Target(3428, "villager_gold_miner", "idle", "male"),
    Target(3429, "villager_gold_miner", "decay", "male"), Target(3432, "villager_gold_miner", "walk", "male"),
    Target(3412, "villager_gold_miner", "die", "female"), Target(3415, "villager_gold_miner", "idle", "female"),
    Target(3416, "villager_gold_miner", "decay", "female"), Target(3419, "villager_gold_miner", "walk", "female"),
    # lumberjack
    *_set("villager_lumberjack", 1535, 1539, 1542, 1544, 1548),
    Target(1545, "villager_lumberjack", "attack", "male, second copy"),
    Target(1536, "villager_lumberjack", "carry", "male wood"),
    Target(1434, "villager_lumberjack", "attack", "female"), Target(1884, "villager_lumberjack", "attack", "female"),
    Target(1437, "villager_lumberjack", "die", "female"), Target(1440, "villager_lumberjack", "idle", "female"),
    Target(1441, "villager_lumberjack", "decay", "female"), Target(1444, "villager_lumberjack", "walk", "female"),
    Target(1883, "villager_lumberjack", "carry", "female wood"),
    # forager
    Target(2586, "villager_forager", "idle", "male"), Target(2592, "villager_forager", "walk", "male"),
    Target(2589, "villager_forager", "work", "male"), Target(2583, "villager_forager", "die", "male"),
    Target(2588, "villager_forager", "decay", "male"), Target(3479, "villager_forager", "work", "male"),
    Target(2571, "villager_forager", "idle", "female"), Target(1414, "villager_forager", "carry", "female"),
    Target(1418, "villager_forager", "carry", "female"), Target(2576, "villager_forager", "walk", "female"),
    Target(2573, "villager_forager", "work", "female"), Target(1875, "villager_forager", "walk", "female"),
    Target(1876, "villager_forager", "work", "female"), Target(2568, "villager_forager", "die", "female"),
    Target(1411, "villager_forager", "die", "female"), Target(1415, "villager_forager", "decay", "female"),
    Target(2572, "villager_forager", "decay", "female"), Target(4602, "villager_forager", "walk", "female"),
    # shepherd
    Target(3684, "villager_shepherd", "idle", "male"), Target(3686, "villager_shepherd", "walk", "male"),
    Target(3843, "villager_shepherd", "work", "male"), Target(3682, "villager_shepherd", "attack", "male"),
    Target(3683, "villager_shepherd", "die", "male"), Target(4649, "villager_shepherd", "decay", "male"),
    Target(3679, "villager_shepherd", "idle", "female"), Target(3681, "villager_shepherd", "walk", "female"),
    Target(3841, "villager_shepherd", "work", "female"), Target(3677, "villager_shepherd", "attack", "female"),
    Target(3678, "villager_shepherd", "die", "female"), Target(4656, "villager_shepherd", "decay", "female"),
    # fisherman
    Target(3980, "villager_fisherman", "carry", "male fish"),
    # monks and king
    *_set("monk", 768, 771, 774, 775, 779), Target(776, "monk", "attack", "second copy"),
    Target(3824, "monk", "die", "with relic"), Target(3827, "monk", "idle", "with relic"),
    Target(3831, "monk", "walk", "with relic"),
    Target(4865, "missionary", "attack"), Target(4869, "missionary", "attack", "heal"),
    Target(4866, "missionary", "die"), Target(4867, "missionary", "idle"), Target(4868, "missionary", "decay"),
    Target(4870, "missionary", "walk"),
    *_std("king", 1761),
    # ---------------------------------------------------------------- infantry
    *_std("militia", 987), *_std("man_at_arms", 1038), *_std("long_swordsman", 1175),
    *_std("two_handed", 2800), *_std("champion", 3085),
    *_std("spearman", 867), *_std("pikeman", 2826),
    *_set("eagle_warrior", 4826, 4827, 4828, 4829, 4830),
    # ---------------------------------------------------------------- archers
    *_std("archer", 2), *_std("crossbowman", 186), *_std("arbalest", 2698),
    *_std("skirmisher", 1644), *_std("elite_skirmisher", 607),
    *_set("hand_cannoneer", 581, 584, 587, 588, 591),
    # ---------------------------------------------------------------- cavalry
    *_std("scout_cavalry", 2079), *_std("light_cavalry", 2998), *_set("hussar", 4853, 4854, 4855, 4856, 4857),
    *_std("knight", 663), *_std("cavalier", 849), *_std("paladin", 3072),
    *_std("camel", 676), *_std("heavy_camel", 2762),
    *_std("cavalry_archer", 320), *_std("heavy_cavalry_archer", 3757),
    # ---------------------------------------------------------------- unique units
    *_set("longbowman", 702, 705, 708, 710, 713), *_std("cataphract", 199), *_std("woad_raider", 1592), *_std("chu_ko_nu", 215),
    *_std("throwing_axeman", 1051), *_set("huskarl", 4537, 4538, 4539, 4540, 4541), *_std("samurai", 974),
    *_std("mangudai", 782), *_std("war_elephant", 795), *_std("mameluke", 351), *_std("teutonic_knight", 1188),
    *_std("janissary", 634), *_set("berserk", 4373, 4376, 4379, 4393, 4383),
    Target(4386, "berserk", "attack", "second copy"), Target(4389, "berserk", "die", "second copy"),
    Target(4392, "berserk", "idle", "second copy"), Target(4396, "berserk", "walk", "second copy"),
    *_set("jaguar_warrior", 4858, 4859, 4860, 4861, 4862), *_set("tarkan", 4916, 4917, 4918, 4919, 4920),
    *_set("plumed_archer", 4871, 4872, 4873, 4874, 4875), *_std("conquistador", 4716),
    *_std("war_wagon", 5204),
    Target(5218, "turtle_ship", "attack"), Target(5219, "turtle_ship", "idle"), Target(5220, "turtle_ship", "walk"),
    Target(689, "longboat", "idle", "used for standing, moving and attacking"),
    # ---------------------------------------------------------------- siege
    # the walk sprites here are the turning wheels; the static body is a layer and gets blanked
    *_std("battering_ram", 173), *_std("capped_ram", 1683), *_std("siege_ram", 3029),
    *_std("mangonel", 716), *_set("onager", 3017, 3020, 3023, 4168, 3026), *_std("siege_onager", 3553),
    *_std("scorpion", 936), *_std("heavy_scorpion", 2813),
    *_set("bombard_cannon", 61, 64, 67, 68, 71),
    Target(1237, "trebuchet", "attack"), Target(1241, "trebuchet", "die"), Target(1244, "trebuchet", "idle"),
    Target(1246, "trebuchet", "decay"), Target(1249, "trebuchet", "walk", "packing up"),
    Target(2279, "trebuchet", "walk", "packed"),
    Target(4572, "trebuchet", "die", "packed"), Target(4573, "trebuchet", "decay", "packed"),
    Target(1122, "trade_cart", "idle", "empty"), Target(4486, "trade_cart", "walk", "empty"),
    Target(1119, "trade_cart", "die", "empty"), Target(1124, "trade_cart", "decay", "empty"),
    Target(4608, "trade_cart", "idle", "loaded"), Target(1127, "trade_cart", "walk", "loaded"),
    Target(4607, "trade_cart", "die", "loaded"), Target(4609, "trade_cart", "decay", "loaded"),
    # ---------------------------------------------------------------- ships (hulls; sails, shadows are blanked)
    Target(444, "fishing_ship", "idle"), Target(449, "fishing_ship", "walk"), Target(438, "fishing_ship", "attack"),
    Target(441, "fishing_ship", "die"), Target(445, "fishing_ship", "decay"),
    Target(4331, "transport_ship", "idle"), Target(4254, "trade_cog", "idle"), Target(4256, "galley", "idle"),
    Target(4300, "war_galley", "idle"), Target(4199, "galleon", "idle"),
    Target(4255, "fire_ship", "idle"), Target(4268, "fast_fire_ship", "idle"),
    Target(4299, "demolition_ship", "idle"), Target(4253, "heavy_demolition_ship", "idle"),
    Target(4244, "cannon_galleon", "idle", "the elite cannon galleon shares this hull"),
    # ---------------------------------------------------------------- animals
    Target(3626, "sheep", "die"), Target(3629, "sheep", "idle"), Target(3631, "sheep", "decay"),
    Target(3634, "sheep", "walk"), Target(3623, "sheep", "idle", "herded"),
    *_set("wolf", 1629, 1632, 1635, 1637, 1640), Target(1636, "wolf", "run"),
    Target(5165, "turkey", "idle"), Target(5167, "turkey", "walk"), Target(5164, "turkey", "run"),
    Target(5166, "turkey", "decay"),
    Target(339, "deer", "die"), Target(344, "deer", "decay"), Target(348, "deer", "walk"), Target(343, "deer", "run"),
    Target(342, "deer", "idle"), Target(336, "deer", "idle", "attack sprite"),
    # ---------------------------------------------------------------- petard (its death is the shared explosion)
    Target(4497, "petard", "idle"), Target(4498, "petard", "walk"),
    *_set("wild_boar", 2555, 2556, 2557, 2558, 2559),
]

# Layered parts of the originals that must disappear once the base sprite is ours.
BLANK: list[tuple[int, str]] = [
    (446, "fishing ship nets"),
    (5238, "war wagon body"), (5239, "war wagon body"), (5240, "war wagon body"),
    (5168, "turtle ship shadow"), (5176, "turtle ship shadow"), (5182, "turtle ship shadow"),
    # ship hull shadows (also used by the sinking animations, which is why the .dat check keeps them)
    *[(s, "ship shadow") for s in (4336, 4501, 4502, 4503, 4508, 4509, 4510, 4514, 4515, 4516, 4517)],
    # sails, by civilisation style (East, Asian, Middle Eastern, West, Meso)
    *[(s, "ship sail") for s in (*range(4224, 4244), *range(4301, 4329), *range(4598, 4602),
                                 *range(5092, 5100), 4935, 4936)],
]

# Units whose sprite ids are not in the community list: matched at build time by the
# internal graphic name in the player's .dat (prefix + action suffix, e.g. HALBD_AN).
NAME_PREFIXES: dict[str, list[str]] = {
    "halberdier": ["HALB", "HLBRD", "HALBD", "HLBDR"],
    "javelina": ["JAVEL", "JAVLN", "PECCA", "JVLNA"],
    "elite_eagle_warrior": ["EEAGL", "EAGLE_E", "UEAGL"],
    "petard": ["PETARD", "PETRD", "SABOT"],
}
# Units drawn by another unit's sprites in the original game.
SHARED = {"elite_cannon_galleon": "cannon_galleon"}

SUFFIX_ACTIONS = {"AN": "attack", "DN": "die", "FN": "idle", "SN": "decay", "WN": "walk", "RN": "run",
                  "CN": "carry"}
