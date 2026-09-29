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

from . import pe

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


def _block(strings: list[str]) -> bytes:
    return b"".join(struct.pack("<H", len(t)) + t.encode("utf-16-le") for t in strings)


def build_dll(strings: dict[int, str]) -> bytes:
    """A resource-only DLL with just these strings."""
    blocks: dict[int, list[str]] = {}
    for sid, text in strings.items():
        blocks.setdefault(sid // 16 + 1, [""] * 16)[sid % 16] = text
    return pe.build({(RT_STRING, b, 1033): (_block(texts), 0) for b, texts in blocks.items()})


def with_strings(data: bytes, strings: dict[int, str]) -> bytes:
    """A copy of a language DLL with these strings set, added where it has none. Nothing in the original changes:
    the new string table goes into a section added at the end (see pe.with_resources)."""
    res = pe.resources(data)
    langs = [lang for (rtype, _, lang) in res if rtype == RT_STRING]
    lang = max(sorted(set(langs)), key=langs.count) if langs else 1033
    for sid, text in strings.items():
        block = sid // 16 + 1
        keys = [k for k in res if k[0] == RT_STRING and k[1] == block] or [(RT_STRING, block, lang)]
        for key in keys:
            blob, codepage = res.get(key, (b"", 0))
            texts = _parse_block(blob, 0, len(blob)) if blob else [""] * 16
            texts[sid % 16] = text
            res[key] = (_block(texts), codepage)
    return pe.with_resources(data, res)


def all_strings(data: bytes) -> dict[int, str]:
    """Every string in the file (the first language's copy of each block)."""
    out = {}
    for block, places in string_blocks(data).items():
        off, size = places[0]
        for k, text in enumerate(_parse_block(data, off, size)):
            if text:
                out[(block - 1) * 16 + k] = text
    return out
