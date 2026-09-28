"""DRS archives: the resource bundles AoE2 loads its sprites, sounds and palettes from.

    header      40-byte copyright, "1.00", 12-byte type ("tribe"), table count,
                offset of the first file
    tables      per file type: reversed 4-char extension, offset of its file
                list, file count
    file lists  per file: id, offset, size (sorted by id)
    file data
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

COPYRIGHT = b"Copyright (c) 1997 Ensemble Studios.\x1a".ljust(40, b"\0")
# On disk the extensions are reversed: 'slp ' is stored as ' pls'.
EXT = {"slp": b" pls", "bina": b"anib", "wav": b" vaw"}
EXT_BACK = {v: k for k, v in EXT.items()}


class Drs:
    """A DRS archive, read lazily from disk or built in memory."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self.index: dict[str, dict[int, tuple[int, int]]] = {}  # type -> id -> (offset, size)
        self.added: dict[str, dict[int, bytes]] = {}
        if path is not None:
            self._read_index(Path(path))

    def _read_index(self, path: Path) -> None:
        with open(path, "rb") as fh:
            head = fh.read(64)
            _, _, _, tables, _ = struct.unpack("<40s4s12sii", head)
            infos = [struct.unpack("<4sii", fh.read(12)) for _ in range(tables)]
            for ext, off, count in infos:
                fh.seek(off)
                raw = fh.read(12 * count)
                entries = {}
                for i in range(count):
                    fid, foff, size = struct.unpack_from("<iii", raw, 12 * i)
                    entries[fid] = (foff, size)
                self.index[EXT_BACK.get(ext, ext.decode("latin-1")[::-1].strip())] = entries

    def ids(self, kind: str = "slp") -> set[int]:
        return set(self.index.get(kind, {})) | set(self.added.get(kind, {}))

    def get(self, fid: int, kind: str = "slp") -> Optional[bytes]:
        if fid in self.added.get(kind, {}):
            return self.added[kind][fid]
        entry = self.index.get(kind, {}).get(fid)
        if entry is None:
            return None
        with open(self.path, "rb") as fh:
            fh.seek(entry[0])
            return fh.read(entry[1])

    def put(self, fid: int, data: bytes, kind: str = "slp") -> None:
        self.added.setdefault(kind, {})[fid] = data

    def write(self, path: Path) -> None:
        kinds = [k for k in ("bina", "slp", "wav") if self.ids(k)]
        kinds += sorted(k for k in set(self.index) | set(self.added) if k not in kinds and self.ids(k))
        header_size = 64 + 12 * len(kinds)
        lists = {k: sorted(self.ids(k)) for k in kinds}
        list_size = sum(12 * len(v) for v in lists.values())
        first_file = header_size + list_size
        tables, file_lists = bytearray(), bytearray()
        sizes = {}
        for k in kinds:
            for fid in lists[k]:
                added = self.added.get(k, {}).get(fid)
                sizes[(k, fid)] = len(added) if added is not None else self.index[k][fid][1]
        list_off, data_off = header_size, first_file
        for k in kinds:
            ext = EXT.get(k, k.encode("latin-1")[:4][::-1].rjust(4, b" "))
            tables += struct.pack("<4sii", ext, list_off, len(lists[k]))
            for fid in lists[k]:
                file_lists += struct.pack("<iii", fid, data_off, sizes[(k, fid)])
                data_off += sizes[(k, fid)]
            list_off += 12 * len(lists[k])
        head = struct.pack("<40s4s12sii", COPYRIGHT, b"1.00", b"tribe".ljust(12, b"\0"), len(kinds), first_file)
        src = open(self.path, "rb") if self.path is not None else None
        try:
            with open(path, "wb") as out:
                out.write(head + tables + file_lists)
                for k in kinds:  # stream the file data; big archives never sit in memory
                    for fid in lists[k]:
                        added = self.added.get(k, {}).get(fid)
                        if added is None:
                            src.seek(self.index[k][fid][0])
                            added = src.read(self.index[k][fid][1])
                        out.write(added)
        finally:
            if src is not None:
                src.close()
