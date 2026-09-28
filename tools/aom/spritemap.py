"""Which original buildings, walls, trees and decorations get replaced, found by graphic name.

The .dat names its graphics systematically, e.g. BRKS3NNM = barracks (BRKS),
Castle Age (3), main sprite (NN), Middle Eastern style (M). Layers next to
the main sprite (N0 = shadow, N1 = flag or smoke, N2.. = extra pieces) are
blanked because our models draw their own shadows and decorations, except
for animated layers we redraw (mill sails, forge smoke, university flag).

Rules run against the player's own .dat at build time, so every sprite is
found by its real id. `plan(graphics)` returns the sprites to render and
the layers to blank.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .voxel import BLOCK

STYLE_OF = {"E": "E", "F": "F", "M": "M", "W": "W", "X": "X", "G": "G", "": "G"}
SIMPLE = {"ARRG", "BLAC", "BRKS", "STBL", "MRKT", "SIWS", "DOCK", "PORT", "TDWS", "UNIV", "HOUS", "SMIL",
          "MINE", "CRCH", "CSTL", "MILL", "RTWC", "FARM"}
ANIMATED_LAYER = {"MILL": "overlay", "BLAC": "overlay", "UNIV": "overlay"}


@dataclass
class Sprite:
    slp: int
    spec: dict
    source: str  # the graphic name it was found by
    note: str = ""


@dataclass
class Plan:
    sprites: dict[int, Sprite] = field(default_factory=dict)
    blanks: dict[int, str] = field(default_factory=dict)

    def add(self, slp_id: int, spec: dict, source: str, note: str = "") -> None:
        if slp_id > 0 and slp_id not in self.sprites:
            self.sprites[slp_id] = Sprite(slp_id, spec, source, note)
            self.blanks.pop(slp_id, None)

    def blank(self, slp_id: int, why: str) -> None:
        if slp_id > 0 and slp_id not in self.sprites:
            self.blanks.setdefault(slp_id, why)


def _age(code: str, digit: str, style: str) -> int:
    return max(1, min(4, int(digit)))


def screen_to_blocks(ox: float, oy: float) -> float:
    """Ground distance (in blocks) of a screen offset, for the building view."""
    my = (ox / 1.0607 + oy / 0.5303) / 2
    mx = (oy / 0.5303 - ox / 1.0607) / 2
    return float((mx * mx + my * my) ** 0.5) / BLOCK


def plan(graphics: dict, taken: set[int] = frozenset()) -> Plan:
    """Map the .dat's graphics to static sprites. `taken` are SLPs already used by units."""
    P = Plan()
    by_name = {g.name.upper(): g for g in graphics.values()}
    by_slp: dict[int, list] = {}
    for g in graphics.values():
        by_slp.setdefault(g.slp, []).append(g)

    def owned_only_by(slp_id: int, pattern: str) -> bool:
        """True if every graphic using this SLP as its own sprite matches `pattern`."""
        return all(re.match(pattern, g.name.upper()) for g in by_slp.get(slp_id, []))

    def add(g, spec, note="", family=None):
        """Replace g's sprite, unless it is shared with graphics of another kind (e.g. the ship flags)."""
        if g.slp in taken or not owned_only_by(g.slp, family or "^" + re.escape(g.name.upper()[:4])):
            return
        P.add(g.slp, spec, g.name, note)

    def blank(g, why, pattern=None):
        if g.slp in taken:
            return
        if pattern is None or owned_only_by(g.slp, pattern):
            P.blank(g.slp, f"{why} ({g.name})")

    for g in sorted(graphics.values(), key=lambda g: g.id):
        name = g.name.upper()
        if g.slp <= 0:
            continue

        # ---------------------------------------------------------------- buildings: CODE age NN [G] style
        m = re.match(r"^([A-Z]{4})(\d)NN(G?)([EFMWX]?)$", name)
        if m and m.group(1) in SIMPLE | {"WCTW"}:
            code, digit, _, st = m.groups()
            style = STYLE_OF[st or "G"]
            spec = {"model": "building", "code": code, "style": style, "age": _age(code, digit, style),
                    "mode": "variants" if code in ("HOUS", "FARM") else "static"}
            if code == "WCTW":
                spec.update(level=int(digit), age=min(4, int(digit) + 1))
            if code in ANIMATED_LAYER:
                spec["part"] = "body"
            if code == "RTWC":
                spec["anchor"] = f"RTWC{digit}CN{st or 'G'}"
            add(g, spec)
            continue
        m = re.match(r"^([A-Z]{4})(\d)N([0-9Z])(G?)([EFMWX]?)$", name)
        if m and m.group(1) in SIMPLE | {"WCTW"}:
            code, digit, layer, _, st = m.groups()
            style = STYLE_OF[st or "G"]
            if code in ANIMATED_LAYER and layer == "1" and g.frame_count > 1:
                spec = {"model": "building", "code": code, "style": style, "age": _age(code, digit, style),
                        "mode": "overlay"}
                add(g, spec, "animated layer")
                continue
            blank(g, "layer of a replaced building", rf"^{code}\d")
            continue
        if name == "BLACSMK":
            add(g, {"model": "building", "code": "BLAC", "style": "W", "age": 2, "mode": "overlay"}, "forge smoke")
            continue

        # ---------------------------------------------------------------- wonders and monuments
        m = re.match(r"^WNDR0NN([A-Z])$", name)
        if m:
            add(g, {"model": "wonder", "letter": m.group(1), "mode": "static"})
            continue
        if re.match(r"^WNDR0N[01][A-Z]$", name):
            blank(g, "layer of a replaced wonder", r"^WNDR")
            continue
        mon = next((mon for pat, mon in ((r"^HDOR\dNN$", "dome_of_the_rock"), (r"^HPYR\dNN$", "small_pyramid"),
                                          (r"^HGPR\dNN$", "large_pyramid"), (r"^SPECR0NN$", "cathedral_monument"),
                                          (r"^MSQUE\dNN$", "mosque"), (r"^HT(OF|AT)NNG$", "tower_of_flies"))
                    if re.match(pat, name)), None)
        if mon:
            add(g, {"model": "monument", "name": mon, "mode": "static"}, family="^H|^SPECR|^MSQUE")
            continue
        if re.match(r"^HT(OF|AT)N0G$", name):
            blank(g, "monument shadow")
            continue

        # ---------------------------------------------------------------- walls
        m = re.match(r"^WALL([123])N([N01])([EFMWXG]?)$", name)
        if m:
            kind = {"1": "palisade", "2": "stone", "3": "fortified"}[m.group(1)]
            style = STYLE_OF[m.group(3) or "G"]
            wall_layer = "1" if kind == "palisade" else "N"
            if m.group(2) == wall_layer:
                add(g, {"model": "wall", "kind": kind, "style": style, "mode": "match"})
            else:
                blank(g, "wall shadow or flag", r"^WALL")
            continue
        m = re.match(r"^WDS([12])([ABC])N([N0])([EFMWX])$", name)
        if m:
            if m.group(3) == "N":
                add(g, {"model": "wall", "kind": "stone" if m.group(1) == "1" else "fortified",
                        "style": m.group(4), "damage": "ABC".index(m.group(2)) + 1, "mode": "match"},
                    "damaged wall")
            else:
                blank(g, "damaged wall shadow", r"^WDS")
            continue
        m = re.match(r"^WCON([23])N([N0])([EFMWX])$", name)
        if m:
            if m.group(2) == "N":
                add(g, {"model": "wall", "kind": "stone" if m.group(1) == "2" else "fortified",
                        "style": m.group(3), "mode": "match", "stages": True}, "wall being built")
            else:
                blank(g, "wall construction shadow", r"^WCON")
            continue

        # ---------------------------------------------------------------- gates
        m = re.match(r"^GT([A-D])([ABC])([23])N([N01])([EFMWX])$", name)
        if m:
            orient, state, digit, layer, st = m.groups()
            age = int(digit)
            if layer != "N":
                blank(g, "gate shadow or layer", r"^GT")
                continue
            if state == "C":
                add(g, {"model": "gate_tower", "style": st, "age": age, "mode": "static"}, family="^GT")
            else:
                from .fortifications import GATE_DIRS
                spec = {"model": "gate", "style": st, "age": age, "direction": GATE_DIRS[orient],
                        "open": state == "B", "mode": "static", "gate_parent": f"GT{orient}X{digit}NN{st}"}
                add(g, spec, family="^GT")
            continue
        if re.match(r"^GTAC[23]N1G$", name):
            blank(g, "gate tower flag", r"^GT")
            continue
        m = re.match(r"^GT([A-D])X([23])C([N0])([EFMWX])$", name)
        if m:
            from .fortifications import GATE_DIRS
            if m.group(3) == "N":
                add(g, {"model": "gate_site", "style": m.group(4), "age": int(m.group(2)),
                        "direction": GATE_DIRS[m.group(1)], "mode": "variants"}, "gate being built")
            else:
                blank(g, "gate construction shadow", r"^GT")
            continue

        # ---------------------------------------------------------------- towers, outpost
        if re.match(r"^WCTWX1NNG$", name):
            add(g, {"model": "outpost", "mode": "static"})
            continue
        if re.match(r"^WCTWX1N0G$", name):
            blank(g, "outpost shadow")
            continue

        # ---------------------------------------------------------------- building sites and rubble
        m = re.match(r"^CNST([1-8D])_NN$", name)
        if m:
            tiles = {"1": 1, "2": 2, "3": 3, "4": 4, "8": 5, "D": 3}.get(m.group(1))
            add(g, {"model": "construction", "tiles": tiles, "mode": "variants"}, "building site")
            continue
        if re.match(r"^RUBL\dV?_NN$|^RUB\dV_NN$", name):
            add(g, {"model": "rubble", "mode": "variants", "fit": True}, "rubble", family="^RUB")
            continue
        if name == "FTRAP":
            add(g, {"model": "fish_trap", "mode": "variants"})
            continue
        if name == "FTRAP_D":
            add(g, {"model": "fish_trap", "stage": 0.0, "mode": "static"}, "wrecked")
            continue
        if name == "FTRPC":
            add(g, {"model": "construction", "tiles": 3, "mode": "variants"}, "fish trap being built")
            continue
        if re.match(r"^FARM0C1G$", name):
            add(g, {"model": "building", "code": "FARM", "stage": 0.0, "mode": "static"}, "farm being built")
            continue
        if re.match(r"^FARM0C0G$", name):
            blank(g, "farm construction layer")
            continue

        # ---------------------------------------------------------------- trees and resources
        m = re.match(r"^TREE([A-L])_(NN|N0|SN)$", name)
        if m:
            letter, part = m.groups()
            if part == "NN":
                add(g, {"model": "tree", "kind": SINGLE_TREE[letter], "mode": "variants", "fit": True})
            elif part == "SN":
                add(g, {"model": "stump", "kind": SINGLE_TREE[letter], "mode": "variants"}, "chopped tree")
            else:
                blank(g, "tree shadow", r"^TREE")
            continue
        m = re.match(r"^(FORTR|FOAK|FPIN|FPAL|FBAM|FJUN|FSNO)_(NN|N0|N1|N2|SN)$", name)
        if m:
            forest = {"FORTR": "forest", "FOAK": "oak", "FPIN": "pine", "FPAL": "palm", "FBAM": "bamboo",
                      "FJUN": "jungle", "FSNO": "snow"}[m.group(1)]
            part = m.group(2)
            if part == "NN":
                add(g, {"model": "tree", "forest": forest, "mode": "variants", "fit": True})
            elif part == "N2" or (part == "N1" and g.angle_count > 1):
                main = by_name.get(f"{m.group(1)}_NN")
                add(g, {"model": "tree", "forest": forest, "mode": "variants", "fit": True,
                        "fit_slp": main.slp if main else g.slp,
                        "part": "trunk" if part == "N2" else "crown"}, "split tree")
            elif part == "SN":
                add(g, {"model": "stump", "kind": TREE_STUMP[forest], "mode": "variants"}, "chopped tree")
            else:
                blank(g, "forest shadow", r"^F")
            continue
        if name in ("STUMP_NN", "STUMB_NN"):
            add(g, {"model": "stump", "kind": "bamboo" if name == "STUMB_NN" else "oak", "felled": False,
                    "mode": "variants"})
            continue
        m = re.match(r"^(GOLDM|STONM)_(NN|N0)$", name)
        if m:
            if m.group(2) == "NN":
                add(g, {"model": "ore", "kind": "gold" if m.group(1) == "GOLDM" else "stone", "mode": "variants",
                        "fit": True})
            else:
                blank(g, "mine layer", r"^(GOLDM|STONM)")
            continue
        simple = {
            "FORAG_NN": {"model": "berry_bush", "mode": "variants"},
            "ROCKX_NN": {"model": "rock", "mode": "variants", "fit": True},
            "PLANTS": {"model": "plants", "mode": "variants"},
            "FLWRB_NN": {"model": "plants", "flowers": True, "mode": "variants"},
            "FCAC": {"model": "cactus", "mode": "variants"}, "FCAC_NN": {"model": "cactus", "mode": "variants"},
            "HSTAC_NN": {"model": "haystack", "mode": "variants"},
            "GRAVES": {"model": "gaia", "name": "graves", "mode": "variants"},
            "HEADS": {"model": "gaia", "name": "heads", "mode": "variants"},
            "STATUE": {"model": "gaia", "name": "statue", "mode": "static"},
            "RUINS_NN": {"model": "gaia", "name": "ruins", "mode": "variants"},
            "TERRX_NN": {"model": "gaia", "name": "ruins", "mode": "static"},
            "SHEAD_NN": {"model": "gaia", "name": "stone_head", "mode": "variants"},
            "BCART_NN": {"model": "gaia", "name": "broken_cart", "mode": "static"},
            "CRATR_NN": {"model": "gaia", "name": "crater", "mode": "variants"},
            "RUGS": {"model": "gaia", "name": "rug", "mode": "variants"},
            "RUGS_NN": {"model": "gaia", "name": "rug", "mode": "variants"},
            "SIGN": {"model": "gaia", "name": "signpost", "mode": "facing"},
            "SKEL_NN": {"model": "gaia", "name": "skeleton", "mode": "facing"},
            "ARTCT_WN": {"model": "gaia", "name": "relic", "mode": "facing"},
            "HPTC_FN": {"model": "gaia", "name": "relic", "mode": "facing"},
            "HPTC_WN": {"model": "gaia", "name": "relic", "mode": "facing"},
            "TORH1NNG": {"model": "gaia", "name": "standing_torch", "mode": "anim"},
            "TORCH2": {"model": "gaia", "name": "standing_torch", "mode": "anim"},
            "TERRA_NN": {"model": "gaia", "name": "sea_rock", "variant": 0, "mode": "static"},
            "TERRJ_NN": {"model": "gaia", "name": "sea_rock", "variant": 1, "mode": "static"},
            "ESFLAG_NN": {"model": "gaia", "name": "banner_flag", "variant": 0, "mode": "anim"},
        }
        if name in simple:
            add(g, dict(simple[name]), family="^" + re.escape(name[:3]))
            continue
        for k in "MNOP":
            if name == f"TERR{k}_NN":
                add(g, {"model": "plants", "flowers": True, "mode": "variants"}, "flowers")
        # ---------------------------------------------------------------- projectiles
        proj = PROJECTILES.get(name)
        if proj:
            add(g, {"model": "projectile", "shadow": False, **proj}, "projectile",
                family="^(M_|ARROW|MRCST|MFCST|MRSTW|MFSTW|BOLT|CATS|MRMLK)")
            continue
        m = re.match(r"^FLAG([A-E])_(NN|N0|N1)$", name)
        if m:
            if m.group(2) == "NN":
                add(g, {"model": "gaia", "name": "banner_flag", "variant": "ABCDE".index(m.group(1)), "mode": "anim"},
                    family="^(FLAG|REVEAL)")
            else:
                blank(g, "flag layer", r"^FLAG")
            continue
        if name in ("REVEAL_NN",):
            add(g, {"model": "gaia", "name": "banner_flag", "variant": 0, "mode": "anim"}, family="^(FLAGA|REVEAL)")
            continue
        if name == "M_SPEA_D":  # a javelin stuck in the ground: snowballs don't stick
            blank(g, "stuck javelin")
            continue
        if name in ("ESFLAG_N0",) or re.match(r"^TERR[AJ]_N[01]$", name):
            blank(g, "decoration layer")
            continue
        m = re.match(r"^YERT([A-H])1NNG?$", name)
        if m:
            add(g, {"model": "gaia", "name": "yurt", "variant": "ABCDEFGH".index(m.group(1)), "mode": "static"},
                family="^YERT")
            continue
        m = re.match(r"^PAV([1-3])1NNG$", name)
        if m:
            add(g, {"model": "gaia", "name": "pavilion", "variant": int(m.group(1)) - 1, "mode": "static"})
            continue
    return P


# name -> projectile; arrows with 11 frames per angle hold the pitch from climbing to diving
PROJECTILES = {
    "ARROW_NN": {"kind": "arrow", "mode": "facing"},
    "M_ARRO_R": {"kind": "arrow", "mode": "facing", "pitched": True},
    "M_ARRO_F": {"kind": "fire_arrow", "mode": "facing", "pitched": True},
    "MRCST": {"kind": "arrow", "mode": "facing", "pitched": True},
    "MFCST": {"kind": "fire_arrow", "mode": "facing", "pitched": True},
    "MRSTW": {"kind": "arrow", "mode": "facing", "pitched": True},
    "MFSTW": {"kind": "fire_arrow", "mode": "facing", "pitched": True},
    "M_HBOL_R": {"kind": "bolt", "mode": "facing"}, "M_HBOL_F": {"kind": "bolt", "mode": "facing"},
    "M_LBOL_R": {"kind": "bolt", "mode": "facing"}, "M_LBOL_F": {"kind": "bolt", "mode": "facing"},
    "BOLTF_NN": {"kind": "bolt", "mode": "facing"}, "BOLTX_NN": {"kind": "bolt", "mode": "facing"},
    "ARROW_D": {"kind": "stuck_arrow", "mode": "facing"},
    "M_AXEX_R": {"kind": "axe", "mode": "facing"},
    "MRMLK": {"kind": "sword", "mode": "facing"},
    "M_SPEA_R": {"kind": "snowball", "mode": "facing"}, "M_SPEA_F": {"kind": "snowball", "mode": "facing"},
    "M_BALL_R": {"kind": "cobble", "mode": "static"},
    "CATST_NN": {"kind": "cobble", "mode": "static"}, "CATSF_NN": {"kind": "magma", "mode": "anim"},
    "M_ROCK_R": {"kind": "stone", "mode": "anim"}, "M_ROCK_F": {"kind": "magma", "mode": "anim"},
    "M_SHOT_R": {"kind": "tnt", "mode": "static"}, "M_SHOT_F": {"kind": "tnt", "mode": "anim"},
}

SINGLE_TREE = {"A": "oak", "B": "birch", "C": "spruce", "D": "jungle", "E": "oak", "F": "dead", "G": "acacia",
               "H": "dark_oak", "I": "dead", "J": "birch", "K": "cherry", "L": "oak"}
TREE_STUMP = {"forest": "oak", "oak": "oak", "pine": "spruce", "palm": "palm", "bamboo": "bamboo",
              "jungle": "jungle", "snow": "spruce"}


def resolve_offsets(P: Plan, graphics: dict) -> None:
    """Fill in placement details that come from composite graphics' delta offsets.

    Town Center: the main piece is drawn at the unit's own position; its offset inside the
    construction composite is only recorded for the report (it should be zero).
    Gates: the distance to the end towers sets the length of the gate between them.
    """
    by_name = {g.name.upper(): g for g in graphics.values()}
    for s in P.sprites.values():
        spec = s.spec
        parent = by_name.get(spec.get("anchor", ""))
        if parent is not None:
            for d in parent.deltas:
                child = graphics.get(d.graphic_id)
                if child is not None and child.slp == s.slp and (d.offset_x or d.offset_y):
                    spec["anchor_offset"] = (d.offset_x, d.offset_y)
        gp = by_name.get(spec.get("gate_parent", ""))
        if gp is not None:
            dists = []
            for d in gp.deltas:
                child = graphics.get(d.graphic_id)
                if child is not None and re.match(r"^GT[A-D]C", child.name.upper()) and (d.offset_x or d.offset_y):
                    dists.append(screen_to_blocks(d.offset_x, d.offset_y))
            if dists:
                spec["half"] = max(dists)
