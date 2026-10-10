"""How each building set builds: its ground, walls, roofs, doors and towers, so the five sets differ in shape and not
only in colour.

AoE2 gives every civilisation one of five building sets (and one Dark Age look for all, which stays as it is in
structures.py). The buildings in structures.py say what a building is (a barracks has a training yard, a stable a
paddock); this module says how its set puts walls and a roof over it:

    W  West European (Britons, Franks, Celts, Spanish): timber-framed walls, an upper storey jutting out over the
       street, red tile gables, a stone ground floor in the Imperial Age, spired stone towers
    E  Central European (Goths, Teutons, Vikings, Huns): log walls on a stone footing, the logs crossing at the
       corners, low walls under steep roofs that come down to them, carved posts on the gables, stave-church towers
    F  East Asian (Japanese, Chinese, Mongols, Koreans): a stone platform with steps, red pillars and a veranda, white
       walls, roofs in two tiers with upturned corners, pagodas
    M  Middle Eastern (Byzantines, Persians, Saracens, Turks): mud brick in the Feudal Age, then sandstone with blue
       tile bands, flat roofs behind battlements, domes, tall gateway portals, minarets
    X  Mesoamerican (Aztecs, Mayans): thatched mud huts in the Feudal Age, then stepped stone platforms with a stair
       up the front, a carved band under a flat roof with a roof comb, stepped temples

Walls only get windows and decorations on their +x and +y sides: those face the camera.
"""
from __future__ import annotations

from . import voxel as V
from .styles import Style

CAMERA_SIDES = ("+x", "+y")


# --------------------------------------------------------------------------- small pieces

def studs(s: V.Structure, x0, y0, x1, y1, z0, z1, block: str, every: int = 2) -> None:
    """Upright timbers (or pillars) at the corners and every `every` blocks along a box of walls."""
    if z1 < z0:
        return
    for x in range(x0, x1 + 1):
        if (x - x0) % every == 0 or x == x1:
            s.fill(x, y0, z0, x, y0, z1, block)
            s.fill(x, y1, z0, x, y1, z1, block)
    for y in range(y0, y1 + 1):
        if (y - y0) % every == 0 or y == y1:
            s.fill(x0, y, z0, x0, y, z1, block)
            s.fill(x1, y, z0, x1, y, z1, block)


def windows(s: V.Structure, x0, y0, x1, y1, z: int, every: int = 2, glass: str = "glass") -> None:
    """Windows between the timbers of the two walls facing the camera."""
    for x in range(x0 + 1, x1):
        if (x - x0) % every == every // 2 and (x - x0) % every:
            V.window(s, x, y1, z, "+y", glass)
    for y in range(y0 + 1, y1):
        if (y - y0) % every == every // 2 and (y - y0) % every:
            V.window(s, x1, y, z, "+x", glass)


def steep_gable(s: V.Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str, gable: str,
                ridge: str = None, axis: str = "x", overhang: int = 1) -> int:
    """A roof rising two blocks for every block in (twice a stair roof's pitch); returns the level above it."""
    if axis == "x":
        lo, hi, level = y0 - overhang, y1 + overhang, z
        while hi - lo >= 1:
            for x in range(x0 - overhang, x1 + overhang + 1):
                s.set(x, lo, level, roof)
                s.set(x, lo, level + 1, roof, "stair_-y")
                s.set(x, hi, level, roof)
                s.set(x, hi, level + 1, roof, "stair_+y")
            if hi - lo >= 2:
                s.fill(x0, lo + 1, level, x1, hi - 1, level + 1, gable)
            lo, hi, level = lo + 1, hi - 1, level + 2
        if lo == hi:
            for x in range(x0 - overhang, x1 + overhang + 1):
                s.set(x, lo, level, ridge or roof, "slab")
            level += 1
        return level
    lo, hi, level = x0 - overhang, x1 + overhang, z
    while hi - lo >= 1:
        for y in range(y0 - overhang, y1 + overhang + 1):
            s.set(lo, y, level, roof)
            s.set(lo, y, level + 1, roof, "stair_-x")
            s.set(hi, y, level, roof)
            s.set(hi, y, level + 1, roof, "stair_+x")
        if hi - lo >= 2:
            s.fill(lo + 1, y0, level, hi - 1, y1, level + 1, gable)
        lo, hi, level = lo + 1, hi - 1, level + 2
    if lo == hi:
        for y in range(y0 - overhang, y1 + overhang + 1):
            s.set(lo, y, level, ridge or roof, "slab")
        level += 1
    return level


def steep_hip(s: V.Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str, overhang: int = 1) -> int:
    """A spire: a pyramid roof rising two blocks for every block in, to a point; returns the level above it."""
    x0, x1, y0, y1, level = x0 - overhang, x1 + overhang, y0 - overhang, y1 + overhang, z
    while x1 - x0 >= 1 and y1 - y0 >= 1:
        s.fill(x0, y0, level, x1, y1, level + 1, roof)
        for x in range(x0, x1 + 1):
            s.set(x, y0, level + 1, roof, "stair_-y")
            s.set(x, y1, level + 1, roof, "stair_+y")
        for y in range(y0 + 1, y1):
            s.set(x0, y, level + 1, roof, "stair_-x")
            s.set(x1, y, level + 1, roof, "stair_+x")
        x0, x1, y0, y1, level = x0 + 1, x1 - 1, y0 + 1, y1 - 1, level + 2
    if x1 >= x0 and y1 >= y0:
        s.fill(x0, y0, level, x1, y1, level, roof)
        level += 1
    return level


def skirt(s: V.Structure, x0: int, x1: int, y0: int, y1: int, z: int, roof: str) -> None:
    """A ring of roof one block out round a wall's top at level z, with a lid over the wall: one eave of a stave
    church (no upturned corners: that is the pagoda's)."""
    for x in range(x0 - 1, x1 + 2):
        s.set(x, y0 - 1, z, roof, "stair_-y")
        s.set(x, y1 + 1, z, roof, "stair_+y")
    for y in range(y0, y1 + 1):
        s.set(x0 - 1, y, z, roof, "stair_-x")
        s.set(x1 + 1, y, z, roof, "stair_+x")
    s.fill(x0, y0, z, x1, y1, z, roof)


def _column_top(s: V.Structure, x: int, y: int) -> int:
    return max((z for (bx, by, z) in s.blocks if bx == x and by == y), default=0)


# --------------------------------------------------------------------------- the ground a building stands on

def ground(s: V.Structure, st: Style, x0, y0, x1, y1, grand: bool = True) -> tuple[int, tuple[int, int, int, int]]:
    """What the set builds under a building on the rectangle: returns (the level its walls start at, the rectangle
    left for the walls). East Asian buildings stand on a stone platform with steps up the front and a veranda on the
    camera sides; Mesoamerican stone buildings (`grand`, from the Castle Age) on stepped platforms."""
    if st.key == "F":
        s.fill(x0, y0, 0, x1, y1, 0, st.base)
        for x in range((x0 + x1) // 2 - 1, (x0 + x1) // 2 + 2):
            s.set(x, y1 + 1, 0, st.base, "stair_+y")
        return 1, (x0, y0, x1 - 1, y1 - 1)
    if st.key == "X" and grand and st.age >= 3 and min(x1 - x0, y1 - y0) >= 6:
        tiers = 2 if min(x1 - x0, y1 - y0) >= 9 else 1
        for k in range(tiers):
            s.fill(x0 + k, y0 + k, k, x1 - k, y1 - k, k, st.base if k == 0 else st.wall)
            s.fill(x0 + k, y1 - k, k, x1 - k, y1 - k, k, st.stone2)  # a carved edge on the front
        mid = (x0 + x1) // 2
        for k in range(tiers):  # a stair straight up the front
            for x in (mid - 1, mid, mid + 1):
                s.set(x, y1 - k + 1 if k else y1 + 1, k, st.base, "stair_+y")
        return tiers, (x0 + tiers, y0 + tiers, x1 - tiers, y1 - tiers)
    return 0, (x0, y0, x1, y1)


# --------------------------------------------------------------------------- walls and roof

def hall(s: V.Structure, st: Style, x0, y0, x1, y1, z0: int, h: int, axis: str = "x", roof: bool = True,
         simple: bool = False) -> int:
    """Walls `h` blocks tall from level z0 over the rectangle, in the set's manner, and its roof (unless `roof` is
    False); returns the level above it all. `simple` buildings (houses, sheds) stay humble: Mesoamerican ones keep
    their thatch in every age."""
    if st.key == "W":
        return _west(s, st, x0, y0, x1, y1, z0, h, axis, roof)
    if st.key == "E":
        return _central(s, st, x0, y0, x1, y1, z0, h, axis, roof)
    if st.key == "F":
        return _asian(s, st, x0, y0, x1, y1, z0, h, roof)
    if st.key == "M":
        return _eastern(s, st, x0, y0, x1, y1, z0, h, roof)
    if st.key == "X":
        return _meso(s, st, x0, y0, x1, y1, z0, h, axis, roof, simple)
    raise ValueError(f"no building set {st.key}")


def thatched(st: Style, simple: bool = True) -> bool:
    """A Mesoamerican building with mud walls and a thatched roof rather than stone."""
    return st.key == "X" and (simple or st.age <= 2)


def tiles(st: Style) -> str:
    """Middle Eastern glazed tiles: turquoise in the Castle Age, deep blue in the Imperial Age."""
    return "cyan_concrete" if st.age <= 3 else "lapis_block"


def daub(st: Style) -> str:
    """A thatched building's walls: bare mud, then white plaster from the Castle Age."""
    return "packed_mud" if st.age <= 2 else "white_concrete"


def _west(s, st, x0, y0, x1, y1, z0, h, axis, roof) -> int:
    """Timber-framed: a stone sill, studs every other block, a beam along the top; two storeys jut out over the
    street (the +x and +y sides); a red tile gable roof with a timber up the middle of each gable end."""
    beam = "stripped_dark_oak_log" if st.age >= 3 else "stripped_oak_log"
    two = h >= 4
    gh = 3 if two else h
    s.fill(x0, y0, z0, x1, y1, z0 + gh - 1, st.base if st.age >= 4 else st.wall)
    s.fill(x0, y0, z0, x1, y1, z0, st.base)
    frame = "dark_oak_log" if st.age >= 3 else "spruce_log"
    if st.age < 4:
        studs(s, x0, y0, x1, y1, z0 + 1, z0 + gh - 2, frame)
    s.ring(x0, y0, x1, y1, z0 + gh - 1, z0 + gh - 1, beam)
    windows(s, x0, y0, x1, y1, z0 + 1)
    top, rect = z0 + gh, (x0, y0, x1, y1)
    if two:
        ux1, uy1 = x1 + 1, y1 + 1
        s.fill(x0, y0, top, ux1, uy1, z0 + h - 1, st.wall_hi)
        studs(s, x0, y0, ux1, uy1, top, z0 + h - 1, frame)
        for x in range(x0, ux1 + 1):  # the jetty's joists under the overhang
            s.set(x, uy1, top - 1, beam, "top_slab")
        for y in range(y0, uy1 + 1):
            s.set(ux1, y, top - 1, beam, "top_slab")
        windows(s, x0, y0, ux1, uy1, z0 + h - 1)
        top, rect = z0 + h, (x0, y0, ux1, uy1)
    if not roof:
        return top
    rx0, ry0, rx1, ry1 = rect
    level = V.gable_roof(s, rx0, rx1, ry0, ry1, top, st.roof, st.wall_hi, st.roof_cap, axis=axis)
    if axis == "x":  # the gable end facing the camera: a timber under the ridge
        s.fill(rx1, (ry0 + ry1) // 2, top, rx1, (ry0 + ry1) // 2, level - 2, frame)
    else:
        s.fill((rx0 + rx1) // 2, ry1, top, (rx0 + rx1) // 2, ry1, level - 2, frame)
    return level


def _central(s, st, x0, y0, x1, y1, z0, h, axis, roof) -> int:
    """Log walls on a stone footing, the logs crossing and sticking out at the corners; low walls under a steep roof
    that reaches down to them, with carved posts standing up from the gable ends."""
    logs = (f"{st.wood}_wood", f"stripped_{st.wood}_log")
    eh = max(2, h - 1)
    feet = 1 if st.age <= 2 else 2
    s.fill(x0, y0, z0, x1, y1, z0 + eh - 1, logs[0])
    s.fill(x0, y0, z0, x1, y1, z0 + min(feet, eh - 1) - 1, st.base if st.age < 4 else st.stone)
    for z in range(z0 + feet, z0 + eh):
        s.ring(x0, y0, x1, y1, z, z, logs[(z - z0) % 2])
        along_x = (z - z0) % 2 == 1
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            s.set(x, y, z, st.log)
            if eh - feet < 2:  # one course of logs: no crossing to show
                continue
            if along_x:
                s.set(x + (1 if x == x1 else -1), y, z, st.log)
            else:
                s.set(x, y + (1 if y == y1 else -1), z, st.log)
    windows(s, x0, y0, x1, y1, z0 + eh - 1, every=3)
    top = z0 + eh
    if not roof:
        return top
    level = steep_gable(s, x0, x1, y0, y1, top - 1, st.roof, st.wall_hi, st.roof_cap, axis=axis)
    if axis == "x":
        ridge = [(x, (y0 + y1) // 2) for x in (x0 - 1, x1 + 1)]
        if (y1 - y0) % 2:
            ridge += [(x, (y0 + y1) // 2 + 1) for x in (x0 - 1, x1 + 1)]
    else:
        ridge = [((x0 + x1) // 2, y) for y in (y0 - 1, y1 + 1)]
        if (x1 - x0) % 2:
            ridge += [((x0 + x1) // 2 + 1, y) for y in (y0 - 1, y1 + 1)]
    for x, y in ridge:  # carved posts at the ends of the ridge
        z = _column_top(s, x, y) + 1
        s.set(x, y, z, st.log, "post")
    return level + 1


def _asian(s, st, x0, y0, x1, y1, z0, h, roof) -> int:
    """White walls on a dark sill between red pillars; on a platform, more pillars hold the eaves over the veranda.
    The roof has two tiers when there is room: a wide eave with upturned corners, a short upper wall, then a hipped
    roof with its own flared eave; gold ornaments end the ridge from the Castle Age."""
    beam = "dark_oak_planks"
    s.fill(x0, y0, z0, x1, y1, z0 + h - 1, st.wall)
    s.fill(x0, y0, z0, x1, y1, z0, beam)
    s.ring(x0, y0, x1, y1, z0 + h - 1, z0 + h - 1, beam)
    studs(s, x0, y0, x1, y1, z0, z0 + h - 1, st.trim, every=3 if max(x1 - x0, y1 - y0) >= 6 else 9)
    windows(s, x0, y0, x1, y1, z0 + max(1, h - 2), glass="white_wool" if st.age <= 2 else "glass")
    for x, y in ((x1 + 1, y0), (x1 + 1, y1 + 1), (x0, y1 + 1)):  # the veranda's pillars, on the platform
        if s.get(x, y, z0 - 1) is not None:
            s.fill(x, y, z0, x, y, z0 + h - 1, st.trim, "post")
    if not roof:
        return z0 + h
    z = z0 + h
    V.pagoda_roof(s, x0, x1, y0, y1, z, st.roof, st.trim)
    if min(x1 - x0, y1 - y0) >= 3:
        ix0, iy0, ix1, iy1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1
        s.fill(ix0, iy0, z + 1, ix1, iy1, z + 1, st.wall_hi)
        studs(s, ix0, iy0, ix1, iy1, z + 1, z + 1, st.trim, every=9)
        V.pagoda_roof(s, ix0, ix1, iy0, iy1, z + 2, st.roof, st.trim)
        top = V.hip_roof(s, ix0, ix1, iy0, iy1, z + 3, st.roof, overhang=0, cap=st.roof_cap)
        ends = [(ix0, iy0), (ix1, iy1)] if ix1 - ix0 != iy1 - iy0 else [((ix0 + ix1) // 2, (iy0 + iy1) // 2)]
    else:
        top = V.hip_roof(s, x0, x1, y0, y1, z + 1, st.roof, overhang=0, cap=st.roof_cap)
        ends = [((x0 + x1) // 2, (y0 + y1) // 2)]
    if st.age >= 3:
        for x, y in ends:
            s.set(x, y, _column_top(s, x, y) + 1, st.accent if st.age >= 4 else "gold_block", "cube_small")
    return top + 1


def _eastern(s, st, x0, y0, x1, y1, z0, h, roof) -> int:
    """Thick walls, mud brick in the Feudal Age, then sandstone with a band of blue tiles under the roof line; small
    windows high up; a flat roof behind a parapet of merlons."""
    wall = "mud_bricks" if st.age <= 2 else st.wall
    s.fill(x0, y0, z0, x1, y1, z0 + h - 1, wall)
    s.fill(x0, y0, z0, x1, y1, z0, "packed_mud" if st.age <= 2 else st.base)
    if st.age >= 3:
        s.ring(x0, y0, x1, y1, z0 + h - 1, z0 + h - 1, tiles(st))
    windows(s, x0, y0, x1, y1, z0 + h - 2, every=3)
    if not roof:
        return z0 + h
    s.fill(x0, y0, z0 + h, x1, y1, z0 + h, st.wall_hi if st.age >= 3 else wall)
    edge = st.base if st.age >= 3 else "packed_mud"
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if (x in (x0, x1) or y in (y0, y1)) and (x + y) % 2 == 0:
                s.set(x, y, z0 + h + 1, edge)
    return z0 + h + 2


def _meso(s, st, x0, y0, x1, y1, z0, h, axis, roof, simple) -> int:
    """Thatched: mud walls between jungle-wood posts under a tall hay roof. Stone: a carved band and a painted band
    under a flat roof, with a pierced roof comb standing along the middle of it."""
    if thatched(st, simple):
        s.fill(x0, y0, z0, x1, y1, z0 + h - 1, daub(st))
        s.fill(x0, y0, z0, x1, y1, z0, st.base)
        if st.age >= 3:
            s.ring(x0, y0, x1, y1, z0 + h - 1, z0 + h - 1, "red_terracotta")
        studs(s, x0, y0, x1, y1, z0, z0 + h - 1, st.log, every=9)
        windows(s, x0, y0, x1, y1, z0 + h - 2, every=4)
        if not roof:
            return z0 + h
        top = V.hip_roof(s, x0, x1, y0, y1, z0 + h, "hay", overhang=1)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        s.set(cx, cy, _column_top(s, cx, cy) + 1, st.log, "post")
        return top + 1
    s.fill(x0, y0, z0, x1, y1, z0 + h - 1, st.wall)
    s.fill(x0, y0, z0, x1, y1, z0, st.base)
    s.ring(x0, y0, x1, y1, z0 + h - 2, z0 + h - 2, st.stone2)
    s.ring(x0, y0, x1, y1, z0 + h - 1, z0 + h - 1, "red_terracotta" if st.age <= 3 else "gold_block")
    windows(s, x0, y0, x1, y1, z0 + max(1, h - 3), every=4)
    if not roof:
        return z0 + h
    s.fill(x0, y0, z0 + h, x1, y1, z0 + h, st.base, "slab")
    top = z0 + h + 1
    if axis == "x":  # the roof comb, pierced every other block
        cy = (y0 + y1) // 2
        s.fill(x0 + 1, cy, top, x1 - 1, cy, top + 1, st.stone2)
        for x in range(x0 + 2, x1 - 1, 2):
            s.clear(x, cy, top)
    else:
        cx = (x0 + x1) // 2
        s.fill(cx, y0 + 1, top, cx, y1 - 1, top + 1, st.stone2)
        for y in range(y0 + 2, y1 - 1, 2):
            s.clear(cx, y, top)
    return top + 2


def shed(s: V.Structure, st: Style, x0, y0, x1, y1, z: int, axis: str = "x") -> int:
    """An open shed: posts at the corners holding the set's roof at level z; returns the level above it."""
    post = {"W": st.log, "E": st.log, "F": st.trim, "M": "mud_bricks" if st.age <= 2 else st.wall,
            "X": st.log}[st.key]
    for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        s.fill(x, y, 0, x, y, z - 1, post, "post" if st.key == "F" else "full")
    if st.key == "W":
        return V.gable_roof(s, x0, x1, y0, y1, z, st.roof, st.planks, st.roof_cap, axis=axis, overhang=0)
    if st.key == "E":
        return steep_gable(s, x0, x1, y0, y1, z - 1, st.roof, st.planks, st.roof_cap, axis=axis, overhang=0)
    if st.key == "F":
        V.pagoda_roof(s, x0, x1, y0, y1, z, st.roof, st.trim)
        return V.hip_roof(s, x0, x1, y0, y1, z + 1, st.roof, overhang=0) if min(x1 - x0, y1 - y0) >= 2 else z + 1
    if st.key == "M":
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                s.set(x, y, z, st.cloth if (x + y) % 2 == 0 else "white_wool", "slab")
        return z + 1
    return V.hip_roof(s, x0, x1, y0, y1, z, "hay", overhang=1)


# --------------------------------------------------------------------------- doors and towers

def door(s: V.Structure, st: Style, x: int, y: int, z: int, facing: str, double: bool = False) -> None:
    """The set's door. A Middle Eastern one stands in a tall portal that rises above the roof line, framed in carved
    stone and topped with tiles."""
    V.door(s, x, y, z, facing, st.wood, double)
    if st.key != "M":
        return
    width = 2 if double else 1
    frame = st.stone2 if st.age >= 3 else "packed_mud"
    cap = tiles(st) if st.age >= 3 else frame
    if facing == "+y":
        cols = [(x - 1, y), (x + width, y)]
        lintel = [(xx, y) for xx in range(x - 1, x + width + 1)]
    else:
        cols = [(x, y - 1), (x, y + width)]
        lintel = [(x, yy) for yy in range(y - 1, y + width + 1)]
    top = max(_column_top(s, cx, cy) for cx, cy in cols) + 1
    for cx, cy in cols:
        s.fill(cx, cy, z, cx, cy, top, frame)
    for cx, cy in lintel:
        s.fill(cx, cy, z + 2, cx, cy, top, frame)
        s.set(cx, cy, top + 1, cap, "slab")
    if facing == "+y":
        s.fill(x, y, z + 2, x + width - 1, y, z + 2, cap)
    else:
        s.fill(x, y, z + 2, x, y + width - 1, z + 2, cap)


def tower(s: V.Structure, st: Style, x0: int, y0: int, n: int, z0: int, h: int) -> int:
    """The set's tower on an n x n footprint, its shaft h blocks tall from level z0; returns the level above its top.
    A bell tower with a pointed spire, a stave tower of stacked roofs, a pagoda, a minaret or a stepped temple."""
    x1, y1 = x0 + n - 1, y0 + n - 1
    cx, cy = x0 + n / 2, y0 + n / 2
    k = st.key
    if k == "W":
        s.fill(x0, y0, z0, x1, y1, z0 + h - 1, st.stone if st.age >= 3 else st.base)
        for z in range(z0 + 2, z0 + h, 3):
            V.window(s, x1, (y0 + y1 + 1) // 2, z, "+x")
        s.carve(x0, y0, z0 + h - 2, x1, y1, z0 + h - 2)  # the belfry's openings
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            s.set(x, y, z0 + h - 2, st.stone if st.age >= 3 else st.base)
        s.fill(x0, y0, z0 + h - 1, x1, y1, z0 + h - 1, st.stone if st.age >= 3 else st.base)
        top = steep_hip(s, x0, x1, y0, y1, z0 + h, st.roof)
        s.set(x0 + (n - 1) // 2, y0 + (n - 1) // 2, top, st.accent if st.age >= 4 else "gold_block", "cube_small")
        return top + 1
    if k == "E":  # a stave church tower: eave skirts one above another, log walls between, a steep spire
        logs = (f"{st.wood}_wood", f"stripped_{st.wood}_log")
        for zz in range(z0, z0 + h):
            s.fill(x0, y0, zz, x1, y1, zz, logs[(zz - z0) % 2])
        top = z0 + h
        rx0, ry0, rx1, ry1 = x0, y0, x1, y1
        for tier in range(2 if n <= 2 else 3):
            skirt(s, rx0, rx1, ry0, ry1, top, st.roof)
            for x, y in ((rx0 - 1, ry0 - 1), (rx0 - 1, ry1 + 1), (rx1 + 1, ry0 - 1), (rx1 + 1, ry1 + 1)):
                s.set(x, y, top + 1, st.log, "post")  # carved heads on the eave's corners
            top += 1
            if rx1 - rx0 >= 2:
                rx0, ry0, rx1, ry1 = rx0 + 1, ry0 + 1, rx1 - 1, ry1 - 1
            s.fill(rx0, ry0, top, rx1, ry1, top + 1, logs[tier % 2])
            top += 2
        top = steep_hip(s, rx0, rx1, ry0, ry1, top, st.roof)
        s.set(rx0 + (rx1 - rx0) // 2, ry0 + (ry1 - ry0) // 2, top, st.log, "post")
        return top + 1
    if k == "F":
        top = z0
        for tier in range(max(2, h // 2)):
            s.fill(x0, y0, top, x1, y1, top, st.wall)
            studs(s, x0, y0, x1, y1, top, top, st.trim, every=9)
            V.pagoda_roof(s, x0, x1, y0, y1, top + 1, st.roof, st.trim)
            top += 2
        top = V.hip_roof(s, x0, x1, y0, y1, top, st.roof, overhang=0)
        s.fill(int(cx), int(cy), top, int(cx), int(cy), top + 1, "gold_block" if st.age >= 3 else st.trim, "post")
        return top + 2
    if k == "M":  # a minaret: a round shaft, a balcony, a slimmer top and a pointed cap
        r = n / 2 + 0.05
        shaft = st.wall_hi if st.age >= 3 else "mud_bricks"
        s.cylinder(cx, cy, r, z0, z0 + h - 1, shaft)
        if st.age >= 3:
            s.cylinder(cx, cy, r, z0 + h // 2, z0 + h // 2, tiles(st))
        s.cylinder(cx, cy, r + 0.9, z0 + h, z0 + h, st.stone2 if st.age >= 3 else "packed_mud")
        upper = r if n <= 2 else r - 0.5
        s.cylinder(cx, cy, upper, z0 + h + 1, z0 + h + 2, shaft)
        cap = st.dome if st.age >= 3 else "packed_mud"
        s.cylinder(cx, cy, upper, z0 + h + 3, z0 + h + 3, cap)
        s.cylinder(cx, cy, upper, z0 + h + 4, z0 + h + 4, cap, )
        for (x, y, z), (name, _) in list(s.blocks.items()):
            if z == z0 + h + 4 and name == cap and abs(x + 0.5 - cx) < n and abs(y + 0.5 - cy) < n:
                s.set(x, y, z, cap, "slab")
        s.set(x0 + (n - 1) // 2, y0 + (n - 1) // 2, z0 + h + 5, "gold_block" if st.age >= 3 else "packed_mud", "post")
        return z0 + h + 6
    # X: a stepped temple, a shrine on top
    top, k_ = z0, 0
    while x1 - k_ - (x0 + k_) >= 0 and top < z0 + h:
        s.fill(x0 + k_, y0 + k_, top, x1 - k_, y1 - k_, top + 1, st.wall if not thatched(st, False) else "packed_mud")
        top += 2
        k_ += 1 if x1 - x0 - 2 * k_ > 2 else 0
    s.ring(x0 + k_, y0 + k_, x1 - k_, y1 - k_, top, top, "red_terracotta")
    s.fill(x0 + k_, y0 + k_, top + 1, x1 - k_, y1 - k_, top + 1, st.stone2)
    return top + 2


def dome(s: V.Structure, st: Style, cx: float, cy: float, z: int, r: float) -> int:
    """A Middle Eastern dome on a drum, with a gold finial; returns the level above it."""
    s.cylinder(cx, cy, r, z, z, st.wall_hi if st.age >= 3 else "mud_bricks")
    s.dome(cx, cy, z + 1, r, st.dome if st.age >= 3 else "packed_mud", squash=1.15)
    top = _column_top(s, int(cx), int(cy)) + 1
    s.set(int(cx), int(cy), top, "gold_block" if st.age >= 3 else "packed_mud", "post")
    return top + 1
