"""Gameplay changes in the .dat: Pac-Man can be trained at the Wonder.

The easter egg lives in Furious the Monkey Boy's slot (unit 860), so the
chat cheat still spawns him. Here every civilisation also gets him enabled,
trained at the Wonder (unit 276), which exists only once a Wonder stands.
He gets his own icon, added at the end of the unit icon sheet (so no other
unit's icon changes), and his name in the language files becomes "Pac-Man".

The Monkey Boy is a "predator animal" (unit class 10), and Transport Ships
do not take animals. Pac-Man becomes infantry (class 6, like the Militia),
and gets the Militia's "board a Transport Ship" task if he lacks it. Like
the wild animals, the Monkey Boy may not stand on beaches (terrain
restriction 1), and ships unload onto the beach ("Not close enough to land
to unload"), so Pac-Man also walks where the Militia walks.

He also gets his own sounds (sounds.py): new entries at the end of the
sound table for clicking on him, ordering him around, training him, his
bites and his death. The Monkey Boy's own sounds are the wolf's, so they
are left alone.

The "to smithereens" cheat's unit, the Saboteur (706), becomes a giant red
Pac-Man (`_giant`): Pac-Man's bite, armour, attack speed and sounds, no
blast (the Saboteur blows itself up), 10000 hit points, a Wonder's room
on the map, and the Militia's boarding task (`_giant_boarding`). The Saboteur borrows the Petard's sprites, which stay the
Petard's: the giant gets a graphic no unit and no other graphic uses (an old
piece of the Trade Cog, `GIANT_GRAPHICS`), pointed at a new SLP of his own
(`giant_slp`: one picture per direction, he is far too big for animations).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import datfile
from . import datunits as DU
from . import langdll
from . import slp

PACMAN_UNIT = 860
WONDER_UNIT = 276
PACMAN_COST = (0, 500, 1, 3, 500, 1, 4, 1, 0)  # 500 food, 500 gold, 1 population
# seconds: 5 minutes, so one Wonder trains few of him; he keeps the cheat unit's attack and armour (99), and
# in Death Match no price would hold him back
PACMAN_TIME = 300
PACMAN_BUTTON = 1
PACMAN_HP = 250  # the Monkey Boy has 50; a unit from a Wonder should last a bit longer
# tiles from his centre to his edge, across and along: his picture is twice the Monkey Boy's size (easter.pacman), so
# his room is twice the Monkey Boy's 0.25 too, and nothing stands inside him (as big as a Mangonel, Scorpion, Bombard
# Cannon or packed Trebuchet, which all pass through gates);
# the selection outline drawn under him grows the same
PACMAN_SIZE = 0.5
# tiles per second: faster than any unit, the cheats' Cobra Car (4.5) included; the fastest units you can train are
# the Demolition Ship (1.6, 1.84 after Dry Dock) and the Hussar (1.5, 1.65 after Husbandry). The Monkey Boy has 0.99.
PACMAN_SPEED = 5.0
INFANTRY = 6  # unit class: foot soldiers board ships, garrison, and get the Blacksmith's infantry upgrades
MILITIA = 74
LAND = 7  # the Militia's terrain restriction: land, beaches and shallows (the Monkey Boy's 1 has no beaches)
UNIT_ICONS = 50730  # the unit icon sheet in interfac.drs
PACMAN_NAME = "Pac-Man"
SABOTEUR = 706  # the "to smithereens" cheat's unit
GIANT_NAME = "Giant Pac-Man"
GIANT_HP = 10000  # more than a Castle and a Wonder together (4800 each)
GIANT_SIZE = 2.5  # tiles from his centre to his edge, a Wonder's: any bigger and the cheat may find no room for him
# graphics no unit and no other graphic uses, each with an SLP of its own (old pieces of the Trade Cog and Galley); the
# first one found becomes the giant's
GIANT_GRAPHICS = ("COGXX_F1", "COGXX_A1", "COGXX_W1", "GALLY_F1", "GALLY_A1")
HELP_STRINGS = 79000  # the .dat stores help text ids 79000 above the string's id in the language files


@dataclass
class DatPatch:
    data: bytes  # the recompressed .dat
    civs: int  # civilisations patched
    notes: list[str]
    pacman_strings: dict[str, int] = None  # the Monkey Boy's text ids: name, creation, help (if Pac-Man was patched)
    sounds_added: bool = False  # the sound table has Pac-Man's sounds: their WAV files must be written too
    giant_name: Optional[int] = None  # the Saboteur's name string, if he became the giant (his SLP must be written)


def wonder_pacman(raw: bytes, graphics: dict) -> tuple[Optional[DatPatch], str]:
    """Make Pac-Man trainable at the Wonder. Returns (patch or None, what happened)."""
    patch, notes = patch_dat(raw, graphics, pacman=True, javelina=False)
    return patch, notes[0]


def patch_dat(raw: bytes, graphics: dict, pacman: bool = True, javelina: bool = True, icon: Optional[int] = None,
              sounds: Optional[dict[str, list[int]]] = None, giant: Optional[int] = None
              ) -> tuple[Optional[DatPatch], list[str]]:
    """All .dat changes: Pac-Man at the Wonder (with icon `icon` and `sounds`, if given), the giant red Pac-Man
    drawn from SLP `giant` (if given; with Pac-Man only), and the Javelina's own sprites. `sounds` maps a sound name
    (see SOUND_USES) to the resource ids of its WAV files.

    Returns (patch, notes)."""
    try:
        data = bytearray(DU.decompress(raw))
        civs = DU.read_units(bytes(data))
    except Exception as exc:  # a .dat we cannot read exactly is left alone
        return None, [f"not changed: could not read the unit tables ({exc})"]
    notes, changed, pac_done, strings = [], False, False, None
    if pacman:
        msg, strings = _pacman(data, civs, graphics, icon)
        pac_done = msg.startswith("Pac-Man (unit")
        changed |= pac_done
        notes.append(msg)
    if javelina:
        msg = _javelina(data, civs, graphics)
        changed |= msg.startswith("Javelina: its own")
        notes.append(msg)
    table = None
    if pac_done and sounds:
        table, msg = _sounds(data, civs, graphics, sounds)
        notes.append(msg)
    giant_gid = giant_name = None
    if pac_done and giant is not None:  # after the sounds: he gets Pac-Man's
        msg, giant_gid, giant_name = _giant(data, civs, graphics, giant)
        notes.append(msg)
    # last, from the back of the file to the front: these grow the file, which moves everything after them
    if pac_done:
        notes.append(_boarding(data, civs))
    if giant_gid is not None:  # his task list comes before Pac-Man's in the file: after it, so nothing moves under it
        notes.append(_giant_boarding(data))
    if table is not None:
        _add_sounds(data, table, sounds)
    if not changed:
        return None, notes
    check = DU.read_units(bytes(data))  # read everything back: same layout, new values
    for units in check.units:
        pac = units[PACMAN_UNIT] if len(units) > PACMAN_UNIT else None
        militia = units[MILITIA] if len(units) > MILITIA else None
        land = militia.values["terrain_restriction"] if militia is not None else LAND
        if pac_done and pac is not None and pac.type >= 70 and (pac.values["train_location"] != WONDER_UNIT
                                                                 or pac.values["class"] != INFANTRY
                                                                 or pac.values["terrain_restriction"] != land):
            return None, notes + ["not changed: the patched file did not read back as expected"]
        sab = units[SABOTEUR] if giant_gid is not None and len(units) > SABOTEUR else None
        if sab is not None and sab.type == 70 and sab.values["standing"][0] == giant_gid and (
                sab.values["hit_points"] != GIANT_HP or sab.values["blast_width"] != 0):
            return None, notes + ["not changed: the giant Pac-Man did not read back as expected"]
    if pac_done:
        try:
            heads = DU.read_unit_headers(bytes(data), check)
        except DU.DatLayoutError:
            return None, notes + ["not changed: the patched task lists did not read back as expected"]
        if giant_gid is not None and not any(t[3] == DU.GARRISON and t[4] == DU.TRANSPORT
                                             for t in heads.tasks[SABOTEUR] or []):
            return None, notes + ["not changed: the giant Pac-Man's boarding task did not read back as expected"]
    packed = DU.compress(bytes(data))
    if table is not None:
        try:
            datfile.read_graphics(packed)
            ok = datfile.sound_table(bytes(data)).count == table.count + len(sounds)
        except (ValueError, struct.error):
            ok = False
        if not ok:
            return None, notes + ["not changed: the patched sound table did not read back as expected"]
    if giant_gid is not None and datfile.read_graphics(packed)[giant_gid].slp != giant:
        return None, notes + ["not changed: the giant Pac-Man's graphic did not read back as expected"]
    return DatPatch(packed, len(civs.units), notes, strings if pac_done else None, sounds_added=table is not None,
                    giant_name=giant_name), notes


def _pacman(data: bytearray, civs, graphics: dict, icon: Optional[int]) -> tuple[str, Optional[dict[str, int]]]:
    patched, strings = 0, None
    for units in civs.units:
        if len(units) <= max(PACMAN_UNIT, WONDER_UNIT):
            continue
        pac, wonder = units[PACMAN_UNIT], units[WONDER_UNIT]
        if pac is None or wonder is None or pac.type < 70 or wonder.type != 80:
            continue
        gfx = graphics.get(pac.values["standing"][0])
        if gfx is not None and not gfx.name.lower().startswith("mkyby"):
            return f"Pac-Man at the Wonder: not changed, unit {PACMAN_UNIT} is {pac.name!r} ({gfx.name})", None
        militia = units[MILITIA]
        land = militia.values["terrain_restriction"] if militia is not None else LAND
        DU.patch(data, pac, enabled=1, train_location=WONDER_UNIT, button=PACMAN_BUTTON, cost=PACMAN_COST,
                 train_time=PACMAN_TIME, hit_points=PACMAN_HP, speed=PACMAN_SPEED, terrain_restriction=land,
                 collision_size=(PACMAN_SIZE, PACMAN_SIZE, pac.values["collision_size"][2]),
                 outline_size=(PACMAN_SIZE, PACMAN_SIZE, pac.values["outline_size"][2]), **{"class": INFANTRY})
        if icon is not None:
            DU.patch(data, pac, icon=icon)
        if strings is None:
            strings = {"name": pac.values["name_id"], "creation": pac.values["creation_id"]}
            if pac.values["help_id"] > HELP_STRINGS:
                strings["help"] = pac.values["help_id"] - HELP_STRINGS
        patched += 1
    if not patched:
        return "Pac-Man at the Wonder: not changed, no civilisation has both the Monkey Boy and the Wonder", None
    return (f"Pac-Man (unit {PACMAN_UNIT}) trainable at the Wonder (unit {WONDER_UNIT}) for {patched} "
            f"civilisations: {PACMAN_COST[1]} food, {PACMAN_COST[4]} gold, {PACMAN_TIME} s, {PACMAN_HP} hit points, "
            f"speed {PACMAN_SPEED:g} (faster than any unit), {PACMAN_SIZE:g} tiles from his centre to his edge"
            + (f", icon {icon}" if icon is not None else "")
            + "; he walks on beaches like the Militia, so ships can unload him"), strings


def giant_graphic(graphics: dict, civs) -> Optional[int]:
    """A graphic for the giant: one of GIANT_GRAPHICS that no unit and no other graphic uses, with an SLP of its own
    and one picture for each of 8 directions (mirrored), as he has."""
    used = set()
    for units in civs.units:
        for u in units:
            if u is not None:
                used |= {g for k in ("standing", "dying", "walking") for g in u.values.get(k, ())}
                used.add(u.values.get("attack_graphic", -1))
    used |= {d.graphic_id for g in graphics.values() for d in g.deltas}
    sharing = {}
    for g in graphics.values():
        sharing[g.slp] = sharing.get(g.slp, 0) + 1
    for name in GIANT_GRAPHICS:
        for gid, g in graphics.items():
            if (g.name.upper() == name and gid not in used and not g.deltas and g.slp > 0 and sharing[g.slp] == 1
                    and g.angle_count == 8 and g.mirroring and g.frame_count == 1 and g.slp_at >= 0):
                return gid
    return None


def _giant(data: bytearray, civs, graphics: dict, slp_id: int) -> tuple[str, Optional[int], Optional[int]]:
    """The Saboteur becomes the giant red Pac-Man: (note, his graphic, his name string)."""
    gid = giant_graphic(graphics, civs)
    if gid is None:
        return f"Giant Pac-Man: not changed, none of {', '.join(GIANT_GRAPHICS)} is free for his picture", None, None
    patched, name = 0, None
    for units in civs.units:
        if len(units) <= max(SABOTEUR, PACMAN_UNIT):
            continue
        sab, pac = units[SABOTEUR], units[PACMAN_UNIT]
        if sab is None or pac is None or sab.type != 70 or pac.type != 70:
            continue
        stand = graphics.get(sab.values["standing"][0])
        if stand is None or not stand.name.upper().startswith("HDSQD"):
            continue  # not the Saboteur this build knows
        bite, armour = pac.values["attacks"], pac.values["armours"]
        if len(sab.values["attacks"]) < len(bite) or len(sab.values["armours"]) < len(armour) or not armour:
            continue
        thick = max(a for _, a in armour)  # his spare attacks hit for nothing, his spare armour is as thick as the rest
        sounds = {f: struct.unpack_from("<h", data, pac.fields[f])[0]  # Pac-Man's, as patched so far
                  for f in ("selection_sound", "dying_sound", "attack_sound", "move_sound")}
        DU.patch(data, sab, hit_points=GIANT_HP, standing=(gid, -1), walking=(gid, -1), dying=(gid, -1),
                 attack_graphic=gid, dead_unit=-1, blast_width=0.0, blast_level=0, reload=pac.values["reload"],
                 attacks=_spares(sab.values["attacks"], bite, 0), armours=_spares(sab.values["armours"], armour, thick),
                 collision_size=(GIANT_SIZE, GIANT_SIZE, sab.values["collision_size"][2]),
                 outline_size=(GIANT_SIZE, GIANT_SIZE, sab.values["outline_size"][2]), **sounds,
                 **{"class": INFANTRY})
        name = sab.values["name_id"]
        patched += 1
    if not patched:
        return "Giant Pac-Man: not changed, unit 706 is not the Saboteur here", None, None
    struct.pack_into("<i", data, graphics[gid].slp_at, slp_id)
    return (f"Giant Pac-Man: the Saboteur (unit {SABOTEUR}, cheat \"to smithereens\") for {patched} civilisations: "
            f"Pac-Man's bite and armour, no blast, {GIANT_HP} hit points, {GIANT_SIZE:g} tiles from his centre to his "
            f"edge; graphic {gid} ({graphics[gid].name}) now draws SLP {slp_id}"), gid, name


def _spares(own: list, wanted: list, amount: int) -> list:
    """`wanted` (class, amount) pairs, then as many more as `own` has, on own classes `wanted` lacks, at `amount`."""
    taken = {c for c, _ in wanted}
    spare = [c for c, _ in own if c not in taken] + [c for c, _ in own]
    return list(wanted) + [(spare[k], amount) for k in range(len(own) - len(wanted))]


_GIANT_SLPS: dict[bytes, bytes] = {}  # palette -> SLP: drawing him takes seconds


def giant_slp(quant) -> bytes:
    """The giant's SLP: the red Pac-Man, one picture for each of the 5 directions stored (the game mirrors the rest),
    in the palette's red team shades, whoever owns him."""
    key = np.asarray(quant.palette).tobytes()
    if key not in _GIANT_SLPS:
        from dataclasses import replace
        from .easter import RED_TEAM, giant_pacman
        from .export import render_frames
        unit = giant_pacman()
        # drawn at half size, every pixel then doubled: his blocks are dozens of pixels wide anyway, and it is four
        # times less to draw
        frames = render_frames(replace(unit, scale=unit.scale / 2), "idle", 1, 8, True, quant)
        out = []
        for f in frames:
            px = f.pixels.repeat(2, 0).repeat(2, 1)
            team = px >= slp.PLAYER
            px[team] = RED_TEAM + (px[team] - slp.PLAYER)
            out.append(slp.SlpFrame(px, (f.hotspot[0] * 2, f.hotspot[1] * 2)))
        _GIANT_SLPS[key] = slp.encode(out)
    return _GIANT_SLPS[key]


def _boarding(data: bytearray, civs) -> str:
    """Give Pac-Man the task that lets a unit board a Transport Ship, if he does not have it."""
    try:
        heads = DU.read_unit_headers(bytes(data), civs)
    except DU.DatLayoutError as exc:
        return f"Pac-Man on ships: infantry now; his task list was not checked ({exc})"
    tasks = heads.tasks[PACMAN_UNIT] if len(heads.tasks) > PACMAN_UNIT else None
    if tasks is None:
        return "Pac-Man on ships: infantry now; he has no task list to add boarding to"
    if any(t[3] == DU.GARRISON and t[4] == DU.TRANSPORT for t in tasks):
        return "Pac-Man on ships: infantry now, so Transport Ships take him (he already has the boarding task)"
    militia = heads.tasks[MILITIA] or []
    board = next((t for t in militia if t[3] == DU.GARRISON and t[4] == DU.TRANSPORT), None)
    if board is None:
        return "Pac-Man on ships: infantry now; no boarding task to copy from the Militia"
    DU.add_task(data, heads, PACMAN_UNIT, (board[0], len(tasks)) + board[2:])
    return "Pac-Man on ships: infantry now, and the Militia's boarding task added, so Transport Ships take him"


def _giant_boarding(data: bytearray) -> str:
    """Give the giant the Militia's boarding task (the Saboteur has none), read afresh: the file may have grown."""
    try:
        civs = DU.read_units(bytes(data))
        heads = DU.read_unit_headers(bytes(data), civs)
    except DU.DatLayoutError as exc:
        return f"Giant Pac-Man on ships: his task list was not checked ({exc})"
    tasks = heads.tasks[SABOTEUR] if len(heads.tasks) > SABOTEUR else None
    if tasks is None:
        return "Giant Pac-Man on ships: he has no task list to add boarding to"
    if any(t[3] == DU.GARRISON and t[4] == DU.TRANSPORT for t in tasks):
        return "Giant Pac-Man on ships: he already has the boarding task"
    board = next((t for t in heads.tasks[MILITIA] or [] if t[3] == DU.GARRISON and t[4] == DU.TRANSPORT), None)
    if board is None:
        return "Giant Pac-Man on ships: no boarding task to copy from the Militia"
    DU.add_task(data, heads, SABOTEUR, (board[0], len(tasks)) + board[2:])
    return "Giant Pac-Man on ships: the Militia's boarding task added, so Transport Ships take him"


# which unit sound each of Pac-Man's sounds replaces; "chomp" and "death" go on his attack and death animations
SOUND_USES = {"select": "selection_sound", "move": "move_sound", "attack": "attack_sound", "train": "train_sound",
              "chomp": None, "death": None}


def _sounds(data: bytearray, civs, graphics: dict, sounds: dict[str, list[int]]):
    """Point Pac-Man at his new sounds (in place); the sounds themselves are added by _add_sounds."""
    try:
        table = datfile.sound_table(bytes(data))
    except (ValueError, struct.error) as exc:
        return None, f"Pac-Man's sounds: not changed, the sound table could not be read ({exc})"
    ids = {name: table.count + k for k, name in enumerate(sounds)}
    first = None
    for units in civs.units:
        pac = units[PACMAN_UNIT] if len(units) > PACMAN_UNIT else None
        if pac is None or pac.type < 70:
            continue
        DU.patch(data, pac, **{field: ids[name] for name, field in SOUND_USES.items() if field and name in ids})
        first = first or pac
    if first is None:
        return None, "Pac-Man's sounds: not changed, no civilisation has him"
    placed = []
    for name, gid in (("chomp", first.values["attack_graphic"]), ("death", first.values["dying"][0])):
        g = graphics.get(gid)
        if name in ids and g is not None and g.name.lower().startswith("mkyby"):
            _graphic_sound(data, g, ids[name])
            placed.append(f"{name} on {g.name}")
    return table, (f"Pac-Man's sounds: {', '.join(ids)} (sounds {min(ids.values())}-{max(ids.values())})"
                   + (f"; {', '.join(placed)}" if placed else ""))


def _graphic_sound(data: bytearray, g, sid: int) -> None:
    """Our sound wherever the animation played one: its own sound, or its per-angle sounds (kept in sync with
    the frames). An animation that played none gets ours as its own sound."""
    played = False
    if g.angle_sounds_at >= 0:
        for a in range(max(1, g.angle_count)):
            for k in range(3):  # (delay, sound id) x 3 per angle
                at = g.angle_sounds_at + 12 * a + 4 * k + 2
                if struct.unpack_from("<h", data, at)[0] >= 0:
                    struct.pack_into("<h", data, at, sid)
                    played = True
    if g.sound >= 0 or not played:
        struct.pack_into("<h", data, g.sound_at, sid)


def _add_sounds(data: bytearray, table, sounds: dict[str, list[int]]) -> None:
    entries = b""
    for k, (name, rids) in enumerate(sounds.items()):
        probs = [100 // len(rids)] * len(rids)
        probs[0] += 100 - sum(probs)
        entries += datfile.sound_entry(table.count + k, [(f"pac{name[:4]}{v}.wav", rid, prob)
                                                         for v, (rid, prob) in enumerate(zip(rids, probs))])
    data[table.end:table.end] = entries
    struct.pack_into("<H", data, table.count_at, table.count + len(sounds))


# The Javelina (unit 822) borrows the Wild Boar's sprites in The Conquerors; its own graphics
# (BOARJ_*) are in the .dat, but their sprite files were never shipped. The build renders those
# files (as a pig) and points the Javelina at them. Its carcass becomes a copy of the boar's
# carcass (same food) with the pig's decay sprite.
JAVELINA, JAVELINA_DEAD, BOAR_DEAD = 822, 823, 356
JAVELINA_ACTIONS = {"BOARJ_AN": "attack", "BOARJ_DN": "die", "BOARJ_FN": "idle", "BOARJ_RN": "run",
                    "BOARJ_SN": "decay", "BOARJ_WN": "walk"}


def javelina_graphics(graphics: dict) -> Optional[dict[str, object]]:
    """The Javelina's own graphics in the .dat, by name, if all six are there."""
    by_name = {g.name.upper(): g for g in graphics.values()}
    found = {name: by_name.get(name) for name in JAVELINA_ACTIONS}
    if any(g is None or g.slp <= 0 for g in found.values()):
        return None
    return found


def _javelina(data: bytearray, civs, graphics: dict) -> str:
    gfx = javelina_graphics(graphics)
    if gfx is None:
        return "Javelina: not changed, its own graphics are not in the .dat"
    gid = {name: next(k for k, g in graphics.items() if g is gfx[name]) for name in gfx}
    patched = corpses = 0
    for units in civs.units:
        if len(units) <= JAVELINA:
            continue
        jav = units[JAVELINA]
        if jav is None or jav.type < 70:
            continue
        stand = graphics.get(jav.values["standing"][0])
        if stand is None or not stand.name.upper().startswith(("BOARX", "BOARJ")):
            continue
        DU.patch(data, jav, standing=(gid["BOARJ_FN"], -1), dying=(gid["BOARJ_DN"], -1),
                 walking=(gid["BOARJ_WN"], gid["BOARJ_RN"]), attack_graphic=gid["BOARJ_AN"])
        patched += 1
        dead, boar_dead = units[JAVELINA_DEAD], units[BOAR_DEAD]
        if (dead is not None and boar_dead is not None and dead.type == boar_dead.type
                and dead.end - dead.offset == boar_dead.end - boar_dead.offset
                and jav.values["dead_unit"] == BOAR_DEAD):
            name = bytes(data[dead.fields["name"]:dead.fields["name"] + len(dead.name)])
            data[dead.offset:dead.end] = data[boar_dead.offset:boar_dead.end]  # same food, same behaviour
            struct.pack_into("<h", data, dead.offset + 3, JAVELINA_DEAD)
            data[dead.fields["name"]:dead.fields["name"] + len(name)] = name
            DU.patch(data, dead, standing=(gid["BOARJ_SN"], -1))
            DU.patch(data, jav, dead_unit=JAVELINA_DEAD)
            corpses += 1
    if not patched:
        return "Javelina: not changed, it does not use the Wild Boar's sprites here"
    return f"Javelina: its own (pig) sprites for {patched} civilisations, with its own carcass for {corpses}"


def pacman_icon(size: int = 36) -> slp.SlpFrame:
    """A unit icon (drawn at 36x36, scaled to `size`): Pac-Man in a blue maze corridor, chasing dots."""
    black, blue, yellow, dark_yellow, eye, dot = 0, 1, 2, 3, 4, 5
    px = np.full((36, 36), black, np.int16)
    px[0:2, :] = px[-2:, :] = px[:, 0:2] = px[:, -2:] = blue
    px[6:8, 2:30] = blue
    px[28:30, 6:34] = blue
    yy, xx = np.mgrid[0:36, 0:36]
    cx, cy, r = 14.5, 17.5, 9.5
    d = np.hypot(xx - cx, yy - cy)
    ang = np.degrees(np.arctan2(-(yy - cy), xx - cx))
    body = (d <= r) & ~((np.abs(ang) < 33) & (xx > cx))
    px[body] = yellow
    px[body & (d > r - 1.3)] = dark_yellow
    px[12:14, 14:16] = eye
    for x in (26, 31):
        px[17:19, x:x + 2] = dot
    if size != 36:
        idx = (np.arange(size) * 36 // size)
        px = px[idx][:, idx]
    return slp.SlpFrame(px, (0, 0))


ICON_COLOURS = {0: (8, 8, 16), 1: (40, 60, 220), 2: (255, 214, 0), 3: (214, 170, 0), 4: (16, 16, 16),
                5: (250, 200, 170)}


def icon_sheets(archives: list[tuple[str, object]]) -> list[tuple[str, object, bytes]]:
    """Every copy of the unit icon sheet, in load order: (archive name, archive, sheet)."""
    out = []
    for name, drs in archives:
        if drs is not None and UNIT_ICONS in drs.ids():
            out.append((name, drs, drs.get(UNIT_ICONS)))
    return out


def new_icon_index(sheets: list[tuple[str, object, bytes]]) -> int:
    """The icon number for Pac-Man: just past the longest copy of the sheet."""
    return max(slp.info(sheet).num_frames for _, _, sheet in sheets)


def add_icon(data: bytes, index: int, quant) -> tuple[Optional[bytes], str]:
    """The unit icon sheet with Pac-Man's icon added as icon `index` (blank icons fill any gap before it)."""
    try:
        info = slp.info(data)
    except ValueError as exc:
        return None, f"not changed ({exc})"
    if info.num_frames > index:
        return None, f"not changed: this sheet already has an icon {index}"
    sizes = [(w, h) for w, h, _, _ in info.sizes if 16 <= w <= 96 and 16 <= h <= 96]
    if not sizes:
        return None, "not changed: no icon in this sheet has a usable size"
    w, h = max(set(sizes), key=sizes.count)  # the size most icons have
    frame = pacman_icon(min(w, h))
    lut = {k: int(quant.indices(np.array([rgb], np.int64))[0]) for k, rgb in ICON_COLOURS.items()}
    px = np.vectorize(lut.get)(frame.pixels).astype(np.int16)
    if (w, h) != px.shape[::-1]:  # not square: centre the icon on a black frame
        full = np.full((h, w), lut[0], np.int16)
        y0, x0 = (h - px.shape[0]) // 2, (w - px.shape[1]) // 2
        full[y0:y0 + px.shape[0], x0:x0 + px.shape[1]] = px
        px = full
    blank = slp.SlpFrame(np.full((1, 1), slp.TRANSPARENT, np.int16), (0, 0))
    frames = [blank] * (index - info.num_frames) + [slp.SlpFrame(px, (0, 0))]
    return slp.append_frames(data, frames), f"Pac-Man is icon {index} ({w}x{h})"


def rename_pacman(files: dict[str, bytes], strings: dict[str, int]) -> tuple[dict[str, bytes], list[str]]:
    """Pac-Man's name in the language files: his name string becomes "Pac-Man", and the old name is replaced
    in his button and help texts. `files` maps file name -> contents; returns the changed files and notes."""
    order = [n for n in langdll.FILES if n in files] + [n for n in files if n not in langdll.FILES]
    old = None
    for name in order:  # the name the game shows comes from the first file that has it
        try:
            old = langdll.read_string(files[name], strings["name"])
        except (langdll.DllError, struct.error):
            continue
        if old:
            break
    if not old:
        return {}, [f"Pac-Man's name: not changed, string {strings['name']} is in none of the language files "
                    f"({', '.join(order) or 'none found'})"]
    changed, notes = {}, []
    for name in order:
        data = files[name]
        try:
            for key, sid in strings.items():
                text = langdll.read_string(data, sid)
                if not text:
                    continue
                new = PACMAN_NAME if key == "name" else text.replace(old, PACMAN_NAME)
                if new != text:
                    data = langdll.set_string(data, sid, new)
        except (langdll.DllError, struct.error) as exc:
            notes.append(f"Pac-Man's name: {name} not changed ({exc})")
            continue
        if data != files[name]:
            changed[name] = data
    if changed:
        notes.insert(0, f"Pac-Man's name: {old!r} is now {PACMAN_NAME!r} in {', '.join(changed)} "
                        f"(strings {', '.join(str(v) for v in strings.values())})")
    return changed, notes
