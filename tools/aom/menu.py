"""The main menu, Minecraft style: a Minecraft world on a clear day, and Minecraft's own menu background.

The Conquerors' main menu (interfac.drs 50189) is one 800x600 picture (frame 0) and, for every button, pictures
drawn over it at the button's place: the object cut out, with a yellow glow (the mouse is on it), with a white glow
(pressed), and plain. The game writes the button names above the objects, and the Single Player menu (title,
buttons, description) on the right, over the picture.

`scene()` draws the new picture: a Minecraft thing in each button's place, and a Minecraft menu button wherever the
game writes a name (`SIGNS`, measured on a screenshot of the game), on the left a village on a clear day, on the
right dark dirt, Minecraft's menu background. `pictures()` cuts every button picture out of it at the same place,
the thing darker while the mouse is on it (`DARKER`, the player asked; no glow); every picture keeps its size and
hotspot. The places were found by matching the original button pictures against the original picture; the build
leaves a menu whose picture sizes differ from these alone.

The menu's palette (50589) was made for the original night in the snow and has no greens, so the menu gets its own
(`palette`), and its screen files (`settings`) have the game draw the Single Player menu's buttons as Minecraft's
(grey, light and dark edges, a black outline) with white names, yellow under the mouse.
"""
from __future__ import annotations

import zlib
from functools import lru_cache
from typing import Optional

import numpy as np

from . import slp
from . import voxel as V
from .palette import Quantiser
from .textures import parse

W, H = 800, 600
MENU = 50189  # interfac.drs: the Conquerors main menu, drawn with its own palette
PALETTE = 50589
# button -> (its pictures, top left of the cut-out one, top left of the others), on the 800x600 picture
BUTTONS = {
    "single": ((10, 11, 12, 13), (313, 14), (309, 12)),
    "multi": ((14, 15, 16, 17), (267, 221), (263, 217)),
    "zone": ((18, 19, 20, 21), (275, 371), (271, 367)),
    "learn": ((22, 23, 24, 25), (0, 9), (0, 6)),
    "map": ((26, 27, 28, 29), (200, 277), (197, 273)),
    "history": ((30, 31, 32, 33), (107, 168), (103, 164)),
    "options": ((34, 35, 36, 37), (104, 352), (101, 347)),
    "exit": ((46, 47, 48), (7, 540), (5, 535)),
    "logo": ((49,), (107, 36), None),
    "banner": ((50, 51, 52), None, (0, 0)),
}
SIZES = {0: (800, 600), 10: (109, 184), 11: (120, 189), 14: (88, 124), 15: (97, 131), 18: (61, 56), 19: (67, 64),
         22: (121, 179), 23: (125, 187), 26: (63, 60), 27: (70, 67), 30: (94, 89), 31: (102, 97), 34: (87, 91),
         35: (95, 100), 46: (154, 60), 47: (153, 65), 49: (211, 111), 50: (427, 170)}
# where the game writes each button's name (measured on a screenshot of the game), with a Minecraft menu button
# behind it: all of the name on it, with room around
SIGNS = {"learn": (8, 9, 116, 31), "single": (313, 13, 423, 37), "history": (121, 166, 188, 188),
         "multi": (263, 218, 360, 241), "map": (181, 273, 276, 296), "options": (112, 348, 182, 371),
         "zone": (279, 367, 327, 388)}
TITLE_SIGN = (453, 3, 775, 53)
DESCRIPTION = (380, 490, 790, 597)
# the Single Player menu's six buttons (measured on photos of the game): the game draws them, its way
SUBMENU = [(462, y, 759, y + 39) for y in (90, 155, 221, 286, 351, 417)]
# the buttons darker while the mouse is on them and when pressed, instead of a glow (the player asked); only the
# thing, not the button its name is on
DARKER = {name: (0.72, 0.55) for name in ("single", "multi", "zone", "learn", "map", "history", "options", "exit")}
SKY = ("#6e9ff2", "#bcd5fa")
GRASS = "#6fa347"
BUTTON = {"fill": "#5e5e5e", "light": "#a4a4a4", "shade": "#383838", "edge": "#000000"}  # Minecraft's, darker
TOOLTIP = ("#100010", "#5000ff", "#28007f")  # Minecraft's tooltip: near black, a purple edge
# the menu's screen file: the game fills the Single Player menu's buttons with Minecraft's button grey, with its
# light and dark edges (outside in, top and left then bottom and right) and a black outline; names in white,
# the one the mouse is on in Minecraft's yellow
SCREEN = {"background_color": "#5e5e5e", "bevel_colors": ("#000000", "#a4a4a4", "#8a8a8a", "#484848", "#383838",
                                                          "#000000"),
          "text_color1": "255 255 255", "text_color2": "0 0 0", "focus_color1": "255 255 160",
          "focus_color2": "0 0 0"}


class Nearest:
    """Nearest-colour quantiser over a whole palette (the menu's own: no player colours to keep free)."""

    def __init__(self, palette: np.ndarray):
        from .palette import _lab
        self.palette = np.asarray(palette)
        self._lab = _lab
        self.lab = _lab(self.palette[:, :3].astype(np.float64))

    def indices(self, rgb: np.ndarray) -> np.ndarray:
        keys = (rgb[:, 0].astype(np.int64) << 16) | (rgb[:, 1].astype(np.int64) << 8) | rgb[:, 2].astype(np.int64)
        uniq, inverse = np.unique(keys, return_inverse=True)
        cols = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64)
        best = np.empty(len(uniq), np.int64)
        for a in range(0, len(uniq), 4096):
            d = ((self._lab(cols[a:a + 4096])[:, None] - self.lab[None]) ** 2).sum(-1)
            best[a:a + 4096] = d.argmin(1)
        return best[inverse]


def palette(original: np.ndarray, extra: Optional[np.ndarray] = None) -> np.ndarray:
    """The menu's own palette: the menu's first one has no greens and few sky blues (it was made for a night in the
    snow). Made from the new picture and `extra` colours (other pictures shown with it), keeping the twenty
    Windows colours at 0-9 and 246-255 where they are."""
    from .loadscreen import palette as median_cut
    img, _ = scene()
    swatches = [parse(c)[:3] for c in (BUTTON["fill"], BUTTON["light"], BUTTON["shade"], "#8a8a8a", "#484848",
                                       "#ffffff", "#ffffa0", *TOOLTIP)]
    rows = [img.reshape(-1, 3), np.repeat(np.array(swatches), 400, 0)]
    if extra is not None:
        rows.append(np.asarray(extra, float).reshape(-1, 3))
    return median_cut(original, np.concatenate(rows)[:, None, :])


def settings(palette: np.ndarray) -> dict[str, list[str]]:
    """The menu screen file's settings for these colours, the palette ones as indices into `palette` (never the
    Windows colours at 0-9 and 246-255: 0 would mean no fill)."""
    pal = np.asarray(palette, float)[:, :3]
    free = np.arange(10, 246)

    def index(colour: str) -> str:
        return str(int(free[np.abs(pal[free] - parse(colour)[:3] * 255).sum(1).argmin()]))

    out = {k: v.split() for k, v in SCREEN.items() if isinstance(v, str) and not v.startswith("#")}
    out["background_color"] = [index(SCREEN["background_color"])]
    out["bevel_colors"] = [index(c) for c in SCREEN["bevel_colors"]]
    return out


# --------------------------------------------------------------------------- drawing helpers


def _tex(name: str, face: str = "front") -> np.ndarray:
    return V.all_blocks()[name].faces[face][..., :3].astype(np.float64)


def _tile(img: np.ndarray, box, texture: np.ndarray, px: int = 2, dark: float = 1.0, turn: bool = False) -> None:
    """Fill a box with a block texture, px screen pixels per texel, blocks lined up on the picture's grid."""
    x0, y0, x1, y1 = box
    t = np.rot90(texture) if turn else texture
    t = np.repeat(np.repeat(t, px, 0), px, 1) * dark
    th, tw = t.shape[:2]
    ys, xs = np.mgrid[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = t[ys % th, xs % tw]


def _rect(img, box, colour) -> None:
    x0, y0, x1, y1 = box
    img[y0:y1, x0:x1] = parse(colour)[:3] if isinstance(colour, str) else colour


def _frame(img, box, outer="#1a120a", inner="#6a5236") -> None:
    x0, y0, x1, y1 = box
    for (a, b, c, d), col in (((x0, y0, x1, y0 + 1), outer), ((x0, y1 - 1, x1, y1), outer),
                              ((x0, y0, x0 + 1, y1), outer), ((x1 - 1, y0, x1, y1), outer),
                              ((x0 + 1, y0 + 1, x1 - 1, y0 + 2), inner), ((x0 + 1, y0 + 1, x0 + 2, y1 - 1), inner)):
        _rect(img, (a, b, c, d), col)


def _sprite(rows: list[str], legend: dict) -> np.ndarray:
    out = np.zeros((len(rows), len(rows[0]), 4))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                out[y, x, :3], out[y, x, 3] = parse(legend[ch])[:3], 1
    return out


def _blit(img, masks, name, spr: np.ndarray, x: int, y: int, k: int = 1, outline: bool = False) -> None:
    """Paste a sprite scaled k times (nearest) with its top left at (x, y), with a dark one-pixel outline like a
    Minecraft item if asked; its pixels join the object's mask."""
    s = np.repeat(np.repeat(spr, k, 0), k, 1)
    h, w = s.shape[:2]
    solid = np.zeros((H, W), bool)
    solid[y:y + h, x:x + w] = (s[..., 3] > 0.5)[:max(0, min(h, H - y)), :max(0, min(w, W - x))]
    if outline:
        ring = _outline(solid, 1)
        img[ring] = parse("#141414")[:3]
        solid |= ring
    region = img[y:y + h, x:x + w]
    inside = (s[..., 3] > 0.5)[:region.shape[0], :region.shape[1]]
    region[inside] = s[:region.shape[0], :region.shape[1], :3][inside]
    if name:
        masks.setdefault(name, np.zeros((H, W), bool))[solid] = True


def _mark(masks, name, box) -> None:
    x0, y0, x1, y1 = box
    masks.setdefault(name, np.zeros((H, W), bool))[y0:y1, x0:x1] = True


# --------------------------------------------------------------------------- the objects


def villager_face() -> np.ndarray:
    return _sprite(["ssssssss", "ssssssss", "ssssssss", "sbbbbbbs", "swgssgws", "sssnnsss", "sssnnsss",
                    "sssnnsss", "ssmnnmss", "ssssssss"],
                   {"s": "#b8866c", "b": "#4a2c22", "w": "#f0f0f0", "g": "#2f8a3a", "n": "#9a6c56", "m": "#7a5040"})


def shield() -> np.ndarray:
    """Minecraft's shield, white with a gold cross, in an iron rim."""
    rows = []
    for y in range(22):
        row = ""
        for x in range(12):
            edge = x in (0, 11) or y in (0, 21)
            cross = x in (5, 6) or y in (7, 8)
            row += "r" if edge else ("y" if cross and 1 <= x <= 10 else ("s" if x >= 9 else "w"))
        rows.append(row)
    return _sprite(rows, {"r": "#7c7c7c", "y": "#e2b53a", "w": "#e8e8e2", "s": "#c8c8c2"})


def open_book() -> np.ndarray:
    rows = ["cccccccccc..cccccccccc", "cppppppppp..pppppppppc", "cpllllllpp..pplllllllc", "cppppppppp..pppppppppc",
            "cplllllllp..plllllllpc", "cppppppppp..pppppppppc", "cpllllllpp..pplllllppc", "cppppppppp..pppppppppc",
            "cpllllllllddllllllllpc", "cppppppppp..pppppppppc", "cplllllpppddpplllllppc", "cppppppppp..pppppppppc",
            "ccccccccccddcccccccccc", ".bbbbbbbbbddbbbbbbbbb."]
    return _sprite(rows, {"c": "#6b3a1a", "p": "#f2ead2", "l": "#8a7a5e", "d": "#3a2210", "b": "#4a2a12"})


SWORD = ["............kkkk", "...........kbwbk", "..........kbwbkk", ".........kbwbk..", "........kbwbk...",
         ".......kbwbk....", "......kbwbk.....", ".kk..kbwbk......", ".kgkkbwbk.......", "..kggbbk........",
         "...kgbk.........", "..khkggk........", ".khk.kgk........", "khk...kk........", "kk..............",
         "................"]


def sword() -> np.ndarray:
    """Minecraft's diamond sword, blade up and to the right."""
    return _sprite(SWORD, {"k": "#0e3f3c", "b": "#33ebcb", "w": "#bafff5", "g": "#1f6f69", "h": "#6b4a2a"})


def crossed_swords() -> np.ndarray:
    """Two diamond swords crossed over a red and white shield."""
    out = _sprite(["................", "...rrrrrrrrrr...", "..rrwwwwwwwwrr..", "..rwwwwwwwwwwr..",
                   "..rwwwrrrrwwwr..", "..rwwwrrrrwwwr..", "..rwwwwwwwwwwr..", "..rrwwwwwwwwrr..",
                   "...rrwwwwwwrr...", "....rrwwwwrr....", ".....rrwwrr.....", "......rrrr......",
                   "................", "................", "................", "................"],
                  {"r": "#a82a24", "w": "#e8e2d8"})
    for s in (sword(), sword()[:, ::-1]):
        solid = s[..., 3] > 0
        out[solid] = s[solid]
    return out


def anvil() -> np.ndarray:
    return _sprite(["hhhhhhhhhhhhhhhh", "iiiiiiiiiiiiiiii", "dddddddddddddddd", ".....iiiiii.....",
                    ".....iiiiii.....", ".....dddddd.....", "...iiiiiiiiii...", "...dddddddddd...",
                    ".iiiiiiiiiiiiii.", ".dddddddddddddd.", ".kkkkkkkkkkkkkk."],
                   {"h": "#9a9a9a", "i": "#5e5e5e", "d": "#444444", "k": "#2a2a2a"})


def item_frame(inside: np.ndarray) -> np.ndarray:
    out = _sprite(["oooooooooooooo"] + ["oiiiiiiiiiiiio"] + ["oi" + "." * 10 + "io"] * 10 + ["oiiiiiiiiiiiio",
                                                                                        "oooooooooooooo"],
                  {"o": "#5a3a1e", "i": "#9c7a45"})
    out[2:12, 2:12] = inside
    return out


def map_item() -> np.ndarray:
    return _sprite(["pppppppppp", "pggppbbbpp", "pgggpbbbbp", "ppggppbbpp", "pppggppppp", "ppgggpprpp",
                    "pgggppprrp", "ppgpppppbp", "pppppppbbp", "pppppppppp"],
                   {"p": "#d9c89a", "g": "#6a9a3a", "b": "#3a6ab0", "r": "#c83030"})


def compass() -> np.ndarray:
    return _sprite(["..kkkkkk..", ".kggggggk.", "kgddddddgk", "kgdddrrdgk", "kgddrrddgk", "kgddwwddgk",
                    "kgdwwdddgk", "kgddddddgk", ".kggggggk.", "..kkkkkk.."],
                   {"k": "#2a2a2a", "g": "#8a8a8a", "d": "#3a3a4a", "r": "#d83030", "w": "#e8e8e8"})


LOGO = (("AGE OF", "gold_block", None, 2), ("MINECRAFT", "cobblestone", "grass_block", 3))  # text, block, top, depth


@lru_cache(maxsize=None)


def logo(width: int, blocks: tuple = LOGO) -> np.ndarray:
    """ "AGE OF MINECRAFT" in blocks, like Minecraft's own title: RGBA 0..1, `width` pixels wide."""
    from .render import Camera, fit_camera, render
    from .textures import Painter  # noqa: F401  (block textures are painted on first use)
    lines = []
    for text, face, top, depth in blocks:
        s = V.Structure("logo")
        x = 0
        for ch in text:
            glyph = GLYPHS[ch]
            for r, row in enumerate(glyph):
                for c, px in enumerate(row):
                    if px == "#":
                        block = top if top and not (r > 0 and glyph[r - 1][c] == "#") else face
                        for d in range(depth):
                            s.set(x + c, d, len(glyph) - 1 - r, block)
            x += len(glyph[0]) + 1
        s.origin = ((x - 1) / 2, depth / 2)
        lines.append(s.part(V.all_blocks()))
    heading, elevation = 84.0, 22.0
    probe = [fit_camera(root, heading, scale=1.0, pad=0, elevation=elevation) for root in lines]
    k = (width - 4) / probe[1].width
    frames = []
    for root, scale in zip(lines, (k * 0.7, k)):
        cam = fit_camera(root, heading, scale=scale, pad=2, elevation=elevation)
        frames.append(render(root, heading, camera=cam, shadow=False).to_rgba(1).astype(np.float64) / 255)
    out = np.zeros((frames[0].shape[0] + frames[1].shape[0], width, 4))
    y = 0
    for f in frames:
        x = (width - f.shape[1]) // 2
        region = out[y:y + f.shape[0], max(0, x):max(0, x) + min(width, f.shape[1])]
        region[...] = f[:, :region.shape[1]]
        y += f.shape[0]
    return out


GLYPHS = {  # a bold pixel font: strokes two blocks wide
    "A": [".#####.", "##...##", "##...##", "#######", "##...##", "##...##", "##...##"],
    "C": [".#####", "##....", "##....", "##....", "##....", "##....", ".#####"],
    "E": ["######", "##....", "##....", "#####.", "##....", "##....", "######"],
    "F": ["######", "##....", "##....", "#####.", "##....", "##....", "##...."],
    "G": [".######", "##.....", "##.....", "##..###", "##...##", "##...##", ".######"],
    "I": ["####", ".##.", ".##.", ".##.", ".##.", ".##.", "####"],
    "M": ["##....##", "###..###", "########", "##.##.##", "##....##", "##....##", "##....##"],
    "N": ["##...##", "###..##", "####.##", "##.####", "##..###", "##...##", "##...##"],
    "O": [".#####.", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."],
    "R": ["######.", "##...##", "##...##", "######.", "##.##..", "##..##.", "##...##"],
    "T": ["######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##.."],
    " ": ["...", "...", "...", "...", "...", "...", "..."],
}


# --------------------------------------------------------------------------- the picture


def _button(img, masks, name, box) -> None:
    """A Minecraft menu button (stone grey, a light top and left edge, a dark bottom and right, a black outline),
    where the game writes a button's name."""
    x0, y0, x1, y1 = box
    rng = np.random.default_rng(zlib.crc32(f"button {name}".encode()))
    img[y0:y1, x0:x1] = np.clip(parse(BUTTON["fill"])[:3] + rng.normal(0, 0.012, (y1 - y0, x1 - x0, 1)), 0, 1)
    img[y0 + 1:y0 + 2, x0 + 1:x1 - 1] = parse(BUTTON["light"])[:3]
    img[y0 + 1:y1 - 1, x0 + 1:x0 + 2] = parse(BUTTON["light"])[:3]
    img[y1 - 3:y1 - 1, x0 + 1:x1 - 1] = parse(BUTTON["shade"])[:3]
    img[y0 + 1:y1 - 1, x1 - 2:x1 - 1] = parse(BUTTON["shade"])[:3]
    edge = parse(BUTTON["edge"])[:3]
    img[y0, x0:x1] = img[y1 - 1, x0:x1] = edge
    img[y0:y1, x0] = img[y0:y1, x1 - 1] = edge
    if masks is not None:
        _mark(masks, name, box)


def _cloud(img, x: int, y: int, blocks: list[str]) -> None:
    """A flat, blocky Minecraft cloud: 8-pixel blocks, white, a little grey underneath."""
    for r, row in enumerate(blocks):
        for c, ch in enumerate(row):
            if ch == "#":
                a, b = x + c * 8, y + r * 8
                img[max(0, b):max(0, b + 8), max(0, a):max(0, a + 8)] = parse("#ffffff" if r < len(blocks) - 1
                                                                              else "#e2eaf7")[:3]


def _hills(img, heights: list[int], colour: str, top: str, step: int = 16, dark: float = 0.0) -> None:
    """A blocky skyline across the picture: one height per `step` columns, a `top` colour on its first block."""
    for k, h in enumerate(heights):
        a, b = k * step, (k + 1) * step
        img[h:470, a:b] = parse(colour)[:3] * (1 - dark)
        img[h:h + 8, a:b] = parse(top)[:3]


def _tree(img, x: int, ground: int, height: int = 3) -> None:
    """A small oak: a log trunk and a blocky crown of leaves (16-pixel blocks)."""
    _tile(img, (x + 16, ground - 16 * height, x + 32, ground), _tex("oak_log"), px=1, dark=0.9)
    for dx, dy in ((0, 1), (1, 1), (2, 1), (0, 2), (1, 2), (2, 2), (1, 3)):
        top = ground - 16 * (height + dy) + 16
        _tile(img, (x + dx * 16, top, x + dx * 16 + 16, top + 16), _tex("oak_leaves"), px=1, dark=0.85)


def _fence(img, x: int, y0: int, y1: int) -> None:
    """An oak fence post, 6 pixels wide."""
    _tile(img, (x, y0, x + 6, y1), _tex("oak_planks"), px=1, dark=0.8)
    img[y0:y1, x] = img[y0:y1, x + 5] = parse("#3a2a16")[:3]


def scene() -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """The 800x600 menu picture (RGB 0..1) and each button's mask (its object and the button its name is on).

    A Minecraft world on a clear day on the left, where the buttons are: a house with a lectern on its roof, a
    stone brick tower, green hills and snowy mountains, the block logo floating in the sky; every button name on
    a Minecraft menu button. On the right, where the game opens the Single Player menu, Minecraft's own menu
    background, dark dirt, and the game's description of a button in a Minecraft tooltip."""
    img = np.zeros((H, W, 3))
    masks: dict[str, np.ndarray] = {}
    yy = np.clip(np.linspace(0, 1, H) / 0.55, 0, 1)[:, None, None]
    img[:] = parse(SKY[0])[:3] * (1 - yy) + parse(SKY[1])[:3] * yy
    img[4:36, 262:294] = parse("#fff2a8")[:3]  # the square sun
    img[8:32, 266:290] = parse("#fffbe2")[:3]
    for x, y, blocks in ((136, 10, ["..####...", "#########"]), (-12, 196, [".#####", "########"]),
                         (200, 156, ["...###", "########"]), (150, 118, ["###.", "#####"])):
        _cloud(img, x, y, blocks)
    # far away: snowy mountains, then green hills with trees
    _hills(img, [262, 246, 230, 214, 222, 238, 254, 238, 222, 206, 214, 230, 246, 262, 254, 246, 238, 246, 254,
                 262, 270, 262, 254, 246, 254, 262, 270], "#9aaed3", "#f2f6ff")
    _hills(img, [310, 302, 294, 302, 310, 318, 310, 302, 294, 286, 294, 302, 310, 318, 326, 318, 310, 302, 310,
                 318, 326, 318, 310, 302, 310, 318, 326], "#5f9e45", "#79bf55")
    for x, ground, h in ((196, 318, 3), (236, 310, 2)):
        _tree(img, x, ground, h)

    # the house on the left: a flat roof with a fence and a lectern, oak planks above, spruce below
    _tile(img, (0, 258, 196, 266), _tex("stone_bricks"), px=1, dark=0.95)
    for x in range(0, 196, 24):
        _fence(img, x + 2, 238, 258)
    _tile(img, (0, 244, 196, 248), _tex("oak_planks"), px=1, dark=0.8)
    _tile(img, (0, 266, 196, 340), _tex("oak_planks"), px=1, dark=0.95)
    _tile(img, (0, 340, 196, 470), _tex("spruce_planks"), px=1, dark=0.9)
    for a in (0, 180):
        _tile(img, (a, 266, a + 16, 470), _tex("oak_log"), px=1, dark=0.85)
    _tile(img, (0, 332, 196, 348), _tex("oak_log"), px=1, dark=0.8, turn=True)
    _tile(img, (40, 280, 104, 324), _tex("glass"), px=1, dark=1.0)  # a window
    img[280:324, 40:104] = img[280:324, 40:104] * 0.4 + parse("#a9d3f5")[:3] * 0.6
    _frame(img, (38, 278, 106, 326), "#3a2a16", "#8a6a3a")
    _tile(img, (32, 406, 64, 470), _tex("door_spruce_lower"), px=2, dark=0.95)  # the door
    # the tower on the right of the buttons: stone bricks, with oak log corners and battlements
    _tile(img, (296, 60, 430, 470), _tex("stone_bricks"), px=1, dark=0.92)
    for k, x in enumerate(range(296, 430, 16)):
        if k % 2 == 0:
            _tile(img, (x, 44, x + 16, 60), _tex("stone_bricks"), px=1, dark=0.92)
    for a in (296, 414):
        _tile(img, (a, 60, a + 16, 470), _tex("oak_log"), px=1, dark=0.8)
    for x, y in ((372, 224), (372, 336)):  # arrow slits
        _rect(img, (x, y, x + 8, y + 24), "#1e1e22")

    # the ground: grass, a path, flowers
    grass = _tex("grass_block", "top") @ np.array([0.299, 0.587, 0.114])
    grass = parse(GRASS)[:3] * (grass / max(1e-3, float(grass.mean())))[..., None]  # Minecraft's plains green
    _tile(img, (0, 470, 430, 600), np.clip(grass, 0, 1), px=2)
    img[470:474, 0:430] = parse("#4f8a33")[:3]
    for y in range(474, 600, 2):
        half = 26 + (y - 474) * 0.55
        a, b = int(250 - half), int(250 + half)
        _tile(img, (max(0, a), y, min(430, b), y + 2), _tex("dirt_path", "top"), px=2, dark=0.95)
    from .nature import flower_sprite
    for name, x, y in (("poppy", 150, 500), ("dandelion", 186, 530), ("cornflower", 20, 512), ("poppy", 348, 516),
                       ("dandelion", 330, 560), ("oxeye", 110, 560), ("tulip", 60, 486)):
        f = flower_sprite(name)
        spr = np.concatenate([f[..., :3], (f[..., 3:4] > 0).astype(float)], -1)
        _blit(img, None, None, spr, x, y, 2)

    # the right: Minecraft's menu background, dark dirt, and the description in a Minecraft tooltip
    _tile(img, (430, 0, 800, 600), _tex("dirt"), px=2, dark=0.38)
    _tile(img, (430, 0, 800, 58), _tex("dirt"), px=2, dark=0.24)
    img[58:60, 430:800] = parse("#000000")[:3]
    img[60:61, 430:800] = parse("#4a4a4a")[:3]
    img[:, 430:432] = parse("#000000")[:3]
    x0, y0, x1, y1 = DESCRIPTION
    _rect(img, DESCRIPTION, TOOLTIP[0])
    for t, row in enumerate(range(y0 + 1, y1 - 1)):
        img[row, x0 + 1] = img[row, x1 - 2] = (parse(TOOLTIP[1])[:3] * (1 - t / (y1 - y0))
                                                 + parse(TOOLTIP[2])[:3] * t / (y1 - y0))
    img[y0 + 1, x0 + 1:x1 - 1] = parse(TOOLTIP[1])[:3]
    img[y1 - 2, x0 + 1:x1 - 1] = parse(TOOLTIP[2])[:3]

    # the buttons: a Minecraft thing, and a Minecraft menu button where the game writes its name
    # Learn to Play: a banner with a villager and a book, on an oak pole
    _fence(img, 110, 36, 238)
    _rect(img, (6, 32, 116, 37), "#5a3a1e")
    _mark(masks, "learn", (6, 32, 116, 37))
    _tile(img, (14, 37, 108, 186), _tex("white_wool"), px=2, dark=0.55)
    img[37:186, 14:108] *= np.array([0.55, 0.8, 1.35])
    img[37:186, 14:108] = np.clip(img[37:186, 14:108], 0, 1)
    _mark(masks, "learn", (14, 37, 108, 186))
    _blit(img, masks, "learn", villager_face(), 33, 50, 7, outline=True)
    _blit(img, masks, "learn", open_book(), 39, 134, 2, outline=True)
    # Single Player: a shield hanging from its button on a chain
    _rect(img, (364, 37, 370, 58), "#4a4a4a")
    _mark(masks, "single", (364, 37, 370, 58))
    _blit(img, masks, "single", shield(), 331, 58, 6, outline=True)
    # History: an open book on a lectern, on the house's roof
    _tile(img, (150, 228, 176, 252), _tex("spruce_planks"), px=1, dark=0.75)
    _tile(img, (134, 252, 192, 258), _tex("spruce_planks"), px=1, dark=0.6)
    _mark(masks, "history", (134, 228, 192, 258))
    _blit(img, masks, "history", open_book(), 130, 196, 3, outline=True)
    # Multiplayer: crossed diamond swords over a shield, on the tower
    _rect(img, (308, 241, 311, 247), "#6a6a6a")
    _blit(img, masks, "multi", crossed_swords(), 271, 247, 5, outline=True)
    # Map Editor: a map in an item frame, on a fence post
    _fence(img, 224, 340, 470)
    _blit(img, masks, "map", item_frame(map_item()), 206, 298, 3, outline=True)
    # Options: an anvil on a smooth stone block
    _tile(img, (118, 433, 174, 470), _tex("smooth_stone"), px=1, dark=0.9)
    _frame(img, (118, 433, 174, 470), "#2a2a2a", "#bdbdbd")
    _blit(img, masks, "options", anvil(), 106, 378, 5, outline=True)
    # Zone: a compass in an item frame, on the tower
    _blit(img, masks, "zone", item_frame(compass()), 283, 389, 3, outline=True)
    # Exit: an arrow-shaped Minecraft button pointing left, on a post
    _fence(img, 94, 594, 600)
    arrow = np.zeros((H, W), bool)
    ys, xs = np.mgrid[0:H, 0:W]
    arrow |= (xs >= 46) & (xs < 156) & (ys >= 552) & (ys < 594)
    arrow |= (xs >= 10) & (xs < 46) & (np.abs(ys - 573) <= (xs - 10) * 0.9)
    stone = np.zeros_like(img)
    _button(stone, None, "exit", (0, 540, 170, 600))
    img[arrow] = stone[arrow]
    rim = arrow & _outline(~arrow, 1)  # its black outline, and inside it a light top and a dark bottom edge
    bevel = arrow & ~rim & _outline(rim | ~arrow, 1)
    img[bevel & (ys < 573)] = parse(BUTTON["light"])[:3]
    img[bevel & (ys >= 573)] = parse(BUTTON["shade"])[:3]
    img[rim] = parse(BUTTON["edge"])[:3]
    masks["exit"] = arrow
    # the names, each on a Minecraft menu button
    for name, box in SIGNS.items():
        _button(img, masks, name, box)
    # the title: the block logo, floating in the sky with its shadow
    title = logo(206)
    tx, ty = 110, 36 + (111 - title.shape[0]) // 2
    shadow = title.copy()
    shadow[..., :3] = 0.08
    shadow[..., 3] *= 0.45
    for layer, (dx, dy) in ((shadow, (3, 4)), (title, (0, 0))):
        a = layer[..., 3:4]
        region = img[ty + dy:ty + dy + layer.shape[0], tx + dx:tx + dx + layer.shape[1]]
        region[...] = layer[:region.shape[0], :region.shape[1], :3] * a[:region.shape[0], :region.shape[1]] \
            + region * (1 - a[:region.shape[0], :region.shape[1]])
    masks["logo"] = np.zeros((H, W), bool)
    masks["logo"][ty:ty + title.shape[0], tx:tx + title.shape[1]] = title[..., 3] > 0.5
    masks["banner"] = masks["logo"] | masks["learn"] | masks["single"]
    return np.clip(img, 0, 1), masks


# --------------------------------------------------------------------------- the pictures the game uses


def _outline(mask: np.ndarray, width: int = 2) -> np.ndarray:
    grown = mask.copy()
    for _ in range(width):
        g = grown.copy()
        g[1:] |= grown[:-1]
        g[:-1] |= grown[1:]
        g[:, 1:] |= grown[:, :-1]
        g[:, :-1] |= grown[:, 1:]
        grown = g
    return grown & ~mask


def glow_colour(original: slp.SlpFrame, background: slp.SlpFrame, at: tuple[int, int], palette: np.ndarray,
                inside: Optional[np.ndarray] = None) -> Optional[np.ndarray]:
    """The colour of the glow a button picture draws around its object (None if it has none). `inside` is the
    object's own shape: a picture that only lights the object up has no glow."""
    x, y = at
    px = original.pixels
    h, w = px.shape
    bg = background.pixels[y:y + h, x:x + w]
    both = (px >= 0) & (px < 256) & (bg >= 0) & (bg < 256)
    a, b = palette[np.where(both, px, 0)].astype(float), palette[np.where(both, bg, 0)].astype(float)
    bright = both & (np.abs(a - b).sum(-1) > 100) & (a.sum(-1) > 450)
    if inside is not None:
        bright &= ~(inside | _outline(inside, 1))
    if bright.sum() < 20:
        return None
    return np.median(a[bright], axis=0) / 255


def _cut(f: slp.SlpFrame) -> bool:
    """A cut-out picture: the object alone, much of it transparent (the others only have a few clear corners)."""
    return float((f.pixels < 0).mean()) > 0.1


def pictures(original: list[slp.SlpFrame], palette: np.ndarray, quant: Quantiser) -> list[slp.SlpFrame]:
    """Every picture of the menu SLP redrawn: the new background, and each button's pictures cut from it at the
    same place, with the glow of the original around the new object. Pictures it doesn't know are kept."""
    img, masks = scene()
    codes = quant.indices(np.clip(img * 255 + 0.5, 0, 255).astype(np.int64).reshape(-1, 3)).reshape(H, W)
    out = list(original)
    out[0] = slp.SlpFrame(codes.astype(np.int16), original[0].hotspot)
    for name, (frames, cut_at, rect_at) in BUTTONS.items():
        mask = masks[name]
        silhouette = None  # the original object's shape, from its cut-out picture, where the others are
        if cut_at and rect_at and frames[0] < len(original) and _cut(original[frames[0]]):
            c = original[frames[0]].pixels >= 0
            silhouette = np.zeros(original[frames[1]].pixels.shape, bool) if len(frames) > 1 else None
            if silhouette is not None:
                dx, dy = cut_at[0] - rect_at[0], cut_at[1] - rect_at[1]
                hh, ww = min(c.shape[0], silhouette.shape[0] - dy), min(c.shape[1], silhouette.shape[1] - dx)
                silhouette[dy:dy + hh, dx:dx + ww] = c[:hh, :ww]
        for k in frames:
            if k >= len(original):
                continue
            f = original[k]
            h, w = f.pixels.shape
            cut = _cut(f)
            alone = rect_at is None  # a picture of the object only (the logo): no glow
            x, y = cut_at if (cut and cut_at) or alone else rect_at
            picture = img[y:y + h, x:x + w].copy()
            shape = mask[y:y + h, x:x + w]
            inside = silhouette if silhouette is not None and silhouette.shape == (h, w) else None
            plain = cut or alone or name in DARKER
            colour = None if plain else glow_colour(f, original[0], (x, y), palette, inside)
            if colour is not None:
                picture[_outline(shape)] = colour
            if name in DARKER and not cut and k in frames[1:3]:  # the thing darker, its name's button as it is
                thing = shape.copy()
                if name in SIGNS:
                    bx0, by0, bx1, by1 = SIGNS[name]
                    thing[max(0, by0 - y):max(0, by1 - y), max(0, bx0 - x):max(0, bx1 - x)] = False
                picture[thing] *= DARKER[name][frames.index(k) - 1]
            px = quant.indices(np.clip(picture * 255 + 0.5, 0, 255).astype(np.int64).reshape(-1, 3)).reshape(h, w)
            px = px.astype(np.int16)
            px[(~shape) if cut else (f.pixels < 0)] = slp.TRANSPARENT
            out[k] = slp.SlpFrame(px, f.hotspot)
    return out


def known(sizes: list[tuple[int, int]]) -> bool:
    """True if a menu SLP has the pictures this module knows, at their sizes."""
    return len(sizes) > 52 and all(sizes[k] == wh for k, wh in SIZES.items())
