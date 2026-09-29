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
is solid dark oak. The loading screen is Minecraft's dark dirt with the block logo in grey stone. Each picture is drawn in every palette the
game shows it in (`quantise`), and only the pictures in RESTYLED, at those sizes, are changed.
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
RESTYLED = {  # picture -> its size: the screens this module redraws
    50100: (800, 600), 50101: (1024, 768), 50102: (1280, 1024), 50103: (800, 600), 50104: (800, 600),  # setup
    50270: (388, 258), 50190: (259, 138), 50202: (800, 600), 50204: (800, 600),  # their dialogues
    50212: (231, 150), 50221: (796, 534), 50222: (316, 326), 50223: (481, 518), 50224: (595, 548),  # in the game:
    50225: (716, 504), 50226: (594, 630), 53208: (603, 518),  # menu, diplomacy, objectives, chat
    50127: (273, 182), 50161: (800, 600), 50149: (800, 600), 50145: (800, 600), 50763: (268, 270),  # editor, history
    53161: (500, 408), 53162: (500, 408), 53163: (500, 408), 53164: (500, 408),  # the campaigns' dialogues
    53171: (500, 408), 53172: (500, 408), 53173: (500, 408), 53174: (500, 408),
    LOADING: (800, 600),
}
LAYOUTS = {  # sheets that are given, not found: (x0, y0, x1, y1) on the picture
    50104: {"insets": [(503, 50, 790, 495)]},  # the game settings' own sheet
    50161: {"sheets": [(0, 10, 251, 588), (262, 10, 792, 588)], "insets": [(8, 18, 238, 390)]},  # the history book
}
LUMA = I.LUMA
PAPER, DARK = 0.38, 0.45  # parchment is lighter than PAPER; a picture darker than DARK on average is all deepslate
STONE, WOOD = 0.3, 0.24  # how light the deepslate and the planks are
SOLID = I.GUI["slot"]  # a picture without parchment: every player colour can be read on it


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
    stone = rest & ~shadow & ~wood
    out[stone] = _tiled("deepslate_tiles", opaque.shape, STONE)[stone]
    out[wood] = _tiled("dark_oak_planks", opaque.shape, WOOD)[wood]
    lay = LAYOUTS.get(sid, {})
    whole = paper.all() or (opaque.all() and paper.mean() > 0.97)
    if whole:  # a texture the game fills a dialogue with: no window edges of its own
        out[paper] = colour(I.GUI["panel"])[:3]
        return out
    I._bevel(out, paper, I.GUI["panel"], I.GUI["light"], I.GUI["shade"], I.GUI["edge"])
    for x0, y0, x1, y1 in lay.get("insets", []):  # a sheet on the sheet: sunk in, like a slot
        m = np.zeros_like(paper)
        m[y0:y1, x0:x1] = True
        I._bevel(out, m & paper, "#b8b8b8", I.GUI["shade"], I.GUI["light"], None)
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


def quantise(rgb: np.ndarray, palettes: list[np.ndarray]) -> np.ndarray:
    """Palette indices for RGB pixels (0..1), each the one that looks best in all the palettes the picture is
    shown in (the worst match over them is smallest)."""
    flat = np.clip(rgb.reshape(-1, 3) * 255 + 0.5, 0, 255).astype(np.int64)
    keys = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    uniq, inverse = np.unique(keys, return_inverse=True)
    cols = _lab(np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.float64))
    worst = np.zeros((len(uniq), 256))
    for pal in palettes:
        lab = _lab(np.asarray(pal, np.float64)[:256])
        worst[:, :len(lab)] = np.maximum(worst[:, :len(lab)], ((cols[:, None] - lab[None]) ** 2).sum(-1))
        worst[:, len(lab):] = np.inf
    return worst.argmin(1)[inverse].reshape(rgb.shape[:2])


def redraw(sid: int, frame: slp.SlpFrame, palettes: list[np.ndarray]) -> slp.SlpFrame:
    """One screen picture redrawn, in the first of its palettes' colours and quantised for all of them."""
    px = frame.pixels
    opaque = (px >= 0) & (px < 256)
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
    return sid in RESTYLED and len(sizes) == 1 and sizes[0][:2] == RESTYLED[sid]


def encode(sid: int, original: bytes, palettes: list[np.ndarray]) -> bytes:
    frames = slp.decode(original)
    return slp.encode([redraw(sid, f, palettes) for f in frames], props=slp.frame_props(original))
