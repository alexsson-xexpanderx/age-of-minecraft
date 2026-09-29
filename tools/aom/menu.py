"""The main menu, Minecraft style: a snowy village street at night, built from blocks.

The Conquerors' main menu (interfac.drs 50189) is one 800x600 picture (frame 0) and, for every button, pictures
drawn over it at the button's place: the object cut out, with a yellow glow (the mouse is on it), with a white glow
(pressed), and plain. The game writes the button names on the dark signs above the objects, and the Single Player
menu (title, buttons, description) on the right, over the picture.

`scene()` draws the new picture with a Minecraft object in each button's place and a dark sign wherever the game
writes. `pictures()` cuts every button picture out of it at the same place, with the glow around the new object;
every picture keeps its size and hotspot. The places were found by matching the original button pictures against
the original picture; the build leaves a menu whose picture sizes differ from these alone.
"""
from __future__ import annotations

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
# where the game writes: a dark sign under each button name, the Single Player title and its description
SIGNS = {"learn": (5, 7, 117, 32), "single": (312, 8, 397, 40), "history": (110, 166, 198, 186),
         "multi": (267, 219, 352, 238), "map": (199, 276, 256, 291), "options": (106, 349, 186, 368),
         "zone": (274, 369, 333, 383)}
TITLE_SIGN = (453, 3, 775, 53)
DESCRIPTION = (380, 490, 790, 597)
# the Single Player menu's six buttons (measured on photos of the game): the game draws only their edges and names,
# so the picture gets a solid plate behind each, a little bigger, and nothing shows through them
SUBMENU = [(462, y, 759, y + 39) for y in (90, 155, 221, 286, 351, 417)]
PLATE = "#1e1e1e"


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


def _blit(img, masks, name, spr: np.ndarray, x: int, y: int, k: int = 1) -> None:
    """Paste a sprite scaled k times (nearest) with its top left at (x, y); its pixels join the object's mask."""
    s = np.repeat(np.repeat(spr, k, 0), k, 1)
    h, w = s.shape[:2]
    solid = s[..., 3] > 0.5
    img[y:y + h, x:x + w][solid] = s[..., :3][solid]
    if name:
        masks.setdefault(name, np.zeros((H, W), bool))[y:y + h, x:x + w] |= solid


def _mark(masks, name, box) -> None:
    x0, y0, x1, y1 = box
    masks.setdefault(name, np.zeros((H, W), bool))[y0:y1, x0:x1] = True


def _line(grid: np.ndarray, p0, p1, colour, width: float = 1.0) -> None:
    """A line on a small sprite grid (RGBA), sampled densely."""
    (x0, y0), (x1, y1) = p0, p1
    n = int(max(abs(x1 - x0), abs(y1 - y0)) * 4) + 1
    for t in np.linspace(0, 1, n):
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        for dx in np.arange(-width / 2 + 0.5, width / 2, 1.0) if width > 1 else (0,):
            xi, yi = int(round(x + dx * 0.7)), int(round(y + dx * 0.7))
            if 0 <= yi < grid.shape[0] and 0 <= xi < grid.shape[1]:
                grid[yi, xi, :3], grid[yi, xi, 3] = parse(colour)[:3], 1


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

def _window(img, box, lit: float = 1.0) -> None:
    x0, y0, x1, y1 = box
    _rect(img, box, "#2a1a0e")
    glow = np.array([0.98, 0.82, 0.42]) * lit
    img[y0 + 3:y1 - 3, x0 + 3:x1 - 3] = glow
    img[y0 + 3:y1 - 3, (x0 + x1) // 2 - 1:(x0 + x1) // 2 + 1] = parse("#2a1a0e")[:3]
    img[(y0 + y1) // 2 - 1:(y0 + y1) // 2 + 1, x0 + 3:x1 - 3] = parse("#2a1a0e")[:3]


def _roof(img, x0, x1, base, px, block="spruce_planks", dark=0.5) -> None:
    """A stepped gable roof from x0 to x1 standing on `base`, with snow on every step."""
    step = 8 * px
    cx = (x0 + x1) / 2
    t = np.repeat(np.repeat(_tex(block), px, 0), px, 1) * dark
    snow = np.array([0.86, 0.9, 0.96])
    for k in range(0, int((x1 - x0) / 2 / step) + 1):
        a, b = int(x0 + k * step), int(x1 - k * step)
        top = base - (k + 1) * step
        if a >= b or top < 0:
            break
        ys, xs = np.mgrid[top:top + step, a:b]
        img[top:top + step, a:b] = t[ys % t.shape[0], xs % t.shape[1]]
        img[top:top + 1, a:b] = snow * 0.8


def _sign(img, masks, name, box) -> None:
    """A dark oak sign, where the game writes a name."""
    _tile(img, box, _tex("dark_oak_planks"), px=1, dark=0.42)
    _frame(img, box)
    _mark(masks, name, box)


def scene() -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """The 800x600 menu picture (RGB 0..1) and each button object's mask."""
    img = np.zeros((H, W, 3))
    masks: dict[str, np.ndarray] = {}
    yy = np.linspace(0, 1, H)[:, None, None]
    img[:] = np.array([0.03, 0.05, 0.15]) * (1 - yy) + np.array([0.09, 0.12, 0.26]) * yy  # the night sky
    rng = np.random.default_rng(11)
    for _ in range(110):
        x, y = int(rng.integers(0, W - 2)), int(rng.integers(0, 330))
        img[y:y + 2, x:x + 2] = np.array([0.85, 0.88, 1.0]) * rng.uniform(0.45, 1.0)
    img[150:174, 206:230] = parse("#e6e2c6")[:3]  # the square moon
    img[155:161, 211:217] = parse("#c8c4a6")[:3]
    img[165:169, 222:226] = parse("#c8c4a6")[:3]

    # the street: houses further back, small blocks
    for (x0, x1, base, wall, top, lit) in ((150, 290, 470, "spruce_planks", 215, ((175, 250, 205, 290),
                                                                                    (240, 330, 270, 372))),
                                           (285, 440, 470, "stone_bricks", 190, ((310, 230, 345, 272),
                                                                                  (380, 300, 415, 342)))):
        _tile(img, (x0, top, x1, base), _tex(wall), px=1, dark=0.42)
        _tile(img, (x0, top, x0 + 8, base), _tex("dark_oak_log"), px=1, dark=0.45)
        _tile(img, (x1 - 8, top, x1, base), _tex("dark_oak_log"), px=1, dark=0.45)
        _roof(img, x0 - 8, x1 + 8, top, 1, dark=0.3)
        for box in lit:
            _window(img, box, 0.85)
    # the house on the left: stone below, planks above, a striped awning and a lit window
    _tile(img, (0, 180, 200, 470), _tex("oak_planks"), px=2, dark=0.5)
    _tile(img, (0, 180, 200, 196), _tex("spruce_log"), px=2, dark=0.5, turn=True)
    _tile(img, (184, 180, 200, 470), _tex("spruce_log"), px=2, dark=0.5)
    for k, x in enumerate(range(0, 200, 16)):  # the market awning, red and white wool
        _rect(img, (x, 300, x + 16, 330), "#b83a32" if k % 2 == 0 else "#e8e2d8")
    img[300:302, 0:200] = parse("#e8eef6")[:3]
    _tile(img, (0, 330, 184, 470), _tex("stone_bricks"), px=2, dark=0.45)
    _window(img, (24, 372, 96, 446))
    _tile(img, (0, 440, 150, 470), _tex("oak_planks"), px=2, dark=0.6)  # the stall's counter, with fruit
    for k, x in enumerate(range(4, 146, 24)):
        _tile(img, (x, 424, x + 20, 444), _tex("melon" if k % 2 else "pumpkin"), px=1, dark=0.75)

    # the blacksmith on the right
    _tile(img, (430, 0, 800, 272), _tex("spruce_planks"), px=2, dark=0.45)
    _tile(img, (430, 0, 462, 600), _tex("dark_oak_log"), px=2, dark=0.5)
    _tile(img, (768, 0, 800, 600), _tex("dark_oak_log"), px=2, dark=0.5)
    _tile(img, (462, 240, 768, 272), _tex("dark_oak_log"), px=2, dark=0.5, turn=True)
    _window(img, (528, 62, 610, 128))
    _window(img, (658, 62, 740, 128))
    _tile(img, (462, 272, 768, 490), _tex("dark_oak_planks"), px=2, dark=0.3)  # inside: dark, with a forge
    _tile(img, (700, 400, 764, 490), _tex("lava"), px=2, dark=0.6)
    _tile(img, (692, 392, 772, 402), _tex("stone_bricks"), px=1, dark=0.5)
    for x in range(482, 690, 44):  # a rack of diamond swords on the wall
        _blit(img, masks, None, sword(), x, 300, 2)
    for x0, y0, x1, y1 in SUBMENU:  # solid behind the Single Player menu's buttons
        _rect(img, (x0 - 5, y0 - 5, x1 + 5, y1 + 5), PLATE)
    _sign(img, masks, "title", TITLE_SIGN)

    # the ground: snow, and a cobblestone path
    _tile(img, (0, 470, 430, 600), _tex("snow"), px=2, dark=0.82)
    img[470:600, 0:430] *= np.array([0.86, 0.92, 1.05])
    for _ in range(160):  # it glitters
        x, y = int(rng.integers(0, 428)), int(rng.integers(472, 598))
        img[y:y + 2, x:x + 2] = (0.97, 0.98, 1.0)
    for y in range(470, 600, 2):
        half = 40 + (y - 470) * 0.9
        a, b = int(290 - half), int(290 + half)
        _tile(img, (max(0, a), y, min(430, b), y + 2), _tex("cobblestone"), px=2, dark=0.55)
    _tile(img, (8, 470, 40, 534), _tex("barrel", "right"), px=2, dark=0.55)
    _tile(img, (380, 440, 428, 488), _tex("hay"), px=2, dark=0.55)
    _tile(img, DESCRIPTION, _tex("deepslate_tiles"), px=2, dark=0.55)  # where the game describes a button
    _frame(img, DESCRIPTION, "#101014", "#4a4a52")
    _tile(img, (156, 446, 188, 478), _tex("barrel", "right"), px=2, dark=0.5)

    # the buttons: a sign for each name, and a Minecraft thing under it
    for name, box in SIGNS.items():
        _sign(img, masks, name, box)
    # Learn to Play: a banner with a villager and a book
    _rect(img, (6, 32, 116, 36), "#5a3a1e")
    _mark(masks, "learn", (6, 32, 116, 36))
    _tile(img, (14, 36, 108, 186), _tex("white_wool"), px=2, dark=0.55)
    img[36:186, 14:108] *= np.array([0.55, 0.8, 1.35])
    _mark(masks, "learn", (14, 36, 108, 186))
    _blit(img, masks, "learn", villager_face(), 33, 48, 7)
    book = open_book()
    _blit(img, masks, "learn", book, 39, 132, 2)
    # Single Player: a shield on an iron post
    _rect(img, (364, 40, 370, 58), "#4a4a4a")
    _mark(masks, "single", (364, 40, 370, 58))
    _blit(img, masks, "single", shield(), 331, 58, 6)
    # History: an open book
    _blit(img, masks, "history", open_book(), 110, 194, 4)
    # Multiplayer: crossed diamond swords over a shield
    _rect(img, (308, 238, 311, 246), "#6a6a6a")
    _blit(img, masks, "multi", crossed_swords(), 271, 246, 5)
    # Map Editor: a map in an item frame
    _blit(img, masks, "map", item_frame(map_item()), 206, 294, 3)
    # Options: an anvil
    _blit(img, masks, "options", anvil(), 106, 378, 5)
    # Zone: a compass in an item frame
    _blit(img, masks, "zone", item_frame(compass()), 283, 386, 3)
    # Exit: an arrow-shaped sign pointing left
    arrow = np.zeros((H, W), bool)
    ys, xs = np.mgrid[0:H, 0:W]
    arrow |= (xs >= 46) & (xs < 156) & (ys >= 552) & (ys < 594)
    arrow |= (xs >= 10) & (xs < 46) & (np.abs(ys - 573) <= (xs - 10) * 0.9)
    planks = np.zeros_like(img)
    _tile(planks, (0, 530, 170, 600), _tex("dark_oak_planks"), px=2, dark=0.55)
    img[arrow] = planks[arrow]
    edge = arrow & ~(np.roll(arrow, 1, 0) & np.roll(arrow, -1, 0) & np.roll(arrow, 1, 1) & np.roll(arrow, -1, 1))
    img[edge] = parse("#140c06")[:3]
    masks["exit"] = arrow
    # the title banner: white wool with the block logo
    _rect(img, (116, 40, 120, 146), "#5a3a1e")
    _rect(img, (306, 40, 310, 146), "#5a3a1e")
    wool = _tex("white_wool")
    _tile(img, (120, 44, 306, 142), wool.mean((0, 1)) + (wool - wool.mean((0, 1))) * 0.3, px=2, dark=0.95)
    _mark(masks, "logo", (116, 40, 310, 146))
    title = logo(180)
    ty = 44 + (98 - title.shape[0]) // 2
    a = title[..., 3:4]
    region = img[ty:ty + title.shape[0], 123:123 + title.shape[1]]
    region[...] = title[..., :3] * a + region * (1 - a)
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
            colour = None if cut or alone else glow_colour(f, original[0], (x, y), palette, inside)
            if colour is not None:
                picture[_outline(shape)] = colour
            px = quant.indices(np.clip(picture * 255 + 0.5, 0, 255).astype(np.int64).reshape(-1, 3)).reshape(h, w)
            px = px.astype(np.int16)
            px[(~shape) if cut else (f.pixels < 0)] = slp.TRANSPARENT
            out[k] = slp.SlpFrame(px, f.hotspot)
    return out


def known(sizes: list[tuple[int, int]]) -> bool:
    """True if a menu SLP has the pictures this module knows, at their sizes."""
    return len(sizes) > 52 and all(sizes[k] == wh for k, wh in SIZES.items())
