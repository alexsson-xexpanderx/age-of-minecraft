"""Render concept previews for Age of Minecraft.

    python tools/concept_sheet.py [output_dir]

Writes into previews/ by default:
    roster_<group>.png  every unit of a group in the 5 stored directions, 2x zoom
    anim_<group>.gif    walk / attack / death cycles for a sample of the group, 2x zoom
    player_colors.png   one unit in all 8 player colours
    scene.png           two armies, in-game size, 2x zoom
    battle.png          siege and cavalry assaulting a town, 2x zoom
    harbor.png          the fleet on the water, 2x zoom
    village.png         a Dark Age village with fields, a forest and mines, 2x zoom
    buildings.png       every building in the five village styles
    wonders.png         the eighteen wonders and the scenario monuments
    fortifications.png  walls, gates, towers and castles
    walls.png           wall lines in every direction, with corners, as the game places them
    sounds/*.wav        Pac-Man's sounds (clicking on him, orders, training, bites, death)
    nature.png          trees, resources and map decorations
    farms.png           farms, which are terrain: being built, grown and exhausted
    interface.png       the resource bar and bottom panel in the Minecraft style (on a stand-in panel)
    menu.png            the main menu, with the texts and Single Player buttons the game draws over it
    screens.png         the other screens as the deepslate hall, and the loading screen (on stand-in screens)
and docs/UNITS.md, the full unit list.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aom.animation import DIRECTIONS, pose  # noqa: E402
from aom import farmland, interface, menu, props  # noqa: E402
from aom.voxel import BUILDING_HEADING  # noqa: E402
from aom.colors import PLAYER_COLORS  # noqa: E402
from aom.geometry import Pose  # noqa: E402
from aom.render import SHADOW, Camera, Frame, fit_camera, render  # noqa: E402
from aom.roster import SHEETS, build_all  # noqa: E402
from aom.units import Unit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TILE_W, TILE_H = 96, 48  # AoE2 tile size at 1x
BASE_SCALE = 1.5  # screen pixels per Minecraft pixel
GRASS = [(84, 128, 52), (92, 138, 56), (78, 120, 48), (98, 144, 62)]
WATER = [(38, 86, 150), (44, 96, 162), (34, 78, 140), (52, 106, 170)]
INK, PAPER, MUTED = (32, 30, 28), (236, 232, 222), (110, 104, 96)
STORED = DIRECTIONS[:5]  # S, SW, W, NW, N; the game mirrors the rest


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def ground(w: int, h: int, seed: int = 7, water: bool = False) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pal = np.array(WATER if water else GRASS, np.uint8)
    return pal[rng.choice(len(pal), size=(h, w), p=[0.4, 0.25, 0.2, 0.15])]


def blend(canvas: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    """Alpha-blend `rgba` onto an RGB canvas with its top-left at (x, y), clipped."""
    h, w = rgba.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, canvas.shape[1]), min(y + h, canvas.shape[0])
    if x0 >= x1 or y0 >= y1:
        return
    src = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(float)
    a = src[..., 3:4] / 255
    dst = canvas[y0:y1, x0:x1].astype(float)
    canvas[y0:y1, x0:x1] = (src[..., :3] * a + dst * (1 - a) + 0.5).astype(np.uint8)


def zoom(img: np.ndarray, k: int) -> np.ndarray:
    return img.repeat(k, 0).repeat(k, 1)


def framed(frame: Frame, player: int, k: int, seed: int, water: bool = False) -> np.ndarray:
    h, w = frame.kind.shape
    bg = ground(w, h, seed, water)
    blend(bg, frame.to_rgba(player), 0, 0)
    return zoom(bg, k)


def shared_camera(jobs: list[tuple[Unit, float, Pose]], pad: int = 3) -> tuple[int, int, int, int]:
    """Canvas extents (left, right, up, down) around the hotspot that fit every (unit, heading, pose)."""
    left = right = up = down = 0
    for unit, heading, ps in jobs:
        cam = fit_camera(unit.root, heading, ps, scale=BASE_SCALE * unit.scale, pad=pad)
        left, up = max(left, cam.origin[0]), max(up, cam.origin[1])
        right, down = max(right, cam.width - cam.origin[0]), max(down, cam.height - cam.origin[1])
    return int(left), int(right), int(up), int(down)


def camera_for(unit: Unit, ext: tuple[int, int, int, int]) -> Camera:
    left, right, up, down = ext
    return Camera(width=left + right, height=up + down, origin=(left, up), scale=BASE_SCALE * unit.scale)


# --------------------------------------------------------------------------- roster sheets

def roster_sheet(title: str, units: list[Unit], out: Path, k: int = 2) -> None:
    ext = shared_camera([(u, h, pose(u, "idle", 0)) for u in units for _, h in STORED])
    cw, ch = (ext[0] + ext[1]) * k, (ext[2] + ext[3]) * k
    label_w, head_h, gap = 290, 70, 6
    W = label_w + len(STORED) * (cw + gap)
    H = head_h + len(units) * (ch + gap) + 40
    sheet = np.full((H, W, 3), PAPER, np.uint8)
    for r, unit in enumerate(units):
        cam = camera_for(unit, ext)
        y = head_h + r * (ch + gap)
        for c, (_, heading) in enumerate(STORED):
            f = render(unit.root, heading, pose(unit, "idle", 0), cam)
            x = label_w + c * (cw + gap)
            sheet[y:y + ch, x:x + cw] = framed(f, r % 8 + 1, k, r * 8 + c, water=unit.group == "ship")

    img = Image.fromarray(sheet)
    d = ImageDraw.Draw(img)
    d.text((16, 14), f"Age of Minecraft - {title} ({len(units)} units, idle, 2x zoom)", font=font(26), fill=INK)
    for c, (name, _) in enumerate(STORED):
        d.text((label_w + c * (cw + gap) + cw // 2, head_h - 10), name, font=font(18), fill=INK, anchor="ms")
    for r, unit in enumerate(units):
        y = head_h + r * (ch + gap) + ch // 2
        d.text((16, y - 22), unit.name, font=font(20), fill=INK)
        d.text((16, y + 4), f"replaces {unit.replaces}", font=font(15), fill=MUTED)
        if unit.civ:
            d.text((16, y + 24), f"unique unit: {unit.civ}", font=font(13), fill=MUTED)
    d.text((16, H - 30), "NE, E and SE are mirrored from NW, W and SW by the game, so these 5 directions are "
                         "all that is stored per animation.", font=font(14), fill=MUTED)
    img.save(out)


def player_sheet(unit: Unit, out: Path, k: int = 3) -> None:
    cam = Camera(width=64, height=72, origin=(32, 62))
    f = render(unit.root, -135, pose(unit, "idle", 0), cam)
    cells = [framed(f, p, k, p) for p in PLAYER_COLORS]
    strip = np.concatenate([np.pad(c, ((0, 0), (0, 4), (0, 0)), constant_values=236) for c in cells], 1)
    pad = np.full((40, strip.shape[1], 3), PAPER, np.uint8)
    img = Image.fromarray(np.concatenate([pad, strip], 0))
    d = ImageDraw.Draw(img)
    for i, (p, (name, _)) in enumerate(PLAYER_COLORS.items()):
        d.text((i * (cam.width * k + 4) + cam.width * k // 2, 28), f"{p} {name}", font=font(16),
               fill=INK, anchor="ms")
    img.save(out)


# --------------------------------------------------------------------------- animations

ANIMATIONS = {  # group -> [(unit, action, direction index)]
    "civilians": [("villager", "walk", 1), ("villager_lumberjack", "attack", 1), ("villager_gold_miner", "attack", 2),
                  ("villager_farmer", "attack", 1), ("villager_lumberjack", "carry", 1),
                  ("villager_fisherman", "attack", 2), ("monk", "attack", 1), ("king", "walk", 1)],
    "infantry": [("militia", "walk", 1), ("champion", "attack", 1), ("pikeman", "attack", 2),
                 ("archer", "attack", 2), ("crossbowman", "attack", 1), ("skirmisher", "attack", 1),
                 ("hand_cannoneer", "attack", 2), ("eagle_warrior", "walk", 1)],
    "cavalry": [("knight", "walk", 1), ("paladin", "attack", 1), ("cavalry_archer", "attack", 2),
                ("camel", "walk", 1), ("scout_cavalry", "die", 1)],
    "siege": [("battering_ram", "attack", 1), ("mangonel", "attack", 1), ("scorpion", "walk", 1),
              ("bombard_cannon", "attack", 2), ("trebuchet", "attack", 1), ("trebuchet", "walk", 1),
              ("war_wagon", "walk", 1), ("trade_cart", "walk", 2)],
    "ships": [("galley", "walk", 1), ("galleon", "attack", 2), ("fire_ship", "attack", 1),
              ("demolition_ship", "walk", 1), ("longboat", "walk", 2), ("turtle_ship", "attack", 1),
              ("fishing_ship", "idle", 1), ("cannon_galleon", "die", 2)],
    "uniques": [("longbowman", "attack", 2), ("woad_raider", "walk", 1), ("throwing_axeman", "attack", 1),
                ("samurai", "attack", 1), ("war_elephant", "attack", 1), ("janissary", "attack", 1),
                ("mangudai", "walk", 1), ("tarkan", "walk", 2)],
    "animals": [("sheep", "walk", 1), ("wolf", "attack", 1), ("wild_boar", "attack", 2), ("deer", "walk", 1),
                ("turkey", "walk", 1), ("jaguar", "attack", 1), ("hawk", "walk", 1), ("macaw", "walk", 2),
                ("marlin", "idle", 1), ("fish_tuna", "idle", 1), ("petard", "attack", 1)],
    "easter": [("pacman", "walk", 1), ("pacman", "attack", 2), ("pacman", "die", 1), ("ghost", "walk", 0),
               ("ghost", "walk", 1), ("cobra_car", "walk", 1)],
}


def _t(action: str, n: int, frames: int) -> float:
    return min(1.0, n / (frames - 3)) if action == "die" else n / frames


def animation_gif(cells, units: dict[str, Unit], out: Path, k: int = 2, frames: int = 12) -> None:
    exts = [shared_camera([(units[key], DIRECTIONS[d][1], pose(units[key], action, _t(action, n, frames)))
                           for n in range(0, frames, 2)], pad=5) for key, action, d in cells]
    height = max(e[2] + e[3] for e in exts) * k
    label_h = 26
    images = []
    for n in range(frames):
        row = []
        for idx, ((key, action, d), ext) in enumerate(zip(cells, exts)):
            u = units[key]
            f = render(u.root, DIRECTIONS[d][1], pose(u, action, _t(action, n, frames)), camera_for(u, ext))
            cell = framed(f, idx % 8 + 1, k, idx, water=u.group == "ship")
            cell = np.pad(cell, ((height - cell.shape[0], 0), (0, 0), (0, 0)), constant_values=236)
            label = np.full((label_h, max(cell.shape[1], 150), 3), PAPER, np.uint8)
            cell = np.pad(cell, ((0, 0), (0, label.shape[1] - cell.shape[1]), (0, 0)), constant_values=236)
            row.append(np.pad(np.concatenate([label, cell], 0), ((0, 0), (0, 4), (0, 0)), constant_values=236))
        img = Image.fromarray(np.concatenate(row, 1))
        dr = ImageDraw.Draw(img)
        x = 0
        for (key, action, _), cell in zip(cells, row):
            dr.text((x + cell.shape[1] // 2, 19), f"{units[key].replaces}: {action}", font=font(14), fill=INK,
                    anchor="ms")
            x += cell.shape[1]
        images.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    images[0].save(out, save_all=True, append_images=images[1:], duration=90, loop=0, disposal=2, optimize=True)


# --------------------------------------------------------------------------- scenes

def tile_xy(i: float, j: float) -> tuple[int, int]:
    """Screen position of map tile (i, j); AoE2 tiles are 96x48 diamonds."""
    return int((i - j) * TILE_W / 2), int((i + j) * TILE_H / 2)


def compose(placed: list[tuple[Frame, int, int, int]], out: Path, k: int = 2, margin: int = 24,
            shore: float = None, fields=()) -> tuple[int, int]:
    """Draw (frame, player, x, y) sprites with hotspots at map pixel (x, y), cropped to fit.

    With `shore`, map tiles whose i coordinate is at least `shore` are water. `fields` are farms, which the game
    draws as terrain: (stage, tile i, tile j) of each farm's centre. Returns the map pixel of the image's corner.
    """
    items = [(f, player, x - f.hotspot[0], y - f.hotspot[1], y) for f, player, x, y in placed]
    patches = []
    for stage, i, j in fields:
        patch = farmland.preview(stage)
        x, y = tile_xy(i, j)
        patches.append((patch, x - patch.shape[1] // 2, y - patch.shape[0] // 2))
    boxes = [(x, y, x + f.kind.shape[1], y + f.kind.shape[0]) for f, _, x, y, _ in items]
    boxes += [(x, y, x + p.shape[1], y + p.shape[0]) for p, x, y in patches]
    x0 = min(b[0] for b in boxes) - margin
    y0 = min(b[1] for b in boxes) - margin
    x1 = max(b[2] for b in boxes) + margin
    y1 = max(b[3] for b in boxes) + margin
    canvas = ground(x1 - x0, y1 - y0, 3)
    if shore is not None:
        yy, xx = np.mgrid[y0:y1, x0:x1]
        i = (xx / (TILE_W / 2) + yy / (TILE_H / 2)) / 2
        wet = i >= shore
        canvas[wet] = ground(x1 - x0, y1 - y0, 5, water=True)[wet]
    for patch, x, y in patches:
        blend(canvas, patch, x - x0, y - y0)
    for f, _, x, y, _ in items:  # shadows go under every sprite
        shadow = np.zeros((*f.kind.shape, 4), np.uint8)
        shadow[f.kind == SHADOW] = (0, 0, 0, 102)
        blend(canvas, shadow, x - x0, y - y0)
    for f, player, x, y, _ in sorted(items, key=lambda it: it[4]):  # back to front
        blend(canvas, f.to_rgba(player, shadow_alpha=0), x - x0, y - y0)
    Image.fromarray(zoom(canvas, k)).save(out)
    return x0, y0


def place_units(army, units: dict[str, Unit]) -> list[tuple[Frame, int, int, int]]:
    """army: (unit, player, tile i, tile j, direction index, action, t)."""
    placed = []
    for key, player, i, j, dir_idx, action, t in army:
        u = units[key]
        ps = pose(u, action, t)
        cam = fit_camera(u.root, DIRECTIONS[dir_idx][1], ps, scale=BASE_SCALE * u.scale)
        placed.append((render(u.root, DIRECTIONS[dir_idx][1], ps, cam), player, *tile_xy(i, j)))
    return placed


def building(spec: dict, variant: int = 0, t: float = 0.0) -> Frame:
    root = props.build(spec, variant=variant, count=3, t=t)
    return render(root, BUILDING_HEADING, camera=fit_camera(root, BUILDING_HEADING))


def place_buildings(spots, player: int = 1) -> list[tuple[Frame, int, int, int]]:
    """spots: (spec, tile i, tile j[, variant])."""
    placed = []
    for spot in spots:
        spec, i, j = spot[:3]
        placed.append((building(spec, spot[3] if len(spot) > 3 else 0), player, *tile_xy(i, j)))
    return placed


def B(code: str, style: str = "W", age: int = 2, **kw) -> dict:
    return {"model": "building", "code": code, "style": style, "age": age, **kw}


def structure_sheet(title: str, rows: list[tuple[str, list[tuple[str, dict]]]], out: Path, k: int = 1,
                    player: int = 1) -> None:
    """A labelled grid of buildings: one row per entry, each a list of (caption, spec)."""
    cells = [[(cap, framed(building(spec, spec.get("variant", 0)), player, 1, 3)) for cap, spec in items]
             for _, items in rows]
    head = 34
    col_w = max(img.shape[1] for row in cells for _, img in row) + 12
    row_h = [max(img.shape[0] for _, img in row) + 22 for row in cells]
    label_w = 150
    w = label_w + col_w * max(len(r) for r in cells)
    h = head + sum(row_h)
    canvas = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(canvas)
    d.text((10, 8), title, fill=INK, font=font(20))
    y = head
    for (label, _), row, rh in zip(rows, cells, row_h):
        d.text((10, y + rh // 2 - 8), label, fill=INK, font=font(14))
        for n, (cap, img) in enumerate(row):
            x = label_w + n * col_w
            canvas.paste(Image.fromarray(img), (x + (col_w - img.shape[1]) // 2, y + rh - img.shape[0] - 4))
            d.text((x + 4, y + 2), cap, fill=MUTED, font=font(11))
        y += rh
    if k > 1:
        canvas = canvas.resize((canvas.width * k, canvas.height * k), Image.NEAREST)
    # a 256-colour palette keeps these big sheets small; the pixel art survives it
    canvas.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)


STYLES = [("W", "West European"), ("E", "Central European"), ("M", "Middle Eastern"), ("F", "Asian"),
          ("X", "Meso-American")]


def buildings_sheet(out: Path) -> None:
    types = [("House", "HOUS", 3), ("Town Center", "RTWC", 3), ("Mill", "MILL", 3), ("Lumber camp", "SMIL", 2),
             ("Mining camp", "MINE", 2), ("Barracks", "BRKS", 3), ("Archery range", "ARRG", 3),
             ("Stable", "STBL", 3), ("Blacksmith", "BLAC", 3), ("Market", "MRKT", 3), ("Monastery", "CRCH", 3),
             ("University", "UNIV", 3), ("Siege workshop", "SIWS", 3), ("Dock", "DOCK", 3)]
    rows = [("Dark Age", [(name, B(code, "G", 1)) for name, code, _ in types
                          if code in ("HOUS", "RTWC", "MILL", "DOCK")])]
    rows.append(("Feudal (West)", [(name, B(code, "W", 2)) for name, code, _ in types[:8]]))
    for key, label in STYLES:
        rows.append((label, [(name, B(code, key, age)) for name, code, age in types]))
    rows.append(("Imperial", [(label, B("RTWC", key, 4)) for key, label in STYLES]
                 + [(f"University {key}", B("UNIV", key, 4)) for key, _ in STYLES[:3]]))
    structure_sheet("Buildings: one design per building, five village styles, materials upgrade with each age",
                    rows, out)


def wonders_sheet(out: Path) -> None:
    from aom.wonders import WONDERS
    names = {"B": "Britons", "R": "Franks", "H": "Goths", "U": "Teutons", "I": "Vikings", "L": "Celts",
             "Y": "Byzantines", "P": "Persians", "S": "Saracens", "T": "Turks", "J": "Japanese", "Z": "Chinese",
             "N": "Mongols", "K": "Koreans", "C": "Spanish", "G": "Huns", "A": "Aztecs", "M": "Mayans"}
    letters = list(WONDERS)
    rows = [("", [(names[k], {"model": "wonder", "letter": k}) for k in letters[i:i + 6]])
            for i in range(0, len(letters), 6)]
    rows.append(("Monuments", [(n.replace("_", " "), {"model": "monument", "name": n}) for n in
                               ("dome_of_the_rock", "small_pyramid", "large_pyramid", "cathedral_monument",
                                "mosque", "tower_of_flies")]))
    structure_sheet("Wonders and scenario monuments", rows, out)


def fortifications_sheet(out: Path) -> None:
    from aom.fortifications import PIECES
    rows = []
    for kind in ("palisade", "stone", "fortified"):
        rows.append((f"{kind.title()} wall", [(p, {"model": "wall", "kind": kind, "style": "W", "piece": p})
                                              for p in PIECES]))
    rows.append(("Gates", [(f"{st} {'open' if o else 'shut'}", {"model": "gate", "style": st, "age": 3,
                                                                 "direction": d, "open": o})
                           for st, d, o in (("W", "x", False), ("E", "y", True), ("M", "h", False),
                                            ("F", "v", True))]
                 + [(f"tower {st}", {"model": "gate_tower", "style": st, "age": 3}) for st in "WX"]))
    rows.append(("Towers", [(n, B("WCTW", "W", min(4, lv + 1), level=lv)) for lv, n in
                            ((1, "watch"), (2, "guard"), (3, "keep"), (4, "bombard"))]
                 + [("outpost", {"model": "outpost"})]))
    rows.append(("Castles", [(label, B("CSTL", key, 3)) for key, label in STYLES]))
    structure_sheet("Walls, gates, towers and castles", rows, out)


def wall_line(kind: str, style: str, tiles: list[tuple[float, float]]) -> list[tuple[dict, float, float]]:
    """Wall tiles along a path, with the piece the game picks for each: posts at the ends and corners."""
    from aom.fortifications import PIECES
    spots = []
    for k, (i, j) in enumerate(tiles):
        before = tiles[k - 1] if k else None
        after = tiles[k + 1] if k + 1 < len(tiles) else None
        if before is None or after is None or (i - before[0], j - before[1]) != (after[0] - i, after[1] - j):
            piece = "post"
        else:
            di, dj = after[0] - i, after[1] - j
            if di < 0 or (di == 0 and dj < 0):
                di, dj = -di, -dj
            # i runs along screen "\\" (the game's frame 1), j along "/" (frame 0); diagonals are frames 3 and 4
            piece = PIECES[{(1, 0): 1, (0, 1): 0, (1, -1): 3, (1, 1): 4}[(di, dj)]]
        spots.append(({"model": "wall", "kind": kind, "style": style, "piece": piece}, i, j))
    return spots


def walls_scene(out: Path) -> None:
    """Palisade, stone and fortified walls, one row each: "--", "\\" and "|" lines, then a corner."""
    spots = []
    for n, (kind, style) in enumerate((("palisade", "G"), ("stone", "E"), ("fortified", "W"))):
        o = 6 * n  # the next row, lower down the screen
        spots += wall_line(kind, style, [(o + k, o - k) for k in range(4)])
        spots += wall_line(kind, style, [(o + 4 + k, o - 6) for k in range(4)])
        spots += wall_line(kind, style, [(o + 6 + k, o - 10 + k) for k in range(4)])
        spots += wall_line(kind, style, [(o + 8, o - 13), (o + 8, o - 12), (o + 8, o - 11), (o + 9, o - 11),
                                         (o + 10, o - 11)])
    compose(place_buildings(spots), out, k=1)


def nature_sheet(out: Path) -> None:
    rows = [("Forests", [(f, {"model": "tree", "forest": f, "variant": v})
                         for f, v in (("oak", 0), ("oak", 4), ("forest", 1), ("pine", 0), ("snow", 2), ("palm", 1),
                                      ("jungle", 0), ("bamboo", 0))]),
            ("Resources", [("gold", {"model": "ore", "kind": "gold"}), ("gold", {"model": "ore", "kind": "gold",
                                                                                 "variant": 3}),
                           ("stone", {"model": "ore", "kind": "stone"}), ("berries", {"model": "berry_bush"}),
                           ("stump", {"model": "stump"}), ("fish trap", {"model": "fish_trap", "stage": 1.0})]),
            ("Decorations", [(n, {"model": "gaia", "name": n}) for n in
                             ("yurt", "pavilion", "ruins", "statue", "graves", "heads", "stone_head", "rug")]
             + [("cactus", {"model": "cactus", "variant": 2}), ("rocks", {"model": "rock", "variant": 1}),
                ("flowers", {"model": "plants", "flowers": True})])]
    structure_sheet("Trees, resources and decorations", rows, out)
    
    
def army_scene(out: Path, units: dict[str, Unit]) -> None:
    army = [
        ("villager", 1, 1.3, 2.0, 0, "idle", 0), ("villager_lumberjack", 1, 2.2, 1.4, 1, "carry", 0.25),
        ("sheep", 1, 1.0, 3.2, 1, "idle", 0), ("sheep", 1, 1.6, 3.8, 6, "idle", 0),
        ("militia", 1, 3.2, 3.0, 7, "idle", 0), ("man_at_arms", 1, 3.8, 3.6, 7, "walk", 0.5),
        ("pikeman", 1, 3.0, 4.2, 7, "idle", 0), ("champion", 1, 3.6, 4.8, 7, "attack", 0.5),
        ("archer", 1, 2.2, 4.4, 7, "idle", 0), ("crossbowman", 1, 2.6, 5.2, 7, "idle", 0),
        ("skirmisher", 1, 1.8, 5.6, 7, "idle", 0),
        ("two_handed", 2, 5.0, 4.2, 3, "attack", 0.3), ("halberdier", 2, 5.6, 5.4, 3, "idle", 0),
        ("militia", 2, 5.4, 3.3, 3, "walk", 0.0), ("arbalest", 2, 6.6, 4.6, 3, "idle", 0),
        ("hand_cannoneer", 2, 6.4, 3.6, 3, "idle", 0), ("petard", 2, 4.5, 5.9, 2, "walk", 0.25),
        ("eagle_warrior", 2, 4.6, 2.4, 3, "idle", 0), ("monk", 2, 6.9, 6.2, 3, "attack", 0.4),
    ]
    compose(place_units(army, units), out)


def battle_scene(out: Path, units: dict[str, Unit]) -> None:
    """Red siege and cavalry storming a blue castle town."""
    placed = place_buildings([(B("CSTL", "W", 3), 1.5, 1.5), (B("HOUS", "W", 3), -2.0, 5.0),
                              (B("WCTW", "W", 3, level=2), 5.0, -1.0)])
    for k in range(4):
        placed += place_buildings([({"model": "wall", "kind": "stone", "style": "W",
                                     "piece": "post" if k in (0, 3) else "x"}, 4.2, k - 0.3)])
    army = [
        ("knight", 1, 5.2, 5.0, 7, "attack", 0.5), ("paladin", 1, 4.4, 6.0, 7, "idle", 0),
        ("crossbowman", 1, 2.4, 5.6, 7, "attack", 0.5), ("hand_cannoneer", 1, 5.8, 3.2, 7, "idle", 0),
        ("skirmisher", 1, 1.6, 6.2, 7, "attack", 0.5), ("war_elephant", 1, 3.6, 6.8, 7, "idle", 0),
        ("battering_ram", 2, 6.2, 6.0, 3, "attack", 0.5), ("capped_ram", 2, 7.0, 4.6, 3, "walk", 0.3),
        ("trebuchet", 2, 10.4, 8.4, 3, "attack", 0.3), ("mangonel", 2, 8.4, 9.0, 3, "attack", 0.45),
        ("bombard_cannon", 2, 9.8, 6.2, 3, "idle", 0), ("scorpion", 2, 7.6, 7.8, 3, "idle", 0),
        ("cavalier", 2, 6.4, 7.6, 3, "walk", 0.2), ("cavalry_archer", 2, 7.6, 3.2, 3, "attack", 0.5),
        ("hussar", 2, 8.6, 5.2, 3, "walk", 0.6), ("camel", 2, 5.4, 8.6, 3, "walk", 0.1),
        ("war_wagon", 2, 9.2, 3.6, 3, "walk", 0.4), ("siege_onager", 2, 11.0, 6.6, 3, "idle", 0),
    ]
    compose(placed + place_units(army, units), out)


def harbor_scene(out: Path, units: dict[str, Unit]) -> None:
    """The fleet off the coast; tiles with i >= 3 are water."""
    placed = place_buildings([(B("DOCK", "W", 3), 3.5, 4.5), (B("HOUS", "W", 2), 0.5, 2.0),
                              (B("HOUS", "W", 2), 0.5, 7.0, 1)])
    placed += place_buildings([({"model": "fish_trap", "stage": 1.0}, 4.5, 9.5)], player=1)
    fleet = [
        ("villager_fisherman", 1, 2.0, 4.0, 7, "idle", 0), ("trade_cart", 1, 1.6, 8.2, 7, "idle", 0),
        ("fishing_ship", 1, 4.4, 2.2, 7, "idle", 0), ("fishing_ship", 1, 4.2, 7.6, 1, "idle", 0.5),
        ("transport_ship", 1, 5.0, 6.8, 3, "idle", 0.2), ("trade_cog", 1, 6.4, 1.2, 1, "walk", 0.3),
        ("galley", 1, 6.6, 6.4, 7, "walk", 0.1), ("war_galley", 1, 7.4, 3.4, 7, "attack", 0.5),
        ("galleon", 2, 10.4, 2.2, 3, "attack", 0.4), ("cannon_galleon", 2, 10.2, 6.2, 3, "attack", 0.5),
        ("fire_ship", 2, 8.8, 8.4, 3, "walk", 0.3), ("demolition_ship", 2, 9.2, 4.6, 2, "walk", 0.6),
        ("longboat", 2, 12.4, 4.4, 3, "walk", 0.2), ("turtle_ship", 2, 12.4, 8.6, 3, "idle", 0),
        ("marlin", 7, 11.0, 10.4, 1, "idle", 0.7), ("fish_tuna", 7, 7.4, 10.2, 1, "idle", 0.2),
    ]
    compose(placed + place_units(fleet, units), out, shore=3.0)


def village_scene(out: Path, units: dict[str, Unit]) -> None:
    """A Dark Age start: Town Center, houses, a mill with fields, a lumber camp at the forest, mines."""
    placed = place_buildings([(B("RTWC", "G", 1), 4.0, 4.0), (B("HOUS", "G", 1), -0.5, 6.0),
                              (B("HOUS", "G", 1), 3.0, -0.5, 1), (B("HOUS", "G", 1), 8.5, 1.0, 2),
                              (B("MILL", "W", 2), 9.0, 7.5), (B("SMIL", "W", 2), -1.5, 10.5),
                              (B("MINE", "W", 2), 4.0, 11.0)])
    for k, (i, j) in enumerate(((-3.5, 12.5), (-2.5, 13.5), (-3.5, 14.5), (-4.5, 13.5), (-1.5, 14.5), (-4.5, 11.5),
                                (-2.5, 15.5), (-5.5, 14.5))):
        placed += place_buildings([({"model": "tree", "forest": "oak", "height": 110 + 12 * (k % 3)}, i, j, k)], 7)
    placed += place_buildings([({"model": "ore", "kind": "gold"}, 5.0, 13.5, 1), ({"model": "ore", "kind": "gold"},
                                                                                6.0, 13.5, 3),
                               ({"model": "ore", "kind": "stone"}, 2.0, 13.5, 2),
                               ({"model": "berry_bush"}, 12.5, 2.0, 0), ({"model": "berry_bush"}, 13.5, 2.0, 1),
                               ({"model": "berry_bush"}, 13.0, 3.0, 2)], 7)
    folk = [
        ("villager_builder", 1, 6.9, 5.2, 7, "attack", 0.3), ("villager_farmer", 1, 9.4, 10.0, 1, "attack", 0.6),
        ("villager_lumberjack", 1, -2.4, 12.0, 3, "attack", 0.6), ("villager", 1, 1.6, 1.4, 0, "idle", 0),
        ("villager_shepherd", 1, 7.0, 6.6, 1, "attack", 0.2), ("villager_forager", 1, 12.0, 2.8, 2, "attack", 0.3),
        ("sheep", 1, 7.2, 7.3, 1, "idle", 0), ("sheep", 1, 7.9, 6.9, 6, "walk", 0.4),
        ("villager_gold_miner", 1, 5.4, 12.6, 0, "attack", 0.3), ("scout_cavalry", 1, 4.6, 7.8, 0, "idle", 0),
        ("deer", 7, 12.4, 12.6, 2, "idle", 0), ("wolf", 7, 13.6, 10.2, 2, "walk", 0.5),
        ("hawk", 7, 6.0, 1.0, 1, "walk", 0.25),
    ]
    compose(placed + place_units(folk, units), out, fields=[("ripe", 9.0, 10.5), ("growing", 12.0, 7.5)])


def farms_sheet(out: Path, units: dict[str, Unit]) -> None:
    """The farm's stages side by side, as 3x3 tile fields on the grass, with a farmer on the grown one."""
    fields = [(stage, 3.5 * n, -3.5 * n) for n, stage in enumerate(farmland.STAGES)]
    folk = [("villager_farmer", 1, 10.8, -10.2, 1, "attack", 0.6)]
    tmp = out.with_suffix(".tmp.png")
    x0, _ = compose(place_units(folk, units), tmp, k=1, margin=12, fields=fields)
    img = Image.open(tmp)
    tmp.unlink()
    head, foot = 34, 24
    canvas = Image.new("RGB", (img.width, img.height + head + foot), PAPER)
    canvas.paste(img, (0, head))
    d = ImageDraw.Draw(canvas)
    d.text((10, 8), "Farms are terrain: built in three stages, then grown, then exhausted", fill=INK, font=font(20))
    for stage, i, j in fields:
        caption = farmland.STAGES[stage]
        x = tile_xy(i, j)[0] - x0 - d.textlength(caption, font=font(12)) / 2
        d.text((x, head + img.height + 4), caption, fill=MUTED, font=font(12))
    canvas = canvas.resize((canvas.width * 2, canvas.height * 2), Image.NEAREST)
    canvas.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)


def stand_in_panel(w: int = 1280, h: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    """A panel picture shaped like the game's (its own is not in this repository): RGB 0..1 and where it is drawn.

    A carved top bar with five resource icons, and a bottom panel with the command area, the parchment and the
    dark area behind the minimap."""
    rng = np.random.default_rng(0)

    def carved(rows: int, cols: int, base) -> np.ndarray:
        grain = 0.06 * np.sin(np.arange(cols) / 3.0)[None, :, None]
        return np.clip(np.array(base) + rng.normal(0, 0.05, (rows, cols, 1)) + grain, 0, 1)

    rgb, drawn = np.zeros((h, w, 3)), np.zeros((h, w), bool)
    top = h - 218
    rgb[:32], drawn[:32] = carved(32, w, (0.36, 0.24, 0.14)), True
    icons = [interface.FIRST + interface.STEP * k for k in range(5)]  # laid out as in the game's own
    for x, col in zip(icons, ((0.5, 0.3, 0.1), (0.8, 0.2, 0.2), (0.9, 0.75, 0.2), (0.6, 0.6, 0.6), (0.3, 0.4, 0.8))):
        rgb[10:27, x + 22:x + 69] = (0.03, 0.03, 0.03)  # the dark box the game writes the amount in
        rgb[13:24, x + 6:x + 20] = col
    rgb[top:], drawn[top:] = carved(h - top, w, (0.42, 0.28, 0.16)), True
    rgb[top:top + 12] = carved(12, w, (0.55, 0.38, 0.2))
    rgb[top + 24:h - 14, 15:330] = carved(h - 14 - top - 24, 315, (0.3, 0.2, 0.12))
    rgb[top + 16:h - 8, 344:846] = (0.66, 0.55, 0.40)  # the parchment's shaded border, where the name is written
    rgb[top + 24:h - 14, 350:840] = np.clip(np.array((0.86, 0.78, 0.6)) + rng.normal(0, 0.03, (180, 490, 1)), 0, 1)
    for x in range(420, 800, 130):
        rgb[top + 16:top + 34, x:x + 14] = carved(18, 14, (0.3, 0.2, 0.12))  # tears in its top edge
    rgb[top + 19:top + 25, 360:420] = (0.05, 0.05, 0.05)  # the unit's name, as the game writes it
    rgb[top + 24:h - 14, 880:w - 20] = (0.05, 0.05, 0.06)
    return rgb, drawn


def interface_sheet(out: Path) -> None:
    """The resource bar and the bottom panel, before and after, on a stand-in for the game's own panel."""
    rgb, drawn = stand_in_panel()
    after = interface.restyle(rgb, drawn)
    top = rgb.shape[0] - 218

    def strip(img: np.ndarray) -> np.ndarray:
        view = (img * 255 + 0.5).astype(np.uint8)
        view[~drawn] = GRASS[0]
        return np.concatenate([view[:32], view[:24] * 0 + np.array(GRASS[0], np.uint8), view[top:]])

    head, gap = 34, 22
    before_img, after_img = strip(rgb), strip(after)
    for img in (before_img, after_img):  # the amounts, as the game writes them: white with a black shadow
        pic = Image.fromarray(img)
        d = ImageDraw.Draw(pic)
        for k, amount in enumerate(("39900", "40000", "20000", "10000", "4/1000")):  # where the game writes them:
            end = interface.FIRST + interface.STEP * k + 66  # right-aligned, 66 pixels after the icon's left edge
            x = end - d.textlength(amount, font=font(12))
            d.text((x, 12), amount, fill=(255, 255, 255), font=font(12), stroke_width=1, stroke_fill=(0, 0, 0))
        img[...] = np.asarray(pic)
    canvas = Image.new("RGB", (before_img.shape[1], head + 2 * (before_img.shape[0] + gap)), PAPER)
    d = ImageDraw.Draw(canvas)
    d.text((10, 8), "The panels, Minecraft style: planks, inventory grey, slots and item icons", fill=INK,
           font=font(20))
    y = head
    for label, img in (("a stand-in for the game's own panel (the build repaints yours)", before_img),
                       ("after", after_img)):
        d.text((10, y + 3), label, fill=MUTED, font=font(13))
        canvas.paste(Image.fromarray(img), (0, y + gap))
        y += gap + img.shape[0]
    canvas.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)


def menu_sheet(out: Path) -> None:
    """The Minecraft main menu at its size, with what the game draws over it (where a screenshot of the game shows
    it): the button names in white on their buttons, and the Single Player menu open on the right, its buttons the
    game's own in the colours the build gives them."""
    img, _ = menu.scene()
    canvas = Image.fromarray((img * 255 + 0.5).astype(np.uint8))
    d = ImageDraw.Draw(canvas)

    def say(xy, text, size, colour=(255, 255, 255)):
        w = d.textlength(text, font=font(size))
        d.text((xy[0] - w / 2 + 1, xy[1] - size / 2 - 1), text, fill=(0, 0, 0), font=font(size))
        d.text((xy[0] - w / 2, xy[1] - size / 2 - 2), text, fill=colour, font=font(size))

    for text, xy in (("Learn to Play", (61, 20)), ("Single Player", (368, 25)), ("History", (154, 177)),
                     ("Multiplayer", (311, 229)), ("Map Editor", (228, 284)), ("Options", (147, 359)),
                     ("Zone", (303, 377)), ("Exit", (82, 577))):
        say(xy, text, 13)
    say((614, 22), "Single Player", 18)
    fill = tuple(int(v * 255) for v in texture_colour(menu.SCREEN["background_color"]))
    light, shade = texture_colour(menu.BUTTON["light"]), texture_colour(menu.BUTTON["shade"])
    for k, (label, (x0, y0, x1, y1)) in enumerate(zip(("The Conquerors Campaigns", "Standard Game",
                                                        "Age of Kings Campaigns", "Custom Campaign", "Watching Player",
                                                        "Saved and Recorded Games"), menu.SUBMENU)):
        d.rectangle((x0, y0, x1, y1), fill=fill, outline=(0, 0, 0))
        d.line((x0 + 1, y0 + 1, x1 - 1, y0 + 1), fill=tuple(int(v * 255) for v in light))
        d.line((x0 + 1, y1 - 1, x1 - 1, y1 - 1), fill=tuple(int(v * 255) for v in shade))
        say(((x0 + x1) / 2, (y0 + y1) / 2), label, 16, (255, 255, 160) if k == 1 else (255, 255, 255))
    d.text((396, 505), "Play with or against computer players, or play one of nine\nhistorical campaigns.",
           fill=(255, 255, 255), font=font(12))
    canvas.save(out, optimize=True)


def texture_colour(colour: str) -> tuple[float, float, float]:
    from aom.textures import parse
    return tuple(float(v) for v in parse(colour)[:3])


def stand_in_screen(w: int, h: int, dialogue: bool) -> tuple[np.ndarray, np.ndarray]:
    """A screen picture shaped like the game's (its own are not in this repository): RGB 0..1 and where it is
    drawn. A parchment with torn edges and an ornament, in a dark frame; a dialogue has a wooden plaque for its
    title and a drop shadow, a setup screen a wooden crate for its buttons."""
    rng = np.random.default_rng(3)
    rgb = np.clip(np.array((0.24, 0.19, 0.13)) + rng.normal(0, 0.04, (h, w, 1)), 0, 1)
    drawn = np.ones((h, w), bool)
    x0, y0, x1, y1 = 14, 14, w - 14, h - 14
    if dialogue:
        shadow = np.zeros((h, w), bool)
        shadow[h - 12:, 12:] = shadow[12:, w - 12:] = True
        rgb[shadow] = 0.02  # the drop shadow: every other pixel
        drawn[shadow] = (np.indices((h, w)).sum(0) % 2 == 0)[shadow]
        x1, y1 = w - 22, h - 22
    paper = np.clip(np.array((0.86, 0.72, 0.5)) + rng.normal(0, 0.03, (y1 - y0, x1 - x0, 1)), 0, 1)
    rgb[y0:y1, x0:x1] = paper
    for x in range(x0 + 20, x1 - 20, 55):  # tears in its edges
        rgb[y0:y0 + int(rng.integers(4, 12)), x:x + int(rng.integers(8, 20))] = (0.24, 0.19, 0.13)
        rgb[y1 - int(rng.integers(4, 12)):y1, x + 20:x + 34] = (0.24, 0.19, 0.13)
    rgb[y0 + 26:y0 + 70, x0 + 20:x0 + 50] = (0.4, 0.15, 0.1)  # an ornament
    if dialogue:
        rgb[y0:y0 + 40, w // 2 - 110:w // 2 + 110] = (0.52, 0.28, 0.05)  # the plaque
    else:
        rgb[h - 130:h - 14, w // 2:w - 14] = (0.36, 0.23, 0.1)  # the crate
    return rgb, drawn


def screens_sheet(out: Path) -> None:
    """The deepslate hall on stand-ins for the game's screens, before and after, and the loading screen."""
    from aom import screens
    pics = [stand_in_screen(800, 600, False), stand_in_screen(560, 400, True)]
    head, gap, pad = 34, 22, 14

    def view(img: np.ndarray, drawn: np.ndarray) -> Image.Image:
        v = (img * 255 + 0.5).astype(np.uint8)
        v[~drawn] = GRASS[0]
        return Image.fromarray(v)

    rows = [[view(rgb, drawn), view(screens.hall(rgb, drawn), drawn)] for rgb, drawn in pics]
    from aom import loadscreen
    rows.append([view(loadscreen.picture(), np.ones((loadscreen.H, loadscreen.W), bool))])
    width = max(sum(im.width for im in r) + pad * (len(r) - 1) for r in rows)
    canvas = Image.new("RGB", (width, head + sum(gap + r[0].height for r in rows)), PAPER)
    d = ImageDraw.Draw(canvas)
    d.text((10, 8), "The other screens, as the deepslate hall (the build redraws your own)", fill=INK, font=font(20))
    y = head
    for label, r in zip(("a setup screen: a stand-in, and after", "a dialogue: a stand-in, and after",
                         "the loading screen"), rows):
        d.text((10, y + 3), label, fill=MUTED, font=font(13))
        x = 0
        for im in r:
            canvas.paste(im, (x, y + gap))
            x += im.width + pad
        y += gap + r[0].height
    canvas.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)


# --------------------------------------------------------------------------- unit list

def unit_table(units: dict[str, Unit], out: Path) -> None:
    lines = ["# Age of Minecraft: unit list", "",
             "Generated by `tools/concept_sheet.py`. Every unit in AoE2: Gold Edition (The Age of Kings and",
             "The Conquerors) and its Minecraft-style replacement. Previews: `previews/roster_<group>.png`.", ""]
    total = 0
    for stem, title, keep in SHEETS:
        group = [u for u in units.values() if keep(u)]
        total += len(group)
        lines += [f"## {title} ({len(group)})", "", "| AoE2 unit | Minecraft figure | Civilisation |", "|---|---|---|"]
        lines += [f"| {u.replaces} | {u.name} | {u.civ or ''} |" for u in group]
        lines += [""]
    lines.insert(5, f"**{total} units.** Villager jobs share one model per job for both genders.\n")
    out.write_text("\n".join(lines))


def pacman_sounds(out: Path) -> None:
    from aom import sounds
    out.mkdir(parents=True, exist_ok=True)
    for name, variants in sounds.pacman_sounds().items():
        for k, x in enumerate(variants):
            (out / f"pacman_{name}{k + 1 if len(variants) > 1 else ''}.wav").write_bytes(sounds.wav(x))


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "previews"
    out.mkdir(parents=True, exist_ok=True)
    units = build_all()
    for stem, title, keep in SHEETS:
        roster_sheet(title, [u for u in units.values() if keep(u)], out / f"roster_{stem}.png")
        animation_gif(ANIMATIONS[stem], units, out / f"anim_{stem}.gif")
    player_sheet(units["champion"], out / "player_colors.png")
    army_scene(out / "scene.png", units)
    battle_scene(out / "battle.png", units)
    harbor_scene(out / "harbor.png", units)
    village_scene(out / "village.png", units)
    buildings_sheet(out / "buildings.png")
    wonders_sheet(out / "wonders.png")
    fortifications_sheet(out / "fortifications.png")
    walls_scene(out / "walls.png")
    pacman_sounds(out / "sounds")
    nature_sheet(out / "nature.png")
    farms_sheet(out / "farms.png", units)
    interface_sheet(out / "interface.png")
    menu_sheet(out / "menu.png")
    screens_sheet(out / "screens.png")
    unit_table(units, ROOT / "docs" / "UNITS.md")
    print(f"previews written to {out}")


if __name__ == "__main__":
    main()
