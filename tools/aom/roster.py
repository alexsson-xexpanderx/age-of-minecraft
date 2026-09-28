"""The full Age of Minecraft roster: every AoE2 Gold Edition unit, by group."""
from __future__ import annotations

from typing import Callable

from .animals import ANIMALS
from .easter import EASTER
from .mounted import MOUNTED
from .ships import SHIPS
from .siege import SIEGE
from .units import FOOT, Unit

ROSTER: dict[str, Callable[[], Unit]] = {**FOOT, **MOUNTED, **SIEGE, **SHIPS, **ANIMALS, **EASTER}

# Preview sheets: (file stem, title, filter)
SHEETS = [
    ("civilians", "Civilians", lambda u: u.group == "civilian"),
    ("infantry", "Infantry and archers", lambda u: u.group == "foot" and not u.civ),
    ("cavalry", "Cavalry", lambda u: u.group == "cavalry" and not u.civ),
    ("siege", "Siege and wagons", lambda u: u.group == "siege" and not u.civ),
    ("ships", "Ships", lambda u: u.group == "ship" and not u.civ),
    ("uniques", "Unique units", lambda u: u.civ is not None),
    ("animals", "Animals", lambda u: u.group == "animal"),
    ("easter", "Easter eggs (cheat units)", lambda u: u.group == "easter"),
]


def build_all() -> dict[str, Unit]:
    return {key: make() for key, make in ROSTER.items()}
