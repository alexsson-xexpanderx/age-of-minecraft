"""Windows PE files (DLLs and exes): read their resources, build a resource-only DLL, give a copy new resources.

Only what the mod needs. A copy with new resources keeps every byte of the original: a section is added at the
end holding the whole new resource tree, and the resource directory points at it (the old tree stays, unused).
Layout follows Microsoft's PE/COFF specification.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Union

Key = Union[int, str]
Resources = dict[tuple[Key, Key, int], tuple[bytes, int]]  # (type, name, language) -> (data, code page)
RT_ICON, RT_STRING, RT_GROUP_ICON = 3, 6, 14
SECTION = struct.Struct("<8sIIIIIIHHI")  # name, virtual size, address, raw size, raw offset, ..., characteristics


class PeError(ValueError):
    pass


@dataclass
class Header:
    pe: int  # offset of "PE\0\0"
    opt: int  # offset of the optional header
    dirs: int  # offset of the data directories
    table: int  # offset of the section table
    sections: list[tuple[int, int, int, int]]  # (virtual address, virtual size, raw offset, raw size)
    section_align: int
    file_align: int


def _align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def header(data: bytes) -> Header:
    if data[:2] != b"MZ":
        raise PeError("not a Windows program or DLL")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise PeError("not a Windows program or DLL")
    n, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic not in (0x10B, 0x20B):
        raise PeError("unknown optional header")
    table = opt + opt_size
    secs = []
    for k in range(n):
        _, vsize, va, raw_size, raw, _, _, _, _, _ = SECTION.unpack_from(data, table + 40 * k)
        secs.append((va, vsize, raw, raw_size))
    section_align, file_align = struct.unpack_from("<II", data, opt + 32)
    return Header(pe, opt, opt + (96 if magic == 0x10B else 112), table, secs, section_align, file_align)


def offset(h: Header, rva: int) -> int:
    for va, vsize, raw, raw_size in h.sections:
        if va <= rva < va + max(vsize, raw_size):
            return rva - va + raw
    raise PeError(f"address {rva:#x} is outside the file")


def resources(data: bytes) -> Resources:
    """Every resource, by (type, name, language); names and types are ids, or strings for named ones."""
    return {key: (bytes(data[at:at + size]), codepage) for key, (at, size, codepage) in places(data).items()}


def places(data: bytes) -> dict[tuple[Key, Key, int], tuple[int, int, int]]:
    """Where every resource is in the file: (type, name, language) -> (file offset, size, code page)."""
    h = header(data)
    rva = struct.unpack_from("<I", data, h.dirs + 16)[0]
    if not rva:
        return {}
    base = offset(h, rva)

    def entries(at):
        named, ids = struct.unpack_from("<HH", data, base + at + 12)
        for k in range(named + ids):
            name, target = struct.unpack_from("<II", data, base + at + 16 + 8 * k)
            if name & 0x80000000:
                p = base + (name & 0x7FFFFFFF)
                length = struct.unpack_from("<H", data, p)[0]
                name = data[p + 2:p + 2 + 2 * length].decode("utf-16-le")
            yield name, target & 0x7FFFFFFF, bool(target & 0x80000000)

    out = {}
    for rtype, at1, is_dir1 in entries(0):
        for name, at2, is_dir2 in (entries(at1) if is_dir1 else ()):
            for lang, leaf, is_dir3 in (entries(at2) if is_dir2 else ()):
                if is_dir3:
                    continue
                drva, size, codepage, _ = struct.unpack_from("<IIII", data, base + leaf)
                out[(rtype, name, lang)] = (offset(h, drva), size, codepage)
    return out


def _order(keys) -> list[Key]:
    """Named entries first (by name), then ids in order, as the specification wants."""
    return sorted(keys, key=lambda k: (0, k.upper(), 0) if isinstance(k, str) else (1, "", k))


def tree(res: Resources, va: int) -> bytes:
    """The resource section's bytes for resources placed at virtual address `va`."""
    nested: dict = {}
    for (rtype, name, lang), value in res.items():
        nested.setdefault(rtype, {}).setdefault(name, {})[lang] = value
    types = _order(nested)
    dirs = [("root", None, types)] + [("type", t, _order(nested[t])) for t in types]
    dirs += [("name", (t, n), _order(nested[t][n])) for t in types for n in _order(nested[t])]
    at, where = 0, {}
    for kind, key, children in dirs:
        where[(kind, key)] = at
        at += 16 + 8 * len(children)
    leaves = [(t, n, l) for t in types for n in _order(nested[t]) for l in _order(nested[t][n])]
    leaf_at = {k: at + 16 * i for i, k in enumerate(leaves)}
    at += 16 * len(leaves)
    names_at = {}
    for key in _order({k for t in types for k in [t, *nested[t]] if isinstance(k, str)}):
        names_at[key] = at
        at += 2 + 2 * len(key)
    at = _align(at, 8)
    data_at = {}
    for k in leaves:
        data_at[k] = at
        at = _align(at + len(nested[k[0]][k[1]][k[2]][0]), 8)
    out = bytearray(at)

    def entry(pos, key, target, is_dir):
        name = (0x80000000 | names_at[key]) if isinstance(key, str) else key
        struct.pack_into("<II", out, pos, name, target | (0x80000000 if is_dir else 0))

    for kind, key, children in dirs:
        pos = where[(kind, key)]
        named = sum(isinstance(c, str) for c in children)
        struct.pack_into("<IIHHHH", out, pos, 0, 0, 0, 0, named, len(children) - named)
        for i, child in enumerate(children):
            if kind == "root":
                entry(pos + 16 + 8 * i, child, where[("type", child)], True)
            elif kind == "type":
                entry(pos + 16 + 8 * i, child, where[("name", (key, child))], True)
            else:
                entry(pos + 16 + 8 * i, child, leaf_at[(key[0], key[1], child)], False)
    for key, pos in names_at.items():
        struct.pack_into("<H", out, pos, len(key))
        out[pos + 2:pos + 2 + 2 * len(key)] = key.encode("utf-16-le")
    for k in leaves:
        blob, codepage = nested[k[0]][k[1]][k[2]]
        struct.pack_into("<IIII", out, leaf_at[k], va + data_at[k], len(blob), codepage, 0)
        out[data_at[k]:data_at[k] + len(blob)] = blob
    return bytes(out)


def checksum(data: bytes, at: int) -> int:
    """The PE checksum of `data`, with the checksum field at `at` counted as zero."""
    buf = bytearray(data)
    buf[at:at + 4] = bytes(4)
    if len(buf) % 2:
        buf += b"\0"
    total = sum(struct.unpack(f"<{len(buf) // 2}H", buf))
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return total + len(data)


def with_checksum(data: bytes) -> bytes:
    """The file with its PE checksum brought up to date; a file without one (0) keeps none."""
    h = header(data)
    if not struct.unpack_from("<I", data, h.opt + 64)[0]:
        return data
    out = bytearray(data)
    struct.pack_into("<I", out, h.opt + 64, checksum(out, h.opt + 64))
    return bytes(out)


def build(res: Resources, dll: bool = True) -> bytes:
    """A resource-only DLL (no code, no entry point) holding these resources."""
    payload = tree(res, 0x1000)
    raw = _align(len(payload), 0x200)
    head = bytearray(0x200)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x40)
    pe, opt = 0x40, 0x40 + 24
    head[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", head, pe + 4, 0x14C, 1, 0, 0, 0, 224, 0x2102 if dll else 0x0102)
    struct.pack_into("<HBB" + "I" * 9 + "H" * 6 + "I" * 4 + "HH" + "I" * 6, head, opt,
                     0x10B, 6, 0, 0, raw, 0, 0, 0x1000, 0x1000, 0x10000000 if dll else 0x400000, 0x1000, 0x200,
                     4, 0, 0, 0, 4, 0, 0, 0x1000 + _align(len(payload), 0x1000), 0x200, 0, 2, 0,
                     0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    struct.pack_into("<II", head, opt + 96 + 16, 0x1000, len(payload))
    SECTION.pack_into(head, opt + 224, b".rsrc", len(payload), 0x1000, raw, 0x200, 0, 0, 0, 0, 0x40000040)
    out = bytearray(head + payload + bytes(raw - len(payload)))
    struct.pack_into("<I", out, opt + 64, checksum(out, opt + 64))
    return bytes(out)


def with_resources(data: bytes, res: Resources) -> bytes:
    """A copy of a DLL or exe whose resources are `res`, in a new section at the end; nothing else moves."""
    h = header(data)
    out = bytearray(data)
    cert_at, cert_size = struct.unpack_from("<II", out, h.dirs + 32)
    if cert_at and cert_size:  # a signature no longer matches the changed file, and it sits at its end
        del out[cert_at:]
        struct.pack_into("<II", out, h.dirs + 32, 0, 0)
    end_of_table = h.table + 40 * len(h.sections)
    first_raw = min((raw for _, _, raw, size in h.sections if size), default=len(out))
    size_of_headers = struct.unpack_from("<I", out, h.opt + 60)[0]
    if end_of_table + 40 > min(size_of_headers, first_raw) or any(out[end_of_table:end_of_table + 40]):
        raise PeError("no room for another section in this file's header")
    new_va = _align(max(va + max(vsize, size) for va, vsize, _, size in h.sections), h.section_align)
    payload = tree(res, new_va)
    raw_at, raw_size = _align(len(out), h.file_align), _align(len(payload), h.file_align)
    out += bytes(raw_at - len(out)) + payload + bytes(raw_size - len(payload))
    SECTION.pack_into(out, end_of_table, b".aomrsrc", len(payload), new_va, raw_size, raw_at, 0, 0, 0, 0, 0x40000040)
    struct.pack_into("<H", out, h.pe + 6, len(h.sections) + 1)
    struct.pack_into("<I", out, h.opt + 8, struct.unpack_from("<I", out, h.opt + 8)[0] + raw_size)
    struct.pack_into("<I", out, h.opt + 56, _align(new_va + len(payload), h.section_align))
    struct.pack_into("<II", out, h.dirs + 16, new_va, len(payload))
    struct.pack_into("<I", out, h.opt + 64, checksum(out, h.opt + 64))
    return bytes(out)
