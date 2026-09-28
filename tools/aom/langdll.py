"""Read and change strings in the game's language files (language.dll, language_x1.dll, language_x1_p1.dll).

The strings are in each DLL's string table (resource type 6), in blocks of 16: block b holds strings
16 * (b - 1) to 16 * b - 1, each a uint16 length followed by that many UTF-16 characters. The game asks
language_x1_p1.dll first, then language_x1.dll, then language.dll.

A string is changed in place: its block keeps its size (the text may only get shorter; the block is padded
with zeros at its end), so the rest of the file stays byte-for-byte identical and the DLL's layout is untouched.
"""
from __future__ import annotations

import struct
from typing import Optional

RT_STRING = 6
FILES = ("language_x1_p1.dll", "language_x1.dll", "language.dll")  # the order the game looks in


class DllError(ValueError):
    pass


def _sections(data: bytes) -> tuple[int, list[tuple[int, int, int, int]]]:
    """(resource directory RVA, sections as (virtual address, virtual size, file offset, file size))."""
    if data[:2] != b"MZ":
        raise DllError("not a Windows DLL")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise DllError("not a Windows DLL")
    n_sections, opt_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dirs = opt + (96 if magic == 0x10B else 112)
    n_dirs = struct.unpack_from("<I", data, dirs - 4)[0]
    if n_dirs < 3:
        raise DllError("no resources")
    rsrc = struct.unpack_from("<I", data, dirs + 16)[0]
    secs = []
    for k in range(n_sections):
        s = opt + opt_size + 40 * k
        vsize, va, raw_size, raw = struct.unpack_from("<IIII", data, s + 8)
        secs.append((va, vsize, raw, raw_size))
    return rsrc, secs


def _offset(rva: int, secs) -> int:
    for va, vsize, raw, raw_size in secs:
        if va <= rva < va + max(vsize, raw_size):
            return rva - va + raw
    raise DllError(f"address {rva:#x} is outside the file")


def _entries(data: bytes, base: int, at: int) -> list[tuple[int, int, bool]]:
    """(id, offset from the resource directory, is a directory) for a resource directory's entries."""
    named, ids = struct.unpack_from("<HH", data, base + at + 12)
    out = []
    for k in range(named + ids):
        name, target = struct.unpack_from("<II", data, base + at + 16 + 8 * k)
        out.append((name, target & 0x7FFFFFFF, bool(target & 0x80000000)))
    return out


def string_blocks(data: bytes) -> dict[int, list[tuple[int, int]]]:
    """Block number -> (file offset, size) of every language's copy of that block."""
    rsrc_rva, secs = _sections(data)
    if not rsrc_rva:
        return {}
    base = _offset(rsrc_rva, secs)
    blocks: dict[int, list[tuple[int, int]]] = {}
    for type_id, at, is_dir in _entries(data, base, 0):
        if type_id != RT_STRING or not is_dir:
            continue
        for block, at2, is_dir2 in _entries(data, base, at):
            if not is_dir2:
                continue
            for _, leaf, is_dir3 in _entries(data, base, at2):
                if is_dir3:
                    continue
                rva, size = struct.unpack_from("<II", data, base + leaf)
                blocks.setdefault(block, []).append((_offset(rva, secs), size))
    return blocks


def _parse_block(data: bytes, off: int, size: int) -> list[str]:
    out, p = [], off
    for _ in range(16):
        if p + 2 > off + size:
            out.append("")
            continue
        n = struct.unpack_from("<H", data, p)[0]
        out.append(data[p + 2:p + 2 + 2 * n].decode("utf-16-le", "replace"))
        p += 2 + 2 * n
    return out


def read_string(data: bytes, sid: int) -> Optional[str]:
    """String `sid`, or None if this file does not have it."""
    for off, size in string_blocks(data).get(sid // 16 + 1, []):
        text = _parse_block(data, off, size)[sid % 16]
        return text or None
    return None


def set_string(data: bytes, sid: int, text: str) -> bytes:
    """A copy of the DLL with string `sid` set to `text` (in every language's copy of its block)."""
    places = string_blocks(data).get(sid // 16 + 1)
    if not places:
        raise DllError(f"string {sid} is not in this file")
    out = bytearray(data)
    for off, size in places:
        strings = _parse_block(data, off, size)
        strings[sid % 16] = text
        block = b"".join(struct.pack("<H", len(s)) + s.encode("utf-16-le") for s in strings)
        if len(block) > size:
            raise DllError(f"string {sid}: {text!r} does not fit in place")
        out[off:off + size] = block + bytes(size - len(block))
    return bytes(out)


def build_dll(strings: dict[int, str]) -> bytes:
    """A minimal resource-only DLL with these strings (for tests)."""
    blocks: dict[int, list[str]] = {}
    for sid, text in strings.items():
        blocks.setdefault(sid // 16 + 1, [""] * 16)[sid % 16] = text
    ids = sorted(blocks)
    # resource tree: root -> type 6 -> one entry per block -> language 1033 -> data
    root = 16 + 8
    type_dir = root
    type_size = 16 + 8 * len(ids)
    lang_dirs = type_dir + type_size
    leaves = lang_dirs + 24 * len(ids)
    payload = leaves + 16 * len(ids)
    va, file_off = 0x1000, 0x200
    tree = bytearray()
    tree += struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", RT_STRING, 0x80000000 | type_dir)
    tree += struct.pack("<IIHHHH", 0, 0, 0, 0, 0, len(ids))
    for k, b in enumerate(ids):
        tree += struct.pack("<II", b, 0x80000000 | (lang_dirs + 24 * k))
    datas = []
    for k, b in enumerate(ids):
        tree += struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 1033, leaves + 16 * k)
        datas.append(b"".join(struct.pack("<H", len(s)) + s.encode("utf-16-le") for s in blocks[b]))
    at = payload
    for d in datas:
        tree += struct.pack("<IIII", va + at, len(d), 0, 0)
        at += (len(d) + 3) // 4 * 4
    for d in datas:
        tree += d + bytes((len(d) + 3) // 4 * 4 - len(d))
    raw_size = (len(tree) + 0x1FF) // 0x200 * 0x200
    pe = 0x40
    head = bytearray(file_off)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, pe)
    head[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", head, pe + 4, 0x14C, 1, 0, 0, 0, 224, 0x2102)
    opt = pe + 24
    struct.pack_into("<H", head, opt, 0x10B)
    struct.pack_into("<I", head, opt + 92, 16)
    struct.pack_into("<II", head, opt + 96 + 16, va, len(tree))
    sec = opt + 224
    head[sec:sec + 8] = b".rsrc\0\0\0"
    struct.pack_into("<IIII", head, sec + 8, len(tree), va, raw_size, file_off)
    return bytes(head) + bytes(tree) + bytes(raw_size - len(tree))
