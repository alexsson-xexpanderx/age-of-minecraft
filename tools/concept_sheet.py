"""Render concept previews for Age of Minecraft.

    python tools/concept_sheet.py [output_dir]

Writes into previews/ by default:
    roster.png         every unit, all 8 directions, 2x zoom
    player_colors.png  one unit in all 8 player colours
    scene.png          in-game mock-up on AoE2-sized grass tiles, 2x zoom
    animations.gif     walk / attack / death cycles, 3x zoom
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aom.animation import DIRECTIONS, pose  # noqa: E402
from aom.colors import PLAYER_COLORS  # noqa: E402
from aom.render import SHADOW, Camera, Frame, render  # noqa: E402
from aom.units import ROSTER, Unit  # noqa: E402

TILE_W, TILE_H = 96, 48  # AoE2 tile size at 1x
GRASS = [(84, 128, 52), (92, 138, 56), (78, 120, 48), (98, 144, 62)]
INK, PAPER, MUTED = (32, 30, 28), (236, 232, 222), (110, 104, 96)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def grass(w: int, h: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pal = np.array(GRASS, np.uint8)
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


def frame_on_grass(frame: Frame, player: int, k: int, seed: int) -> np.ndarray:
    h, w = frame.kind.shape
    bg = grass(w, h, seed)
    blend(bg, frame.to_rgba(player), 0, 0)
    return zoom(bg, k)


# --------------------------------------------------------------------------- roster

def roster_sheet(units: list[Unit], out: Path, k: int = 2) -> None:
    cam = Camera(width=80, height=76, origin=(40, 66))
    cell_w, cell_h = cam.width * k, cam.height * k
    label_w, head_h, gap = 250, 64, 6
    W = label_w + len(DIRECTIONS) * (cell_w + gap)
    H = head_h + len(units) * (cell_h + gap) + 40
    sheet = np.full((H, W, 3), PAPER, np.uint8)

    for r, unit in enumerate(units):
        player = r % 8 + 1
        y = head_h + r * (cell_h + gap)
        for c, (_, heading) in enumerate(DIRECTIONS):
            f = render(unit.root, heading, pose(unit.rig, "idle", 0), cam)
            sheet[y:y + cell_h, label_w + c * (cell_w + gap):][:, :cell_w] = frame_on_grass(f, player, k, r * 8 + c)

    img = Image.fromarray(sheet)
    d = ImageDraw.Draw(img)
    d.text((16, 14), "Age of Minecraft - unit roster (idle, 2x zoom)", font=font(26), fill=INK)
    for c, (name, _) in enumerate(DIRECTIONS):
        x = label_w + c * (cell_w + gap) + cell_w // 2
        d.text((x, head_h - 8), name + ("*" if c >= 5 else ""), font=font(18), fill=INK, anchor="ms")
    for r, unit in enumerate(units):
        y = head_h + r * (cell_h + gap) + cell_h // 2
        d.text((16, y - 14), unit.name, font=font(20), fill=INK)
        d.text((16, y + 12), f"replaces {unit.replaces}", font=font(15), fill=MUTED)
        d.text((16, y + 32), f"player {r % 8 + 1}: {PLAYER_COLORS[r % 8 + 1][0].lower()}", font=font(13), fill=MUTED)
    d.text((16, H - 30), "* NE, E and SE are mirrored from NW, W and SW by the game, so only 5 directions "
                         "are stored per animation.", font=font(14), fill=MUTED)
    img.save(out)


# --------------------------------------------------------------------------- player colours

def player_sheet(unit: Unit, out: Path, k: int = 3) -> None:
    cam = Camera(width=64, height=72, origin=(32, 62))
    f = render(unit.root, -135, pose(unit.rig, "idle", 0), cam)
    cells = [frame_on_grass(f, p, k, p) for p in PLAYER_COLORS]
    strip = np.concatenate([np.pad(c, ((0, 0), (0, 4), (0, 0)), constant_values=236) for c in cells], 1)
    pad = np.full((40, strip.shape[1], 3), PAPER, np.uint8)
    img = Image.fromarray(np.concatenate([pad, strip], 0))
    d = ImageDraw.Draw(img)
    for i, (p, (name, _)) in enumerate(PLAYER_COLORS.items()):
        d.text((i * (cam.width * k + 4) + cam.width * k // 2, 28), f"{p} {name}", font=font(16),
               fill=INK, anchor="ms")
    img.save(out)


# --------------------------------------------------------------------------- in-game scene

def scene(out: Path, k: int = 2) -> None:
    """Two small armies on grass, drawn at the size they would have in game."""

    def tile_xy(i: float, j: float) -> tuple[int, int]:
        """Screen position of map tile (i, j); AoE2 tiles are 96x48 diamonds."""
        return int((i - j) * TILE_W / 2), int((i + j) * TILE_H / 2)

    # (unit, player, tile i, tile j, direction index, action, t)
    army = [
        ("villager", 1, 1.3, 2.0, 0, "idle", 0), ("villager", 1, 2.2, 1.4, 1, "walk", 0.25),
        ("sheep", 1, 1.0, 3.2, 1, "idle", 0), ("sheep", 1, 1.6, 3.8, 6, "idle", 0),
        ("militia", 1, 3.2, 3.0, 7, "idle", 0), ("man_at_arms", 1, 3.8, 3.6, 7, "walk", 0.5),
        ("long_swordsman", 1, 3.0, 4.2, 7, "idle", 0), ("champion", 1, 3.6, 4.8, 7, "attack", 0.5),
        ("skeleton_archer", 1, 2.2, 4.4, 7, "idle", 0), ("skeleton_archer", 1, 2.6, 5.2, 7, "idle", 0),
        ("two_handed", 2, 5.0, 4.2, 3, "attack", 0.3), ("champion", 2, 5.6, 5.4, 3, "idle", 0),
        ("militia", 2, 5.4, 3.3, 3, "walk", 0.0), ("skeleton_archer", 2, 6.6, 4.6, 3, "idle", 0),
        ("skeleton_archer", 2, 6.4, 3.6, 3, "idle", 0), ("creeper", 2, 4.5, 5.9, 2, "walk", 0.25),
        ("man_at_arms", 2, 4.6, 2.4, 3, "idle", 0), ("villager", 2, 6.6, 6.6, 4, "walk", 0.1),
        ("sheep", 2, 7.4, 6.8, 2, "idle", 0),
    ]
    units = {key: make() for key, make in ROSTER.items()}
    cam = Camera(width=96, height=96, origin=(48, 80))
    placed = []
    for key, player, i, j, dir_idx, action, t in army:
        u = units[key]
        f = render(u.root, DIRECTIONS[dir_idx][1], pose(u.rig, action, t), cam)
        cx, cy = tile_xy(i, j)
        placed.append((cy, f, player, cx - f.hotspot[0], cy - f.hotspot[1]))

    # Crop the canvas to the units' bounding box plus a margin.
    margin = 24
    x0 = min(x for *_, x, _ in placed) - margin
    y0 = min(y for *_, y in placed) - margin
    x1 = max(x + f.kind.shape[1] for _, f, _, x, _ in placed) + margin
    y1 = max(y + f.kind.shape[0] for _, f, _, _, y in placed) + margin
    canvas = grass(x1 - x0, y1 - y0, 3)
    for _, f, player, x, y in placed:  # shadows go under every unit
        shadow = np.zeros((*f.kind.shape, 4), np.uint8)
        shadow[f.kind == SHADOW] = (0, 0, 0, 102)
        blend(canvas, shadow, x - x0, y - y0)
    for _, f, player, x, y in sorted(placed, key=lambda p: p[0]):
        blend(canvas, f.to_rgba(player, shadow_alpha=0), x - x0, y - y0)
    Image.fromarray(zoom(canvas, k)).save(out)


# --------------------------------------------------------------------------- animations

def animations(out: Path, k: int = 3, frames: int = 12) -> None:
    cam = Camera(width=80, height=84, origin=(40, 72))
    cells = [("militia", "walk", 1, 1), ("man_at_arms", "attack", 1, 2), ("champion", "walk", 1, 5),
             ("skeleton_archer", "walk", 1, 3), ("villager", "walk", 1, 4), ("creeper", "walk", 1, 3),
             ("sheep", "walk", 1, 1), ("long_swordsman", "die", 1, 6)]
    units = {key: ROSTER[key]() for key, *_ in cells}
    label_h = 26
    images = []
    for n in range(frames):
        row = []
        for idx, (key, action, dir_idx, player) in enumerate(cells):
            u = units[key]
            t = n / frames if action != "die" else min(1.0, n / (frames - 3))
            f = render(u.root, DIRECTIONS[dir_idx][1], pose(u.rig, action, t), cam)
            cell = frame_on_grass(f, player, k, idx)
            label = np.full((label_h, cell.shape[1], 3), PAPER, np.uint8)
            row.append(np.pad(np.concatenate([label, cell], 0), ((0, 0), (0, 4), (0, 0)), constant_values=236))
        img = Image.fromarray(np.concatenate(row, 1))
        d = ImageDraw.Draw(img)
        for idx, (key, action, *_) in enumerate(cells):
            d.text((idx * (cam.width * k + 4) + cam.width * k // 2, 19), f"{units[key].name}: {action}",
                   font=font(14), fill=INK, anchor="ms")
        images.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=255))
    images[0].save(out, save_all=True, append_images=images[1:], duration=90, loop=0, disposal=2)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "previews"
    out.mkdir(parents=True, exist_ok=True)
    units = [make() for make in ROSTER.values()]
    roster_sheet(units, out / "roster.png")
    player_sheet(ROSTER["champion"](), out / "player_colors.png")
    scene(out / "scene.png")
    animations(out / "animations.gif")
    print(f"previews written to {out}")


if __name__ == "__main__":
    main()
