"""The game's other screens (game setup, history, the dialogues, the loading screen), Minecraft style.

Each screen is described by a small text file in interfac.drs (a "bina" entry, 50001-50099 in the Conquerors)
with one setting per line: its background pictures for 800x600, 1024x768 and 1280x1024 ("background1_files" to
"background3_files"), its palette ("palette_file"), and the colours the game draws its buttons and text in
("bevel_colors", "text_color1", ...). `read()` finds every one of them, and `pictures()` every screen picture
(plus every other large picture in interfac.drs); the build saves them as PNG files (screen_originals/) and lists
the screen files in the report.

Almost every screen is a light parchment the game writes on, in black or in light text with a black shadow. So
the "deepslate hall" keeps the parchment as light as it was: each sheet becomes a window in the grey of
Minecraft's inventory, with straight edges (its tears filled, what sticks out cut off) and Minecraft's bevel;
the dark frames around it become deepslate tiles and the wood (crates, the plaques titles are written on) dark oak
planks, as dark as the original. Pictures without parchment (the achievements, the blue and green dialogue
backgrounds) are one solid colour, the grey of Minecraft's inventory slots: the game writes the achievements in
each player's colour, and on a texture or a dark or light background some of those can't be read. A wooden board
is solid dark oak. The loading screen is Minecraft's dark dirt with the block logo in grey stone. The
achievements' flags become Minecraft banners in their own colours, with a black stripe where the game writes each
player's name (in white, or in a colour the game chooses, which can be the flag's own).

Each picture is drawn in every palette the game shows it in (`quantise`), and only the pictures in RESTYLED, at
those sizes, are changed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from . import interface as I
from . import slp
from . import voxel as V
from .palette import _lab
from .textures import parse as colour

KEYS = ("background1_files", "background2_files", "background3_files", "palette_file", "button_file",
        "popup_dialog_sin", "bevel_colors", "text_color1")
MAIN_PALETTE = 50500
INTERFACE = range(50000, 60000)  # the ids of interfac.drs's files (the sprites' ids are lower)
PANELS = range(51101, 51161)  # the in-game panels: interface.py
MIN_SIZE = (250, 130)  # smaller pictures are buttons and icons, not screens
ALSO_SAVED = (50761, 50762, 50765, 50769)  # smaller pictures of the achievements: icons, flags, tabs, team shields
LOADING = 50163  # the Conquerors' loading screen (screen file 50063)
FLAGS = 50762  # the achievements' flags, one picture per player colour: the game writes each player's name on one
TABS = 50765  # the achievements' tabs (Score ... Timeline), each as it looks chosen and not chosen
TEAMS = 50769  # the achievements' team marks: none, then teams 1 to 4
RESTYLED = {  # picture -> its size: the screens this module redraws
    50100: (800, 600), 50101: (1024, 768), 50102: (1280, 1024), 50103: (800, 600), 50104: (800, 600),  # setup
    50270: (388, 258), 50190: (259, 138), 50202: (800, 600), 50204: (800, 600),  # their dialogues
    50212: (231, 150), 50221: (796, 534), 50222: (316, 326), 50223: (481, 518), 50224: (595, 548),  # in the game:
    50225: (716, 504), 50226: (594, 630), 53208: (603, 518),  # menu, diplomacy, objectives, chat
    50127: (273, 182), 50161: (800, 600), 50149: (800, 600), 50145: (800, 600), 50763: (268, 270),  # editor, history
    53161: (500, 408), 53162: (500, 408), 53163: (500, 408), 53164: (500, 408),  # the campaigns' dialogues
    53171: (500, 408), 53172: (500, 408), 53173: (500, 408), 53174: (500, 408),
    LOADING: (800, 600), FLAGS: None, TABS: None, TEAMS: None,
}
SHOWN_WITH = {FLAGS: 50061, TABS: 50061, TEAMS: 50061}  # no screen file names them: shown on the achievements
LAYOUTS = {  # sheets that are given, not found: (x0, y0, x1, y1) on the picture
    50104: {"insets": [(503, 50, 790, 495)]},  # the game settings' own sheet
    50161: {"sheets": [(0, 10, 251, 588), (262, 10, 792, 588)], "insets": [(8, 18, 238, 390)]},  # the history book
    50149: {"sheets": [(26, 0, 800, 540)], "window": "dark", "wood": [(0, 540, 800, 600)]},  # the achievements:
    # white titles and every player's colour on a dark sheet; the tabs sit on the wooden table under it
    50763: {"window": "dark"},  # the timeline's background
}
LUMA = I.LUMA
PAPER, DARK = 0.38, 0.45  # parchment is lighter than PAPER; a picture darker than DARK on average is all deepslate
STONE, WOOD = 0.3, 0.24  # how light the deepslate and the planks are
# the windows: (fill, light edge, dark edge). The game writes in white, cream, black and the players' colours: all
# of them can be read on the middle grey; the dark one is for the achievements (white, cream and player colours)
WINDOWS = {"mid": ("#6b6b6b", "#9a9a9a", "#3a3a3a"), "dark": ("#373737", "#5c5c5c", "#1c1c1c")}
SOLID = WINDOWS["dark"][0]  # a picture without parchment (the dark dialogue backgrounds)


@dataclass
class Screen:
    id: int  # the screen file's id in interfac.drs
    fields: dict[str, list[str]] = field(default_factory=dict)  # each setting's words

    def _resource(self, key: str) -> Optional[int]:
        """The first resource id on a setting's line ("csbkg1a.slp none 50117 -1" -> 50117)."""
        for word in self.fields.get(key, []):
            try:
                n = int(word)
            except ValueError:
                continue
            if n > 0:
                return n
        return None

    @property
    def backgrounds(self) -> list[int]:
        found = [self._resource(f"background{k}_files") for k in (1, 2, 3)]
        return [n for n in found if n is not None]

    @property
    def palette(self) -> Optional[int]:
        return self._resource("palette_file")


def parse(data: bytes) -> dict[str, list[str]]:
    """A screen file's settings; empty if it isn't one."""
    text = data.decode("latin-1", "replace")
    if not any(k in text for k in KEYS):
        return {}
    out = {}
    for line in text.splitlines():
        words = line.split()
        if words and words[0][0].isalpha():
            out[words[0].lower()] = words[1:]
    return out if any(k in out for k in KEYS) else {}


def read(ids: list[int], get: Callable[[int], Optional[bytes]]) -> list[Screen]:
    """Every screen file among these data file ids."""
    out = []
    for fid in sorted(ids):
        data = get(fid)
        fields = parse(data) if data and len(data) < 16384 else {}
        if fields:
            out.append(Screen(fid, fields))
    return out


def pictures(screens: list[Screen], slp_ids: list[int], get: Callable[[int], Optional[bytes]],
             skip: set[int]) -> dict[int, int]:
    """Picture id -> the palette it is drawn with: every screen's backgrounds, then every other picture at least
    MIN_SIZE big (the main palette, as no screen file names them). Skips the panels and `skip`."""
    out: dict[int, int] = {}
    for s in screens:
        for sid in s.backgrounds:
            if sid not in skip and get(sid) is not None:
                out.setdefault(sid, s.palette or MAIN_PALETTE)
    for sid in sorted(slp_ids):
        if sid in out or sid in skip or sid in PANELS:
            continue
        data = get(sid)
        try:
            sizes = slp.info(data).sizes if data else []
        except (ValueError, IndexError):
            continue
        if sid in ALSO_SAVED or any(w >= MIN_SIZE[0] and h >= MIN_SIZE[1] for w, h, _, _ in sizes):
            out[sid] = MAIN_PALETTE
    return out


def palettes(screens: list[Screen]) -> dict[int, list[int]]:
    """Picture id -> every palette a screen shows it in (a setup picture serves two screens, in two palettes)."""
    out: dict[int, list[int]] = {}
    for s in screens:
        for sid in s.backgrounds:
            pal = s.palette or MAIN_PALETTE
            if pal not in out.setdefault(sid, []):
                out[sid].append(pal)
    return out


def palette_ids(sid: int, screens: list[Screen]) -> list[int]:
    """The palettes a picture is drawn in: those of every screen that shows it (SHOWN_WITH for the ones no screen
    file names), or the main palette."""
    if sid in SHOWN_WITH:
        host = next((s for s in screens if s.id == SHOWN_WITH[sid] and s.palette), None)
        return [host.palette] if host else [MAIN_PALETTE]
    return palettes(screens).get(sid, [MAIN_PALETTE])


# --------------------------------------------------------------------------- masks

def _padded(f, m: np.ndarray, r: int) -> np.ndarray:
    """f on m, with r pixels around it that are not in m (the outside is not parchment)."""
    return f(np.pad(m, r))[r:-r, r:-r]


def _opening(m: np.ndarray, r: int) -> np.ndarray:
    return _padded(lambda b: I._grow(I._shrink(b, r), r), m, r + 1)


def _blur(a: np.ndarray, r: int, m: np.ndarray) -> np.ndarray:
    """The mean of a over the pixels of m in a box 2r+1 wide around each pixel."""
    def box(x):
        c = np.pad(np.pad(x, r, mode="edge").cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        k = 2 * r + 1
        return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return box(a * m) / np.maximum(box(m.astype(np.float64)), 1e-9)


def _label(m: np.ndarray) -> tuple[np.ndarray, int]:
    """Connected parts of m (4-neighbours), numbered from 1, found run by run."""
    parent: list[int] = []

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    runs, prev = [], []
    for y in range(m.shape[0]):
        d = np.diff(np.concatenate(([0], m[y].astype(np.int8), [0])))
        cur = []
        for s, e in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            rid = len(parent)
            parent.append(rid)
            for ps, pe, pid in prev:
                if ps < e and pe > s:
                    parent[find(pid)] = find(rid)
            cur.append((s, e, rid))
            runs.append((y, s, e, rid))
        prev = cur
    lab = np.zeros(m.shape, np.int32)
    ids: dict[int, int] = {}
    for y, s, e, rid in runs:
        lab[y, s:e] = ids.setdefault(find(rid), len(ids) + 1)
    return lab, len(ids)


def _fill_holes(m: np.ndarray, max_area: float) -> np.ndarray:
    """m with the small parts of ~m it encloses filled (the ornaments drawn on the parchment)."""
    lab, n = _label(~m)
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    small = [k for k in range(1, n + 1) if sizes[k] < max_area and k not in edge]
    return m | np.isin(lab, small)


def _rectangle(paper: np.ndarray, opaque: np.ndarray, notch: int = 12) -> np.ndarray:
    """The parchment as a Minecraft window: a rectangle with straight edges where most of its edge is (the tears
    filled, what sticks out cut off), minus the big things inside it that aren't parchment (a crate, a plaque)."""
    if not paper.any():
        return paper
    ys, xs = np.nonzero(paper)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    box = paper[y0:y1, x0:x1]

    def depth(b: np.ndarray) -> int:  # how far in from one side the edge mostly is
        return int(np.percentile(np.argmax(b, axis=1)[b.any(1)], 25))

    rect = np.zeros_like(paper)
    rect[y0 + depth(box.T):y1 - depth(box[::-1].T), x0 + depth(box):x1 - depth(box[:, ::-1])] = True
    return rect & ~_boxes(_opening(rect & ~paper, notch), 0.015 * paper.size) & opaque


def _boxes(m: np.ndarray, min_area: float) -> np.ndarray:
    """Each part of m at least min_area big as its bounding box (crates and plaques are square); the rest dropped."""
    lab, n = _label(m)
    out = np.zeros_like(m)
    for k in np.nonzero(np.bincount(lab.ravel(), minlength=n + 1)[1:] >= min_area)[0] + 1:
        ys, xs = np.nonzero(lab == k)
        out[ys.min():ys.max() + 1, xs.min():xs.max() + 1] = True
    return out


def sheets(rgb: np.ndarray, opaque: np.ndarray, sid: int = 0) -> np.ndarray:
    """Where the parchment is: the sheets the game writes on."""
    lay = LAYOUTS.get(sid, {})
    if "sheets" in lay:
        paper = np.zeros_like(opaque)
        for x0, y0, x1, y1 in lay["sheets"]:
            paper[y0:y1, x0:x1] = True
        return paper & opaque
    lum = rgb @ LUMA
    if not opaque.any() or lum[opaque].mean() < DARK:
        return np.zeros_like(opaque)
    paper = _opening(opaque & (_blur(lum, 3, opaque) > PAPER), 4)
    paper = _fill_holes(paper, 0.02 * opaque.size)
    return _rectangle(paper, opaque)


# --------------------------------------------------------------------------- painting

def _tiled(name: str, shape: tuple[int, int], brightness: float) -> np.ndarray:
    """A block's texture over a whole picture, 2 screen pixels to a texel, as light as `brightness`."""
    tex = V.all_blocks()[name].faces["front"][..., :3].astype(np.float64)
    big = tex.repeat(I.PIXEL, 0).repeat(I.PIXEL, 1)
    reps = (shape[0] // big.shape[0] + 1, shape[1] // big.shape[1] + 1, 1)
    return np.clip(np.tile(big, reps)[:shape[0], :shape[1]] * brightness / (tex @ LUMA).mean(), 0, 1)


def hall(rgb: np.ndarray, opaque: np.ndarray, sid: int = 0) -> np.ndarray:
    """A screen picture (RGB 0..1) as the deepslate hall; every pixel keeps its place, transparency stays."""
    lum = rgb @ LUMA
    paper = sheets(rgb, opaque, sid)
    rest = opaque & ~paper
    shadow = rest & (lum < 0.07) & ~I._shrink(opaque, 3)  # the dots of a drop shadow outside: they stay
    warm = (rgb[..., 0] - rgb[..., 2] > 0.2).astype(np.float64)
    wood = rest & ~shadow & (_blur(warm, 3, rest) > 0.5)
    out = rgb.copy()
    if not paper.any():  # no parchment: the game writes straight on it, so one solid colour
        tex = V.all_blocks()["dark_oak_planks"].faces["front"][..., :3].reshape(-1, 3).mean(0)
        board = wood.sum() > 0.5 * rest.sum()  # a wooden board
        out[rest & ~shadow] = tex * WOOD / (tex @ LUMA) if board else colour(SOLID)[:3]
        return out
    wood = _boxes(_opening(wood, 3), 0.01 * opaque.size) & rest & ~shadow
    for x0, y0, x1, y1 in LAYOUTS.get(sid, {}).get("wood", []):
        wood[y0:y1, x0:x1] = rest[y0:y1, x0:x1]
    stone = rest & ~shadow & ~wood
    out[stone] = _tiled("deepslate_tiles", opaque.shape, STONE)[stone]
    out[wood] = _tiled("dark_oak_planks", opaque.shape, WOOD)[wood]
    lay = LAYOUTS.get(sid, {})
    whole = paper.all() or (opaque.all() and paper.mean() > 0.97)
    fill, light, shade = WINDOWS[lay.get("window", "mid")]
    if whole:  # a texture the game fills a dialogue with: no window edges of its own
        out[paper] = colour(fill)[:3]
        return out
    I._bevel(out, paper, fill, light, shade, I.GUI["edge"])
    for x0, y0, x1, y1 in lay.get("insets", []):  # a sheet on the sheet: sunk in, like a slot
        m = np.zeros_like(paper)
        m[y0:y1, x0:x1] = True
        I._bevel(out, m & paper, "#606060", shade, light, None)
    return out


def loading(shape: tuple[int, int]) -> np.ndarray:
    """The loading screen: Minecraft's dark dirt, with the block logo in grey stone (its palette has greys, not
    gold or green)."""
    from .menu import STONE_LOGO, logo
    out = _tiled("dirt", shape, 0.11)
    h, w = shape
    mark = logo(int(w * 0.65), STONE_LOGO)
    y, x = int(h * 0.25), (w - mark.shape[1]) // 2
    a = mark[..., 3:4]
    region = out[y:y + mark.shape[0], x:x + mark.shape[1]]
    region[...] = mark[..., :3] * a + region * (1 - a)
    return out


def banner(rgb: np.ndarray, opaque: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A flag (RGB 0..1, and where it is drawn) as a Minecraft banner the size of the original: wool in the flag's
    own colours (they are in its palette) on a dark oak pole, its end cut like a swallowtail, and across its middle,
    where the game writes the player's name (on two lines if it is long), a black stripe (Minecraft's "fess"
    pattern), so a name in white or in a player's colour can be read on it."""
    h, w = opaque.shape
    rows = np.nonzero(opaque.mean(1) > 0.6)[0]  # the original's cloth, not the shadow under it
    top, bottom = (int(rows.min()), int(rows.max()) + 1) if len(rows) else (4, h - 6)
    mid = (top + bottom) // 2
    ys, xs = np.mgrid[0:h, 0:w]
    cloth_px = rgb[opaque & (ys >= top) & (ys < bottom)]
    if len(cloth_px):  # its own colour: the pixels nearest its usual hue (not the green shadow's)
        hue = cloth_px - (cloth_px @ LUMA)[:, None]
        off = np.abs(hue - np.median(hue, axis=0)).sum(1)
        cloth_px = cloth_px[off <= np.percentile(off, 60)]
    ramp = cloth_px[np.argsort(cloth_px @ LUMA)] if len(cloth_px) else np.full((1, 3), 0.5)
    wool = V.all_blocks()["white_wool"].faces["front"][..., :3] @ LUMA
    shade = (wool - wool.min()) / max(1e-6, np.ptp(wool))  # the wool's weave, 0..1
    shade = np.tile(shade.repeat(I.PIXEL, 0).repeat(I.PIXEL, 1), (h // (16 * I.PIXEL) + 1, w // (16 * I.PIXEL) + 1))
    out = ramp[((0.35 + 0.35 * shade[:h, :w]) * (len(ramp) - 1)).astype(int)]  # its middle tones, not the folds
    stripe = (ys >= top + 5) & (ys < bottom - 5)  # tall enough for a name on two lines
    out[stripe] = _tiled("black_wool", (h, w), 0.09)[stripe]
    cloth = (ys >= top) & (ys < bottom) & (xs >= 6) & (xs < w - 1)
    cloth &= ~(w - 1 - xs < (bottom - top) // 2 - np.abs(ys - mid) * 0.9)  # the swallowtail cut
    out[cloth & ~I._shrink(cloth, 1)] = 0.05
    pole = (xs < 6) & (ys >= max(0, top - 4)) & (ys < min(h, bottom + 6))
    out[pole] = _tiled("dark_oak_log", (h, w), 0.2)[pole]
    out[pole & ((xs == 0) | (xs == 5))] = 0.05
    return out, cloth | pole


def tab(rgb: np.ndarray, opaque: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """An achievements tab as a Minecraft tab (RGB 0..1, and where it is drawn), the size of the original. Its top
    rows carry on the sheet above it, under the Play Again and Main Menu buttons: those are left out, so the tab
    no longer runs into them. A chosen tab (no dark edge at its top) is the dark window's grey and opens into the
    window; the others are darker, each a button on the wooden floor, with a gap between them."""
    h, w = opaque.shape
    lum = rgb @ LUMA
    rows = lum[:, 15:-15].mean(1) if w > 30 else lum.mean(1)
    chosen = rows[8:34].min() > 0.75 * np.median(rows)  # no dark edge between the sheet and the tab
    top = 16 if chosen else 20
    ys, xs = np.mgrid[0:h, 0:w]
    body = (ys >= top) & (xs >= 2) & (xs < w - 2)
    fill, light, shade = WINDOWS["dark"] if chosen else ("#262626", "#474747", "#141414")
    out = np.zeros((h, w, 3))
    out[body] = colour(fill)[:3]
    ring = body & ~I._shrink(body, 1)
    if chosen:  # open at the top
        ring &= ys > top
    inner = body & ~ring
    out[inner & ~I._shrink(inner, I.PIXEL) & ((xs < 6) | (ys < top + 4 + I.PIXEL))] = colour(light)[:3]
    out[inner & ~I._shrink(inner, I.PIXEL) & (xs >= w - 6)] = colour(shade)[:3]
    out[ring] = 0.0
    return out, body


DIGITS = {"1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
          "2": [".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"],
          "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
          "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."]}


def team_mark(k: int, opaque: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Team mark k (RGB 0..1, and where it is drawn): 0 is no team, a stone dash; 1 to 4 a Minecraft shield (iron
    rim, white face) with the team's number on it."""
    h, w = opaque.shape
    out, drawn = np.zeros((h, w, 3)), np.zeros((h, w), bool)
    if k == 0:
        y0, x0 = h // 2 - 3, w // 2 - 9
        drawn[y0:y0 + 6, x0:x0 + 18] = True
        out[drawn] = 0.0
        out[y0 + 1:y0 + 5, x0 + 1:x0 + 17] = colour("#c6c6c6")[:3]
        out[y0 + 1:y0 + 2, x0 + 1:x0 + 17] = 1.0
        return out, drawn
    sw, sh = min(w, 32) // 2 * 2, min(h, 42) // 2 * 2  # the shield, whole 2-pixel blocks
    x0, y0 = (w - sw) // 2, (h - sh) // 2
    ys, xs = np.mgrid[0:h, 0:w]
    u, v = (xs - x0) // 2, (ys - y0) // 2  # in blocks
    bw, bh = sw // 2, sh // 2
    point = np.maximum(0, v - (bh - 5)) * 1.2  # the shield narrows to a point at the bottom
    shape = (u >= 0) & (u < bw) & (v >= 0) & (v < bh) & (u >= point) & (u < bw - point)
    rim = shape & ~I._shrink(shape, 2)
    out[shape] = colour("#e8e8e2")[:3]
    out[shape & (u >= bw // 2)] = colour("#c8c8c2")[:3]  # its right half in shade
    out[rim] = colour("#7c7c7c")[:3]
    out[shape & ~I._shrink(shape, 1)] = colour("#2a2a2a")[:3]
    glyph = DIGITS[str(min(k, 4))]
    gy, gx = y0 + (sh - 7 * 3) // 2 - 2, x0 + (sw - 5 * 3) // 2
    for r, row in enumerate(glyph):
        for c, ch in enumerate(row):
            if ch == "#":
                out[gy + 3 * r:gy + 3 * r + 3, gx + 3 * c:gx + 3 * c + 3] = colour("#202020")[:3]
    return out, shape


def quantise(rgb: np.ndarray, palettes: list[np.ndarray]) -> np.ndarray:
    """Palette indices for RGB pixels (0..1), each the one that looks best in all the palettes the picture is
    shown in (the worst match over them is smallest). A wrong hue counts double a wrong lightness: a grey window
    stays grey in a palette of browns, a little lighter or darker rather than purple."""
    flat = np.clip(rgb.reshape(-1, 3) * 255 + 0.5, 0, 255).astype(np.int64)
    keys = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    uniq, inverse = np.unique(keys, return_inverse=True)
    hue = np.array([1.0, 2.0, 2.0])
    cols = _lab(np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64)) * hue
    worst = np.zeros((len(uniq), 256))
    for pal in palettes:
        lab = _lab(np.asarray(pal, np.float64)[:256]) * hue
        worst[:, :len(lab)] = np.maximum(worst[:, :len(lab)], ((cols[:, None] - lab[None]) ** 2).sum(-1))
        worst[:, len(lab):] = np.inf
    return worst.argmin(1)[inverse].reshape(rgb.shape[:2])


def intended(px: np.ndarray, opaque: np.ndarray, palettes: list[np.ndarray]) -> list[np.ndarray]:
    """The palettes to draw a picture in, the one it was made for first. A picture two screens show in very
    different palettes only looks right in one of them (in the other its colours are scrambled): the one where its
    neighbouring pixels are most alike. Palettes only a few colours apart from that one are kept too."""
    if len(palettes) < 2:
        return palettes
    both = opaque[:, 1:] & opaque[:, :-1]

    def roughness(pal: np.ndarray) -> float:
        rgb = np.asarray(pal, np.float64)[np.clip(px, 0, 255)][..., :3]
        return float(np.abs(rgb[:, 1:] - rgb[:, :-1]).sum(-1)[both].mean()) if both.any() else 0.0

    best = min(range(len(palettes)), key=lambda i: roughness(palettes[i]))
    ref = np.asarray(palettes[best], np.float64)[:256, :3]
    alike = [p for i, p in enumerate(palettes) if i != best and len(p) >= len(ref)
             and (np.abs(np.asarray(p, np.float64)[:256, :3] - ref).sum(1) > 10).sum() <= 32]
    return [palettes[best]] + alike


def redraw(sid: int, frame: slp.SlpFrame, palettes: list[np.ndarray], k: int = 0) -> slp.SlpFrame:
    """Picture k of a screen SLP redrawn, in the colours of the palette it was made for, and quantised for it and
    those like it."""
    px = frame.pixels
    opaque = (px >= 0) & (px < 256)
    palettes = intended(px, opaque, palettes)
    if sid in (FLAGS, TABS, TEAMS):
        rgb = np.asarray(palettes[0], np.float64)[np.clip(px, 0, 255)][..., :3] / 255
        new, drawn = (banner(rgb, opaque) if sid == FLAGS else tab(rgb, opaque) if sid == TABS
                      else team_mark(k, opaque))
        out = np.full(px.shape, slp.TRANSPARENT, np.int16)
        out[drawn] = quantise(new, palettes)[drawn]
        return slp.SlpFrame(out, frame.hotspot)
    rgb = np.asarray(palettes[0], np.float64)[np.clip(px, 0, 255)][..., :3] / 255
    new = loading(px.shape) if sid == LOADING else hall(rgb, opaque, sid)
    out = px.copy()
    out[opaque] = quantise(new, palettes)[opaque]
    return slp.SlpFrame(out.astype(np.int16), frame.hotspot)


def fits(sid: int, data: bytes) -> bool:
    """True if this is a picture this module redraws, at its known size."""
    try:
        sizes = slp.info(data).sizes
    except (ValueError, IndexError):
        return False
    if sid == FLAGS:  # eight pennants, about 150 by 45
        return len(sizes) == 8 and all(140 <= w <= 165 and 36 <= h <= 56 for w, h, _, _ in sizes)
    if sid == TABS:  # six tabs, each chosen and not, about 107 by 78
        return len(sizes) == 12 and all(95 <= w <= 120 and 70 <= h <= 86 for w, h, _, _ in sizes)
    if sid == TEAMS:  # no team, about 37 by 21, and four shields about 37 by 45
        return (len(sizes) == 5 and 25 <= sizes[0][0] <= 50 and 12 <= sizes[0][1] <= 30
                and all(28 <= w <= 48 and 36 <= h <= 56 for w, h, _, _ in sizes[1:]))
    return sid in RESTYLED and len(sizes) == 1 and sizes[0][:2] == RESTYLED[sid]


def encode(sid: int, original: bytes, palettes: list[np.ndarray]) -> bytes:
    frames = slp.decode(original)
    return slp.encode([redraw(sid, f, palettes, k) for k, f in enumerate(frames)], props=slp.frame_props(original))
