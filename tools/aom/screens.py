"""The game's other screens (game setup, options, scenario editor, history, loading, dialogues): where they are.

Each screen is described by a small text file in interfac.drs (a "bina" entry, 50001-50099 in the Conquerors)
with one setting per line: its background pictures for 800x600, 1024x768 and 1280x1024 ("background1_files" to
"background3_files"), its palette ("palette_file"), and the colours the game draws its buttons and text in
("bevel_colors", "text_color1", ...). `read()` finds every one of them. The loading screen and a few others are
pictures no screen file names, so `pictures()` also takes every other large picture in interfac.drs.

The build saves all of them as PNG files (screen_originals/) so the Minecraft versions can be drawn to fit their
layout, and lists the screen files in the report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import slp

KEYS = ("background1_files", "background2_files", "background3_files", "palette_file", "button_file",
        "popup_dialog_sin", "bevel_colors", "text_color1")
MAIN_PALETTE = 50500
INTERFACE = range(50000, 60000)  # the ids of interfac.drs's files (the sprites' ids are lower)
PANELS = range(51101, 51161)  # the in-game panels: interface.py
MIN_SIZE = (250, 130)  # smaller pictures are buttons and icons, not screens


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
        if any(w >= MIN_SIZE[0] and h >= MIN_SIZE[1] for w, h, _, _ in sizes):
            out[sid] = MAIN_PALETTE
    return out
