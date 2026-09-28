"""Minecraft-style block textures, painted procedurally (16x16 texels per face).

`blocks()` returns a registry of named block types. A block type holds one
texture per face; most blocks look the same on every side, logs and pillars
have distinct ends, and workstations (furnace, crafting table...) have a
distinct front. Textures with transparent texels (leaves, glass panes, iron
bars) let the renderer see through the gaps.

Everything is deterministic: the same name always paints the same pixels.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .textures import FACES, PC, Painter, parse

N = 16


@dataclass
class BlockType:
    faces: dict[str, np.ndarray]
    opaque: bool = True  # hides whatever is behind it (used to skip buried blocks)

    @classmethod
    def uniform(cls, tex: np.ndarray, opaque: bool = True) -> "BlockType":
        return cls({f: tex for f in FACES}, opaque)

    @classmethod
    def pillar(cls, side: np.ndarray, end: np.ndarray) -> "BlockType":
        return cls({"front": side, "back": side, "right": side, "left": side, "top": end, "bottom": end})

    @classmethod
    def fronted(cls, front: np.ndarray, side: np.ndarray, top: np.ndarray, bottom: np.ndarray = None) -> "BlockType":
        """A workstation: `front` faces +y and +x (the two walls the camera sees)."""
        return cls({"front": front, "right": front, "back": side, "left": side, "top": top,
                    "bottom": top if bottom is None else bottom})


# --------------------------------------------------------------------------- painting helpers

def _c(spec) -> np.ndarray:
    return parse(spec)


def _mix(a: str, b: str, t: float) -> str:
    ca, cb = _c(a)[:3], _c(b)[:3]
    r, g, bb = (ca * (1 - t) + cb * t) * 255
    return f"#{int(r):02x}{int(g):02x}{int(bb):02x}"


def _shade(spec: str, k: float) -> str:
    r, g, b = np.clip(_c(spec)[:3] * k, 0, 1) * 255
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def noise_fill(p: Painter, base: str, amount: float = 0.08, spots: tuple = ()) -> np.ndarray:
    tex = p.fill(N, N, base, amount)
    for spec, prob in spots:
        tex[p.rng.random((N, N)) < prob] = _c(spec)
    return tex


def planks(p: Painter, base: str) -> np.ndarray:
    light, dark, seam = base, _shade(base, 0.78), _shade(base, 0.68)
    tex = p.fill(N, N, light, 0.05)
    for r in (3, 7, 11, 15):
        tex[r] = _c(dark)
    for r0, c in ((0, 5), (4, 12), (8, 2), (12, 9)):  # staggered plank ends
        tex[r0:r0 + 3, c] = _c(seam)
    streak = p.rng.random((N, N)) < 0.12
    tex[streak, :3] *= 0.92
    return p.jitter(tex, 0.03)


def log_side(p: Painter, bark: str) -> np.ndarray:
    tex = p.fill(N, N, bark, 0.07)
    groove = _c(_shade(bark, 0.72))
    for c in range(N):
        if p.rng.random() < 0.35:
            r0 = p.rng.integers(0, 8)
            tex[r0:r0 + p.rng.integers(5, 14), c] = groove
    return p.jitter(tex, 0.04)


def log_top(p: Painter, bark: str, wood: str) -> np.ndarray:
    yy, xx = np.mgrid[0:N, 0:N]
    d = np.maximum(np.abs(xx - 7.5), np.abs(yy - 7.5))
    tex = p.fill(N, N, wood, 0.04)
    ring = _c(_shade(wood, 0.82))
    tex[(d > 1.5) & (d < 2.5)] = ring
    tex[(d > 3.5) & (d < 4.5)] = ring
    tex[(d > 5.5) & (d < 6.5)] = ring
    tex[d >= 6.5] = _c(bark)
    return tex


def cobble(p: Painter, base: str, light: str = None, mortar: str = None) -> np.ndarray:
    light = light or _shade(base, 1.2)
    mortar = mortar or _shade(base, 0.6)
    tex = p.fill(N, N, mortar, 0.05)
    yy, xx = np.mgrid[0:N, 0:N]
    for _ in range(10):
        cx, cy = p.rng.uniform(0, 16, 2)
        rx, ry = p.rng.uniform(2.2, 4.2, 2)
        m = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 < 1
        tex[m] = _c(base)
        tex[m & (yy < cy - ry * 0.35)] = _c(light)
    return p.jitter(tex, 0.06)


def brick_rows(p: Painter, face: str, mortar: str, rows: int = 2, light: str = None) -> np.ndarray:
    """Running-bond bricks: `rows` courses per block (2 = stone bricks, 4 = clay bricks)."""
    tex = p.fill(N, N, face, 0.06)
    h = N // rows
    bw = N if rows <= 2 else N // 2
    for i in range(rows):
        y = i * h
        if light:
            tex[y + 1, :] = _c(light)
        tex[y] = _c(mortar)
        for x in range((bw // 2) if i % 2 else 0, N, bw):
            tex[y:y + h, x] = _c(mortar)
    return p.jitter(tex, 0.04)


def framed(p: Painter, inner: str, border: str, noise: float = 0.05) -> np.ndarray:
    tex = p.fill(N, N, inner, noise)
    tex[0, :] = tex[-1, :] = tex[:, 0] = tex[:, -1] = _c(border)
    return tex


def chiseled(p: Painter, base: str) -> np.ndarray:
    tex = framed(p, base, _shade(base, 0.65))
    yy, xx = np.mgrid[0:N, 0:N]
    d = np.maximum(np.abs(xx - 7.5), np.abs(yy - 7.5))
    tex[(d > 2.5) & (d < 3.5)] = _c(_shade(base, 0.7))
    tex[(d > 4.5) & (d < 5.5)] = _c(_shade(base, 1.15))
    tex[d < 1.5] = _c(_shade(base, 0.8))
    return p.jitter(tex, 0.03)


def sandstone_side(p: Painter, base: str, band: str) -> np.ndarray:
    tex = p.fill(N, N, base, 0.04)
    tex[0:2] = _c(_shade(base, 1.06))
    tex[12:14] = _c(band)
    tex[14:16] = _c(_shade(base, 0.9))
    speck = p.rng.random((N, N)) < 0.08
    tex[speck, :3] *= 0.94
    return tex


def creeper_face(p: Painter, base: str) -> np.ndarray:
    """Chiseled sandstone: the creeper face, as carved in desert temples."""
    rows = ["BBBBBBBBBBBBBBBB", "B..............B", "B.DD........DD.B", "B.DD........DD.B",
            "B..............B", "B......DD......B", "B.....DDDD.....B", "B.....D..D.....B",
            "B..............B", "BBBBBBBBBBBBBBBB", "................", "..DDDD....DDDD..",
            "..............  ".replace(" ", "."), "BBBBBBBBBBBBBBBB", "................", "BBBBBBBBBBBBBBBB"]
    return p.grid(rows, {"B": _shade(base, 0.85), ".": base, "D": _shade(base, 0.62)}, 0.03)


def leaves(p: Painter, base: str, holes: float = 0.18, dark: float = 0.78) -> np.ndarray:
    tex = p.fill(N, N, base, 0.1)
    d = p.rng.random((N, N))
    tex[d < 0.3, :3] *= dark
    tex[(d > 0.85), :3] = np.clip(tex[(d > 0.85), :3] * 1.18, 0, 1)
    tex[p.rng.random((N, N)) < holes, 3] = 0
    return tex


def ore(p: Painter, stone: str, fleck: str, fleck_light: str = None) -> np.ndarray:
    tex = noise_fill(p, stone, 0.08)
    for _ in range(4):
        x, y = p.rng.integers(1, 13, 2)
        shape = p.rng.random((3, 3)) < 0.7
        for dy in range(3):
            for dx in range(3):
                if shape[dy, dx]:
                    tex[y + dy, x + dx] = _c(fleck)
        if fleck_light:
            tex[y, x] = _c(fleck_light)
    return tex


def workstation(p: Painter, rows: list[str], legend: dict) -> np.ndarray:
    return p.grid(rows, legend, 0.03)


# --------------------------------------------------------------------------- the registry

WOODS = {  # planks, bark, stripped/core
    "oak": ("#b18d54", "#6b5132", "#b8955e"),
    "spruce": ("#7a5a35", "#3d2a18", "#8a6a40"),
    "birch": ("#d7c68a", "#e8e4dc", "#e0cf94"),
    "jungle": ("#b0794f", "#5a4420", "#b98a5c"),
    "acacia": ("#b8622f", "#6a625a", "#c07040"),
    "dark_oak": ("#4f3720", "#3a2a18", "#5c4226"),
    "cherry": ("#e6b8b0", "#3a2530", "#e3aaa8"),
    "mangrove": ("#7a3530", "#4f4033", "#8a4038"),
    "bamboo": ("#c9b44e", "#8a9a3a", "#d4c05a"),
    "crimson": ("#6b344a", "#5c1a1e", "#7a3a55"),
}

COLOURS = {  # Minecraft dye colours (wool/concrete/terracotta bases)
    "white": "#e9ecec", "orange": "#f07613", "magenta": "#bd44b3", "light_blue": "#3aafd9",
    "yellow": "#f8c527", "lime": "#70b919", "pink": "#ed8dac", "gray": "#3e4447",
    "light_gray": "#8e8e86", "cyan": "#158991", "purple": "#792aac", "blue": "#35399d",
    "brown": "#724728", "green": "#546d1b", "red": "#a12722", "black": "#141519",
}
TERRACOTTA = {
    "terracotta": "#985e43", "white": "#d1b2a1", "orange": "#a15325", "yellow": "#ba8523",
    "red": "#8f3d2e", "brown": "#4d3323", "light_gray": "#876a61", "gray": "#392a23",
    "cyan": "#565b5b", "green": "#4c532a", "blue": "#4a3b5b", "black": "#251710", "lime": "#677534",
    "light_blue": "#716c89", "pink": "#a14e4e", "purple": "#764656", "magenta": "#95576c",
}


@lru_cache(maxsize=None)
def blocks() -> dict[str, BlockType]:
    p = Painter("blocks-v2")
    B: dict[str, BlockType] = {}
    u, pil = BlockType.uniform, BlockType.pillar

    # woods
    for name, (plank, bark, core) in WOODS.items():
        B[f"{name}_planks"] = u(planks(p, plank))
        B[f"{name}_log"] = pil(log_side(p, bark), log_top(p, bark, core))
        B[f"stripped_{name}_log"] = pil(log_side(p, _shade(core, 0.95)), log_top(p, core, core))
        B[f"{name}_wood"] = u(log_side(p, bark))
    birch = log_side(p, "#e8e4dc")
    for _ in range(9):  # birch bark: black dashes
        y, x = p.rng.integers(0, 15), p.rng.integers(0, 12)
        birch[y, x:x + p.rng.integers(2, 5)] = _c("#2b2b28")
    B["birch_log"] = pil(birch, log_top(p, "#e8e4dc", "#e0cf94"))
    bamboo_side = p.fill(N, N, "#9aa53c", 0.05)
    for c in (0, 5, 10, 15):
        bamboo_side[:, c] = _c("#6f7a2a")
    bamboo_side[7] = _c("#c9c065")
    B["bamboo_block"] = pil(bamboo_side, log_top(p, "#8a9a3a", "#c9c065"))
    B["bamboo_mosaic"] = u(brick_rows(p, "#c9b44e", "#9c8a36", rows=4))

    # stone family
    B["stone"] = u(noise_fill(p, "#7f7f7f", 0.08, (("#737373", 0.2), ("#8c8c8c", 0.15))))
    B["cobblestone"] = u(cobble(p, "#8a8a8a", "#a8a8a8", "#555555"))
    mossy = cobble(p, "#8a8a8a", "#a8a8a8", "#555555")
    moss = p.rng.random((N, N)) < 0.38
    mossy[moss] = np.array([*(_c("#5d7a36")[:3] * p.rng.uniform(0.85, 1.1)), 1, 0], np.float32)
    B["mossy_cobblestone"] = u(mossy)
    B["stone_bricks"] = u(brick_rows(p, "#8c8c8c", "#5f5f5f", 2, light="#a0a0a0"))
    mb = brick_rows(p, "#8c8c8c", "#5f5f5f", 2, light="#a0a0a0")
    mb[p.rng.random((N, N)) < 0.3] = _c("#5d7a36")
    B["mossy_stone_bricks"] = u(mb)
    cb = brick_rows(p, "#8c8c8c", "#5f5f5f", 2, light="#a0a0a0")
    for (y, x) in ((3, 4), (4, 5), (5, 5), (6, 6), (11, 10), (12, 11), (12, 12), (13, 12)):
        cb[y, x] = _c("#4a4a4a")
    B["cracked_stone_bricks"] = u(cb)
    B["chiseled_stone_bricks"] = u(chiseled(p, "#8c8c8c"))
    B["smooth_stone"] = u(framed(p, "#a3a3a3", "#8a8a8a", 0.03))
    for name, col in (("andesite", "#888889"), ("diorite", "#bcbcbc"), ("granite", "#9a6c5a")):
        B[name] = u(noise_fill(p, col, 0.1, ((_shade(col, 0.8), 0.25), (_shade(col, 1.2), 0.15))))
        B[f"polished_{name}"] = u(framed(p, col, _shade(col, 0.82), 0.05))
    B["deepslate_tiles"] = u(brick_rows(p, "#3b3b40", "#26262a", 4, light="#4a4a50"))
    B["deepslate_bricks"] = u(brick_rows(p, "#4a4a50", "#2e2e33", 2))
    B["cobbled_deepslate"] = u(cobble(p, "#4d4d52", "#5d5d63", "#2a2a2e"))
    B["bricks"] = u(brick_rows(p, "#96503c", "#bfb3a8", 4, light="#a8604a"))
    B["mud_bricks"] = u(brick_rows(p, "#8c6a4f", "#6e5140", 4))
    B["packed_mud"] = u(noise_fill(p, "#8e6b50", 0.08))
    B["nether_bricks"] = u(brick_rows(p, "#2c1519", "#160a0c", 4, light="#3a1d22"))
    B["red_nether_bricks"] = u(brick_rows(p, "#5a0a0c", "#2e0506", 4, light="#6e1012"))
    B["obsidian"] = u(noise_fill(p, "#1b1428", 0.08, (("#3b2754", 0.12),)))
    B["blackstone"] = u(noise_fill(p, "#2a2429", 0.1))
    B["prismarine_bricks"] = u(brick_rows(p, "#63ab9e", "#3f7a70", 2))
    B["dark_prismarine"] = u(framed(p, "#335b4b", "#23433a"))
    B["purpur"] = u(framed(p, "#a97ca9", "#8a5f8a"))
    B["end_stone"] = u(noise_fill(p, "#dbdea0", 0.06))

    # sand family
    for name, col, band in (("sandstone", "#dbcf99", "#c9ba7c"), ("red_sandstone", "#ba6224", "#a0521b")):
        top = noise_fill(p, col, 0.04)
        B[name] = BlockType({"front": sandstone_side(p, col, band), "back": sandstone_side(p, col, band),
                             "right": sandstone_side(p, col, band), "left": sandstone_side(p, col, band),
                             "top": top, "bottom": top})
        B[f"cut_{name}"] = u(brick_rows(p, col, band, 2))
        B[f"smooth_{name}"] = u(noise_fill(p, col, 0.03))
        B[f"chiseled_{name}"] = pil(creeper_face(p, col), top)
    B["sand"] = u(noise_fill(p, "#dbcf99", 0.07, (("#c9bb85", 0.2),)))
    B["red_sand"] = u(noise_fill(p, "#b9611f", 0.07))
    B["gravel"] = u(noise_fill(p, "#857f7c", 0.12, (("#6b6360", 0.3), ("#a39c98", 0.2))))
    B["clay"] = u(noise_fill(p, "#9ea4b0", 0.05))

    # earth
    B["dirt"] = u(noise_fill(p, "#866043", 0.1, (("#6d4c32", 0.25), ("#9a7355", 0.12))))
    B["coarse_dirt"] = u(noise_fill(p, "#77553a", 0.12, (("#5c4029", 0.3), ("#8f8f8f", 0.06))))
    grass_top = noise_fill(p, "#6a9a3a", 0.1, (("#5b8a30", 0.3), ("#7aaa46", 0.15)))
    grass_side = B["dirt"].faces["front"].copy()
    for c in range(N):
        grass_side[:p.rng.integers(2, 5), c] = grass_top[0, c]
    B["grass_block"] = BlockType({"front": grass_side, "back": grass_side, "right": grass_side,
                                  "left": grass_side, "top": grass_top, "bottom": B["dirt"].faces["top"]})
    path_top = noise_fill(p, "#9a7b48", 0.08, (("#8a6d3e", 0.25),))
    B["dirt_path"] = BlockType({**{f: B["dirt"].faces[f] for f in FACES}, "top": path_top})
    farmland = noise_fill(p, "#553a24", 0.08)
    for r in (2, 6, 10, 14):
        farmland[r] = _c("#3e2917")
    B["farmland"] = BlockType({**{f: B["dirt"].faces[f] for f in FACES}, "top": farmland})
    B["podzol"] = BlockType({**{f: B["dirt"].faces[f] for f in FACES},
                             "top": noise_fill(p, "#7a5a2a", 0.1, (("#5b4020", 0.3),))})
    B["mycelium"] = BlockType({**{f: B["dirt"].faces[f] for f in FACES},
                               "top": noise_fill(p, "#6f6369", 0.1, (("#8a7f86", 0.2),))})
    B["snow"] = u(noise_fill(p, "#f2fbfb", 0.03))
    B["ice"] = u(noise_fill(p, "#8fb4f5", 0.04))
    B["packed_ice"] = u(noise_fill(p, "#a1bdf0", 0.05))
    water = noise_fill(p, "#3a62c8", 0.06)
    for r in range(0, N, 4):
        water[r, p.rng.integers(0, 10):][:5] = _c("#5a82e0")
    B["water"] = u(water)
    lava = noise_fill(p, "#d9611a", 0.12, (("#f2b02a", 0.3), ("#a8350f", 0.1)))
    B["lava"] = u(lava)

    # ores and precious blocks
    B["gold_ore"] = u(ore(p, "#7f7f7f", "#f5d84a", "#fff7a8"))
    B["iron_ore"] = u(ore(p, "#7f7f7f", "#d8af93", "#efd5c0"))
    B["coal_ore"] = u(ore(p, "#7f7f7f", "#2b2b2b"))
    B["emerald_ore"] = u(ore(p, "#7f7f7f", "#17dd62", "#8ff5b0"))
    B["diamond_ore"] = u(ore(p, "#7f7f7f", "#4ae2e0", "#c0fbf9"))
    B["redstone_ore"] = u(ore(p, "#7f7f7f", "#c20a0a", "#ff5050"))
    B["deepslate_gold_ore"] = u(ore(p, "#4d4d52", "#f5d84a", "#fff7a8"))
    B["raw_gold_block"] = u(noise_fill(p, "#dda32a", 0.1, (("#f5d84a", 0.3), ("#a8751a", 0.2))))
    B["gold_block"] = u(framed(p, "#f7d43a", "#d6a522", 0.04))
    B["iron_block"] = u(framed(p, "#dcdcdc", "#bcbcbc", 0.03))
    B["emerald_block"] = u(framed(p, "#2ad064", "#1a9a48", 0.04))
    B["diamond_block"] = u(framed(p, "#6ae8e3", "#3bbab5", 0.04))
    B["lapis_block"] = u(noise_fill(p, "#1f4aa3", 0.08, (("#3a68c8", 0.2),)))
    B["copper_block"] = u(framed(p, "#c06a4a", "#9c5238", 0.05))
    B["oxidized_copper"] = u(noise_fill(p, "#52a384", 0.08, (("#3e8a6c", 0.25),)))
    B["cut_copper"] = u(brick_rows(p, "#c06a4a", "#9c5238", 2))
    B["oxidized_cut_copper"] = u(brick_rows(p, "#52a384", "#3a7a62", 2))
    B["quartz"] = u(noise_fill(p, "#ece6df", 0.02))
    B["quartz_bricks"] = u(brick_rows(p, "#ece6df", "#cfc8bf", 2))
    B["quartz_pillar"] = pil(framed(p, "#ece6df", "#d6cfc6", 0.02), chiseled(p, "#ece6df"))
    B["chiseled_quartz"] = u(chiseled(p, "#ece6df"))

    # colours
    for name, col in COLOURS.items():
        wool = p.fill(N, N, col, 0.06)
        wool[p.rng.random((N, N)) < 0.25, :3] *= 0.9
        B[f"{name}_wool"] = u(wool)
        B[f"{name}_concrete"] = u(p.fill(N, N, col, 0.02))
    B["player_wool"] = u(p.fill(N, N, PC(0.6), 0.06))
    B["player_wool_dark"] = u(p.fill(N, N, PC(0.4), 0.06))
    for name, col in TERRACOTTA.items():
        key = "terracotta" if name == "terracotta" else f"{name}_terracotta"
        B[key] = u(noise_fill(p, col, 0.05))
    glazed = p.grid(["WWWWBBBBBBBBWWWW", "WOOWBYYYYYYBWOOW", "WOOWBYBBBBYBWOOW", "WWWWBYBWWBYBWWWW",
                     "BBBBBYBWWBYBBBBB", "BYYYYYBWWBYYYYYB", "BYBBBBBWWBBBBBYB", "BYBWWWWOOWWWWBYB",
                     "BYBWWWWOOWWWWBYB", "BYBBBBBWWBBBBBYB", "BYYYYYBWWBYYYYYB", "BBBBBYBWWBYBBBBB",
                     "WWWWBYBWWBYBWWWW", "WOOWBYBBBBYBWOOW", "WOOWBYYYYYYBWOOW", "WWWWBBBBBBBBWWWW"],
                    {"W": "#f2f0e8", "B": "#2f5ea8", "Y": "#f5c542", "O": "#d9622b"}, 0.02)
    B["glazed_terracotta"] = u(glazed)

    # glass and see-through blocks
    glass = p.fill(N, N, "#c8e4ec", 0.02)
    glass[..., 3] = 0
    glass[0, :] = glass[-1, :] = glass[:, 0] = glass[:, -1] = _c("#e8f4f7")
    for i in range(3, 8):
        glass[i, 11 - i] = _c("#ffffff")
    B["glass_see"] = BlockType.uniform(glass, opaque=False)
    window = p.fill(N, N, "#9fc3cf", 0.03)
    for i in range(3, 8):
        window[i, 11 - i] = _c("#e4f3f7")
        window[i + 5, 14 - i] = _c("#e4f3f7")
    window[0, :] = window[-1, :] = window[:, 0] = window[:, -1] = _c("#6f5a3a")
    B["glass"] = u(window)
    for name in ("red", "yellow", "blue", "purple", "cyan", "light_blue", "orange", "lime"):
        st = p.fill(N, N, _mix(COLOURS[name], "#ffffff", 0.2), 0.03)
        st[0, :] = st[-1, :] = st[:, 0] = st[:, -1] = _c(_shade(COLOURS[name], 0.6))
        st[7, :] = st[:, 7] = _c("#3a3a3a")
        B[f"{name}_stained_glass"] = u(st)
    bars = np.zeros((N, N, 5), np.float32)
    for c in (1, 5, 10, 14):
        bars[:, c] = _c("#6b6b6b")
        bars[:, c + 1] = _c("#9a9a9a")
    bars[0] = bars[15] = _c("#6b6b6b")
    B["iron_bars"] = BlockType.uniform(bars, opaque=False)
    scaffold = np.zeros((N, N, 5), np.float32)
    for c in (0, 1, 14, 15):
        scaffold[:, c] = _c("#c9a860")
    scaffold[0:2] = scaffold[14:16] = _c("#c9a860")
    for i in range(2, 14):
        scaffold[i, i] = _c("#a88c4a")
    B["scaffolding"] = BlockType.uniform(scaffold, opaque=False)
    ladder = np.zeros((N, N, 5), np.float32)
    ladder[:, 2:4] = ladder[:, 12:14] = _c("#8a6a40")
    for r in (2, 6, 10, 14):
        ladder[r, 2:14] = _c("#a07c4a")
    B["ladder"] = BlockType.uniform(ladder, opaque=False)

    # leaves (with gaps)
    for name, col in (("oak", "#4a8a2a"), ("spruce", "#395a39"), ("birch", "#6a9a4a"), ("jungle", "#3f9a22"),
                      ("acacia", "#5a8a22"), ("dark_oak", "#3a6a1e"), ("cherry", "#f2b7d2"),
                      ("azalea", "#5d7d2e"), ("mangrove", "#5a8a2a")):
        B[f"{name}_leaves"] = BlockType.uniform(leaves(p, col), opaque=False)
    fl = leaves(p, "#5d7d2e")
    for _ in range(10):
        fl[p.rng.integers(0, 15), p.rng.integers(0, 15)] = _c("#d985c9")
    B["flowering_azalea_leaves"] = BlockType.uniform(fl, opaque=False)
    snowy = leaves(p, "#395a39", holes=0.1)
    snowy[:6] = np.where(p.rng.random((6, N, 1)) < 0.8, _c("#f2fbfb"), snowy[:6])
    B["snowy_spruce_leaves"] = BlockType({**{f: snowy for f in FACES}, "top": noise_fill(p, "#f2fbfb", 0.03)},
                                         opaque=False)

    # plants as blocks
    cactus_side = p.fill(N, N, "#0f7a1f", 0.06)
    for c in (1, 7, 14):
        cactus_side[:, c] = _c("#0a5a15")
    for (y, x) in ((2, 3), (6, 10), (11, 4), (13, 12)):
        cactus_side[y, x] = _c("#e8e0a8")
    B["cactus"] = BlockType({**{f: cactus_side for f in FACES},
                             "top": framed(p, "#2a9a3a", "#0f7a1f", 0.04)})
    B["hay"] = pil(p.speckle("#c8a43a", ("#a88422", 0.3), ("#e0c257", 0.15))(N, N),
                   p.speckle("#b89530", ("#8e7020", 0.3))(N, N))
    hay_side = B["hay"].faces["front"].copy()
    hay_side[3:5] = hay_side[11:13] = _c("#8a2a1a")
    B["hay"] = pil(hay_side, B["hay"].faces["top"])
    B["melon"] = pil(noise_fill(p, "#6a9a22", 0.1, (("#4a7a12", 0.3),)), noise_fill(p, "#7aa22a", 0.06))
    pump = p.fill(N, N, "#d8891a", 0.06)
    for c in (0, 5, 10, 15):
        pump[:, c] = _c("#b06a10")
    B["pumpkin"] = pil(pump, noise_fill(p, "#c07a18", 0.06))
    lantern_face = pump.copy()
    for (y, x) in ((5, 3), (5, 4), (5, 11), (5, 12), (10, 4), (10, 5), (10, 6), (10, 7), (10, 8), (10, 9),
                   (10, 10), (10, 11), (11, 5), (11, 10)):
        lantern_face[y, x] = _c("#f5e05a")
    B["jack_o_lantern"] = BlockType.fronted(lantern_face, pump, noise_fill(p, "#c07a18", 0.06))
    mush = p.fill(N, N, "#c22d2a", 0.05)
    for (y, x) in ((2, 3), (3, 3), (2, 4), (6, 10), (6, 11), (7, 10), (11, 5), (12, 5), (11, 6), (13, 12)):
        mush[y, x] = _c("#f2eee8")
    B["red_mushroom_block"] = u(mush)
    B["brown_mushroom_block"] = u(noise_fill(p, "#936a4c", 0.05))
    B["mushroom_stem"] = u(noise_fill(p, "#d6d0c5", 0.04))
    B["moss_block"] = u(noise_fill(p, "#5d7a36", 0.1, (("#4a6a2a", 0.3),)))
    B["sweet_berry_leaves"] = BlockType.uniform(leaves(p, "#3e6a38", holes=0.15), opaque=False)

    # utility and workstation blocks
    plank = B["oak_planks"].faces["top"]
    books = p.grid(["PPPPPPPPPPPPPPPP", "PRRBBGGYRBBGGRYP", "PRRBBGGYRBBGGRYP", "PRRBBGGYRBBGGRYP",
                    "PRRBBGGYRBBGGRYP", "PRRBBGGYRBBGGRYP", "PRRBBGGYRBBGGRYP", "PPPPPPPPPPPPPPPP",
                    "PPPPPPPPPPPPPPPP", "PGYRRBBRRYGGBBRP", "PGYRRBBRRYGGBBRP", "PGYRRBBRRYGGBBRP",
                    "PGYRRBBRRYGGBBRP", "PGYRRBBRRYGGBBRP", "PGYRRBBRRYGGBBRP", "PPPPPPPPPPPPPPPP"],
                   {"P": "#9c7a45", "R": "#8a2a22", "B": "#2a3f8a", "G": "#2a6a2a", "Y": "#c9a83a"}, 0.04)
    B["bookshelf"] = BlockType({**{f: books for f in ("front", "back", "right", "left")},
                                "top": plank, "bottom": plank})
    ct_top = p.grid(["BBBBBBBBBBBBBBBB", "BLLLLLLLLLLLLLLB", "BLDDDDLLLLDDDDLB", "BLDLLDLLLLDLLDLB",
                     "BLDDDDLLLLDDDDLB", "BLLLLLLLLLLLLLLB", "BLLLLLLLLLLLLLLB", "BLLLLLLLLLLLLLLB",
                     "BLLLLLLLLLLLLLLB", "BLLLLLLLLLLLLLLB", "BLLLLLLLLLLLLLLB", "BLDDDDLLLLDDDDLB",
                     "BLDLLDLLLLDLLDLB", "BLDDDDLLLLDDDDLB", "BLLLLLLLLLLLLLLB", "BBBBBBBBBBBBBBBB"],
                    {"B": "#6b4a2a", "L": "#b08a52", "D": "#5a3e22"}, 0.03)
    ct_side = planks(p, "#9c7a45")
    ct_side[2:9, 2:6] = _c("#7a7a7a")  # saw and tools hanging on the side
    ct_side[3:8, 10:13] = _c("#5a3e22")
    B["crafting_table"] = BlockType.fronted(ct_side, ct_side, ct_top, plank)
    stone_side = B["smooth_stone"].faces["front"]
    fur = B["cobblestone"].faces["front"].copy()
    fur[4:12, 4:12] = _c("#2a2a2a")
    fur[8:12, 5:11] = _c("#f2a13a")
    fur[9:12, 6:10] = _c("#ffe070")
    B["furnace"] = BlockType.fronted(fur, B["cobblestone"].faces["front"], stone_side)
    bf = B["iron_block"].faces["front"].copy()
    bf[5:13, 3:13] = _c("#3a3a3a")
    bf[9:13, 4:12] = _c("#f27a1a")
    B["blast_furnace"] = BlockType.fronted(bf, B["smooth_stone"].faces["front"], stone_side)
    barrel_side = planks(p, "#7a5a35")
    barrel_side[:, 0:1] = barrel_side[:, 15:16] = _c("#4a4a4a")
    barrel_side[3] = barrel_side[12] = _c("#4a4a4a")
    barrel_top = framed(p, "#8a6a40", "#4a4a4a")
    barrel_top[6:10, 6:10] = _c("#3a2a18")
    B["barrel"] = BlockType({**{f: barrel_side for f in ("front", "back", "right", "left")},
                             "top": barrel_top, "bottom": barrel_top})
    chest = planks(p, "#a0762e")
    chest[0] = chest[15] = chest[:, 0] = chest[:, 15] = _c("#4a3218")
    chest[5] = _c("#4a3218")
    chest[4:8, 7:9] = _c("#c0c0c0")
    B["chest"] = BlockType.fronted(chest, framed(p, "#a0762e", "#4a3218"), framed(p, "#a0762e", "#4a3218"))
    tnt_side = p.grid(["RRRRRRRRRRRRRRRR"] * 5 + ["WWWWWWWWWWWWWWWW", "WKKKWKKWKWKKKWWW", "WWKWWKWKKWWKWWWW",
                                                "WWKWWKWWKWWKWWWW", "WWWWWWWWWWWWWWWW"] + ["RRRRRRRRRRRRRRRR"] * 6,
                      {"R": "#c0271c", "W": "#e8e4dc", "K": "#1a1a1a"}, 0.04)
    tnt_top = framed(p, "#b02a20", "#8a1e18")
    tnt_top[6:10, 6:10] = _c("#3a3a3a")
    B["tnt"] = BlockType({**{f: tnt_side for f in ("front", "back", "right", "left")},
                          "top": tnt_top, "bottom": tnt_top})
    target = p.fill(N, N, "#e8dcd0", 0.03)
    yy, xx = np.mgrid[0:N, 0:N]
    rr = np.hypot(xx - 7.5, yy - 7.5)
    target[rr < 7.5] = _c("#c0271c")
    target[rr < 5.2] = _c("#e8dcd0")
    target[rr < 3] = _c("#c0271c")
    B["target"] = BlockType.pillar(target, B["hay"].faces["top"])
    disp = B["cobblestone"].faces["front"].copy()
    disp[5:11, 5:11] = _c("#1a1a1a")
    disp[6:10, 6:10] = _c("#3a3a3a")
    B["dispenser"] = BlockType.fronted(disp, B["cobblestone"].faces["front"], B["cobblestone"].faces["top"])
    piston_top = framed(p, "#b89a62", "#8a7040")
    piston_side = B["cobblestone"].faces["front"].copy()
    piston_side[0:4] = planks(p, "#b89a62")[0:4]
    B["piston"] = BlockType({**{f: piston_side for f in ("front", "back", "right", "left")},
                             "top": piston_top, "bottom": B["cobblestone"].faces["top"]})
    red = B["stone"].faces["front"].copy()
    red[6:10, :] = _c("#aa1010")
    B["redstone_block"] = u(framed(p, "#b01a12", "#7a0a08", 0.08))
    anvil = framed(p, "#474747", "#303030", 0.05)
    B["anvil_block"] = u(anvil)
    grind = framed(p, "#8a8a8a", "#5a5a5a", 0.04)
    B["smithing_table"] = BlockType.fronted(planks(p, "#3a2a22"), planks(p, "#3a2a22"),
                                            framed(p, "#2e2e36", "#5a3a2a"))
    fletch_top = planks(p, "#d4c08a")
    fletch_side = planks(p, "#c9b57a")
    fletch_side[2:6, 3:13] = _c("#8a2a22")  # feathers and arrows on the rack
    fletch_side[8:10, 2:14] = _c("#6b4a2a")
    B["fletching_table"] = BlockType.fronted(fletch_side, fletch_side, fletch_top)
    lect = planks(p, "#b08a52")
    lect[3:12, 4:12] = _c("#e8dcc0")
    lect[3:12, 7:9] = _c("#9a8a70")
    B["lectern_top"] = BlockType({**{f: planks(p, "#9c7a45") for f in FACES}, "top": lect})
    ench_side = framed(p, "#1b1428", "#3b2754")
    ench_top = p.fill(N, N, "#1b1428", 0.05)
    ench_top[2:14, 2:14] = _c("#a8252a")
    ench_top[5:11, 3:13] = _c("#e8dcc0")
    B["enchanting_table"] = BlockType({**{f: ench_side for f in FACES}, "top": ench_top})
    B["cauldron"] = BlockType({**{f: framed(p, "#3a3a3a", "#262626") for f in FACES},
                               "top": framed(p, "#3a62c8", "#2a2a2a")})
    B["composter"] = BlockType({**{f: planks(p, "#8a6a40") for f in FACES},
                                "top": framed(p, "#5a4020", "#8a6a40")})
    loom_side = planks(p, "#c9b085")
    loom_side[4:12, 3:13] = _c("#d8d0c0")
    B["loom"] = BlockType.fronted(loom_side, planks(p, "#c9b085"), framed(p, "#b09a70", "#8a7050"))
    B["grindstone_block"] = u(grind)
    B["stonecutter"] = BlockType({**{f: B["smooth_stone"].faces["front"] for f in FACES},
                                  "top": framed(p, "#8a8a8a", "#5a5a5a")})
    B["bone_block"] = pil(framed(p, "#e2dcc8", "#c8c0a8", 0.04), chiseled(p, "#e2dcc8"))
    B["sea_lantern"] = u(chiseled(p, "#cfe8e0"))
    B["glowstone"] = u(noise_fill(p, "#c9a45a", 0.12, (("#f7e0a0", 0.3),)))
    B["shroomlight"] = u(noise_fill(p, "#f09a4a", 0.1))
    B["beacon"] = u(framed(p, "#8ae8e8", "#cfe8f0", 0.03))
    B["white_carpet"] = B["white_wool"]
    return B


def block(name: str) -> BlockType:
    return blocks()[name]
