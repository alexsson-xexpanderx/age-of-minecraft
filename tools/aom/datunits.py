"""Read and patch the civilisations' unit tables in empires2_x1_p1.dat (The Conquerors, "VER 5.7").

Only what the mod needs: find every civilisation's copy of a unit, read its
basic fields, and change a few fixed-size fields in place (enabled, icon,
cost, training time, training building, button). Patching in place keeps the
rest of the file byte-for-byte identical. The layout follows genieutils /
openage (unit types 10 to 80, Age of Kings and later).

The civilisations are located by their headers (count, name, resources,
unit pointer table), and every civ's units are parsed completely: they must
end exactly where the next civilisation begins, which verifies the layout.

The units' task lists (what a unit can do: attack, garrison, gather...) are
shared by all civilisations and stored just before them, one "unit header"
per unit id; they are found by parsing back from the civilisations.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional



class DatLayoutError(ValueError):
    pass


class _R:
    def __init__(self, data: bytes, pos: int):
        self.d, self.p = data, pos

    def take(self, fmt: str):
        v = struct.unpack_from("<" + fmt, self.d, self.p)
        self.p += struct.calcsize("<" + fmt)
        return v

    def one(self, fmt: str):
        return self.take(fmt)[0]

    def skip(self, n: int) -> None:
        self.p += n


@dataclass
class UnitRecord:
    civ: int
    id: int
    type: int
    name: str
    offset: int  # start of the record in the decompressed data
    end: int = 0  # end of the record
    fields: dict[str, int] = field(default_factory=dict)  # name -> byte offset of the field
    values: dict[str, object] = field(default_factory=dict)


# field name -> struct format, for the fields we may patch
FORMATS = {"enabled": "b", "icon": "h", "hide_in_editor": "b", "train_time": "h", "train_location": "h",
           "button": "b", "cost": "hhhhhhhhh", "creatable_type": "b", "hotkey": "i", "name_id": "H",
           "creation_id": "H", "help_id": "i", "hotkey_text_id": "i", "standing": "hh", "hit_points": "h",
           "dying": "hh", "walking": "hh", "attack_graphic": "h", "dead_unit": "h", "class": "h",
           "terrain_restriction": "h", "speed": "f",
           "train_sound": "h", "selection_sound": "h", "dying_sound": "h", "attack_sound": "h", "move_sound": "h"}


def _unit(r: _R, civ: int) -> UnitRecord:
    start = r.p
    f: dict[str, int] = {}
    v: dict[str, object] = {}
    utype = r.one("b")
    name_len = r.one("H")
    uid = r.one("h")
    f["name_id"] = r.p
    v["name_id"] = r.one("H")
    f["creation_id"] = r.p
    v["creation_id"] = r.one("H")
    f["class"] = r.p
    v["class"] = r.one("h")
    f["standing"] = r.p
    v["standing"] = r.take("hh")
    f["dying"] = r.p
    v["dying"] = r.take("hh")
    r.one("b")  # undead mode
    f["hit_points"] = r.p
    v["hit_points"] = r.one("h")
    r.one("f")  # line of sight
    r.one("b")  # garrison capacity
    r.take("fff")  # collision size
    f["train_sound"] = r.p
    v["train_sound"] = r.one("h")
    r.one("h")  # damage sound
    f["dead_unit"] = r.p
    v["dead_unit"] = r.one("h")
    r.take("bb")  # sort number, can be built on
    f["icon"] = r.p
    v["icon"] = r.one("h")
    f["hide_in_editor"] = r.p
    r.one("b")
    r.one("h")  # old portrait
    f["enabled"] = r.p
    v["enabled"] = r.one("b")
    r.one("b")  # disabled
    r.take("hhhh")  # placement side terrain, placement terrain
    r.take("ff")  # clearance size
    r.take("bb")  # hill mode, fog visibility
    f["terrain_restriction"] = r.p
    v["terrain_restriction"] = r.one("h")  # which terrains the unit may stand on (a row of the restriction table)
    r.one("b")  # fly mode
    r.one("h")  # resource capacity
    r.one("f")  # resource decay
    r.take("bbbbb")  # blast defence, combat level, interaction mode, minimap mode, interface kind
    r.one("f")  # multiple attribute mode
    r.one("b")  # minimap colour
    f["help_id"] = r.p
    v["help_id"] = r.one("i")
    f["hotkey_text_id"] = r.p
    r.one("i")
    f["hotkey"] = r.p
    r.one("i")
    r.take("bbbb")  # recyclable, auto gather, doppelganger on death, resource gather group
    r.take("bbb")  # occlusion mode, obstruction type, obstruction class
    r.take("Bbh")  # trait, civilisation, nothing
    r.take("bB")  # selection effect, editor selection colour
    r.take("fff")  # outline size
    r.skip(3 * 7)  # resource storages: (int16 type, float amount, int8 flag) x 3
    n_damage = r.one("B")
    r.skip(n_damage * 5)
    f["selection_sound"] = r.p
    v["selection_sound"] = r.one("h")
    f["dying_sound"] = r.p
    v["dying_sound"] = r.one("h")
    r.take("bb")  # old attack reaction, convert terrain
    f["name"] = r.p
    raw_name = r.d[r.p:r.p + name_len]
    r.skip(name_len)
    r.take("hh")  # copy id, base id
    if utype >= 20:  # flags and up: speed
        f["speed"] = r.p
        v["speed"] = r.one("f")  # tiles per second
    if utype >= 30:  # dead units / fish: movement
        f["walking"] = r.p
        v["walking"] = r.take("hh")
        r.one("f")  # rotation speed
        r.one("b")  # old size class
        r.one("h")  # tracking unit
        r.one("b")  # tracking unit mode
        r.one("f")  # tracking unit density
        r.one("b")  # old move algorithm
        r.take("fffff")  # turn radius, turn speed, yaw rates
    if utype >= 40:  # birds and up: tasks and gathering
        r.one("h")  # default task
        r.take("ff")  # search radius, work rate
        r.take("hh")  # drop sites
        r.one("b")  # task swap group
        f["attack_sound"] = r.p
        v["attack_sound"] = r.one("h")
        f["move_sound"] = r.p
        v["move_sound"] = r.one("h")
        r.one("b")  # run pattern
    if utype >= 50:  # combat
        r.one("h")  # base armour
        n = r.one("H")
        r.skip(n * 4)  # attacks
        n = r.one("H")
        r.skip(n * 4)  # armours
        r.one("h")  # defence terrain bonus
        r.take("fff")  # max range, blast width, reload time
        r.take("hh")  # projectile unit, accuracy
        r.one("b")  # break off combat
        r.one("h")  # frame delay
        r.take("fff")  # graphic displacement
        r.one("b")  # blast attack level
        r.one("f")  # min range
        r.one("f")  # accuracy dispersion
        f["attack_graphic"] = r.p
        v["attack_graphic"] = r.one("h")
        r.take("hh")  # displayed melee armour, displayed attack
        r.take("ff")  # displayed range, displayed reload time
    if utype == 60:  # projectiles
        r.take("bbbbb")
        r.one("f")
    if utype >= 70:  # creatable: cost, training
        f["cost"] = r.p
        v["cost"] = r.take("hhhhhhhhh")
        f["train_time"] = r.p
        v["train_time"] = r.one("h")
        f["train_location"] = r.p
        v["train_location"] = r.one("h")
        f["button"] = r.p
        v["button"] = r.one("b")
        r.take("ff")  # rear and flank attack modifiers
        f["creatable_type"] = r.p
        v["creatable_type"] = r.one("b")
        r.one("b")  # hero mode
        r.one("i")  # garrison graphic
        r.one("f")  # total projectiles
        r.one("b")  # max total projectiles
        r.take("fff")  # projectile spawning area
        r.take("ii")  # secondary projectile, special graphic
        r.one("b")  # special ability
        r.one("h")  # displayed pierce armour
    if utype == 80:  # buildings
        r.take("hh")  # construction graphic, snow graphic
        r.one("b")  # adjacent mode
        r.one("h")  # graphics angle
        r.one("b")  # disappears when built
        r.take("hhhh")  # stack unit, foundation terrain, old overlay, tech
        r.one("b")  # can burn
        r.skip(4 * 10)  # annexes
        r.take("hhh")  # head unit, transform unit, transform sound
        r.one("h")  # construction sound
        r.one("b")  # garrison type
        r.take("ff")  # garrison heal / repair rates
        r.one("h")  # pile unit
        r.skip(6)  # looting table
    name = raw_name.split(b"\0", 1)[0].decode("latin-1")
    if utype not in (10, 15, 20, 25, 30, 40, 50, 60, 70, 80) or not all(32 <= ord(c) < 127 for c in name):
        raise DatLayoutError(f"unexpected unit record at {start}: type {utype}, name {raw_name!r}")
    return UnitRecord(civ, uid, utype, name, start, r.p, f, v)


def _civ_header(data: bytes, h: int) -> Optional[tuple[int, int, int]]:
    """(resource count, unit count, pointer table offset) if a civilisation header looks to start at h."""
    if h + 30 > len(data) or data[h] > 5:
        return None
    name = data[h + 1:h + 21].split(b"\0", 1)[0]
    if not name or not all(32 <= c < 127 for c in name):
        return None
    rc = struct.unpack_from("<H", data, h + 21)[0]
    if not 1 <= rc <= 2000 or h + 30 + 4 * rc > len(data):
        return None
    count = struct.unpack_from("<H", data, h + 28 + 4 * rc)[0]
    if not 100 <= count <= 20000:
        return None
    return rc, count, h + 30 + 4 * rc


@dataclass
class CivUnits:
    tables: list[tuple[int, int]]  # (pointer table offset, unit count) per civ
    units: list[list[Optional[UnitRecord]]]
    start: int = 0  # offset of the civilisation count, where the civilisations block begins


def _parse_civs(data: bytes, first: int, n_civs: int) -> CivUnits:
    tables, civs = [], []
    h = first
    for k in range(n_civs):
        head = _civ_header(data, h)
        if head is None:
            raise DatLayoutError(f"civilisation {k} does not start where civilisation {k - 1} ended ({h})")
        _, count, table = head
        ptrs = struct.unpack_from(f"<{count}i", data, table)
        r = _R(data, table + 4 * count)
        units: list[Optional[UnitRecord]] = []
        for uid, ptr in enumerate(ptrs):
            if not ptr:  # 0 means "no unit"; otherwise any value (a memory address, or 1 after an editor)
                units.append(None)
                continue
            u = _unit(r, k)
            if u.id != uid:
                raise DatLayoutError(f"civ {k}: unit {uid} reads as id {u.id} at {u.offset}")
            units.append(u)
        tables.append((table, count))
        civs.append(units)
        h = r.p
    return CivUnits(tables, civs)


def read_units(data: bytes) -> CivUnits:
    """Every civilisation's units.

    The civilisations block is found by its header: a civ count, then per civ a type, a 20-byte name,
    its starting resources and its unit pointer table. The first candidate whose civilisations all parse
    and follow each other exactly is taken.
    """
    import re
    tried = 0
    for m in re.finditer(rb"(?=[\x00-\x05][\x20-\x7e]{1,19}\x00)", data):
        h = m.start()
        if h < 2:
            continue
        n_civs = struct.unpack_from("<H", data, h - 2)[0]
        if not 2 <= n_civs <= 64 or _civ_header(data, h) is None:
            continue
        tried += 1
        try:
            civs = _parse_civs(data, h, n_civs)
        except (DatLayoutError, struct.error):
            continue
        civs.start = h - 2
        return civs
    raise DatLayoutError(f"could not find the civilisations' unit tables ({tried} candidates checked)")


# a task: type, id, is default, action, target class, target unit, terrain, resources in/multiplier/out/unused,
# work values 1 and 2, work range, auto search, search wait, targeting, combat level, gather type, work flag 2,
# target diplomacy, carry check, pick for construction, moving/proceeding/working/carrying graphics,
# gathering and deposit sounds
TASK = struct.Struct("<hhbhhhhhhhhfffbfbbhhbbbhhhhhh")
GARRISON = 3  # task action: enter a unit or building of the target class
TRANSPORT = 20  # unit class of the Transport Ship


@dataclass
class UnitHeaders:
    offsets: list[int]  # per unit id: offset of its "exists" byte
    tasks: list[Optional[list[tuple]]]  # per unit id: its tasks (None if the unit has no header)


def _parse_headers(data: bytes, at: int, n: int) -> tuple[UnitHeaders, int]:
    p = at + 4
    offsets, tasks = [], []
    for _ in range(n):
        offsets.append(p)
        exists = data[p]
        p += 1
        if exists not in (0, 1):
            raise DatLayoutError("not a unit header")
        if not exists:
            tasks.append(None)
            continue
        count = struct.unpack_from("<H", data, p)[0]
        p += 2
        if count > 500:
            raise DatLayoutError("not a unit header")
        tasks.append([TASK.unpack_from(data, p + TASK.size * k) for k in range(count)])
        p += TASK.size * count
    return UnitHeaders(offsets, tasks), p


def read_unit_headers(data: bytes, civs: CivUnits, search: int = 4_000_000) -> UnitHeaders:
    """Every unit's task list: the block of unit headers that ends exactly where the civilisations begin."""
    n = civs.tables[0][1]
    pattern = struct.pack("<I", n)
    at = civs.start
    while True:
        at = data.rfind(pattern, max(0, civs.start - search), at)
        if at < 0:
            raise DatLayoutError("could not find the units' task lists")
        try:
            heads, end = _parse_headers(data, at, n)
        except (DatLayoutError, struct.error, IndexError):
            continue
        if end == civs.start:
            return heads


def add_task(data: bytearray, heads: UnitHeaders, uid: int, task: tuple) -> None:
    """Append a task to a unit's task list (the file grows; offsets after it move)."""
    tasks = heads.tasks[uid]
    if tasks is None:
        raise DatLayoutError(f"unit {uid} has no task list")
    at = heads.offsets[uid]
    struct.pack_into("<H", data, at + 1, len(tasks) + 1)
    end = at + 3 + TASK.size * len(tasks)
    data[end:end] = TASK.pack(*task)


def decompress(raw: bytes) -> bytes:
    return zlib.decompress(raw, -15)


def compress(data: bytes) -> bytes:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def patch(data: bytearray, unit: UnitRecord, **values) -> None:
    """Overwrite fixed-size fields of one civ's copy of a unit."""
    for name, value in values.items():
        if name not in unit.fields:
            raise KeyError(f"unit {unit.id} ({unit.name}) has no field {name}")
        fmt = "<" + FORMATS[name]
        vals = value if isinstance(value, (tuple, list)) else (value,)
        struct.pack_into(fmt, data, unit.fields[name], *vals)
