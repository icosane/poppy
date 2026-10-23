#!/usr/bin/env python3
"""
custom_arc.py (v2, corrected) - extract / pack / verify for the no-magic
script.arc used by this engine (Switch ports).

FORMAT (verified byte-for-byte by rebuilding a real English script.arc):
    0x00  uint32  data_start   = 8 + count * 72  (where file data begins)
    0x04  uint32  count
    0x08  count x 72-byte entries:
              64 bytes  name, NUL-terminated, remaining bytes filled with 0xFE
               4 bytes  size   (uint32 LE)
               4 bytes  offset (uint32 LE, ABSOLUTE from start of the .arc)
    data_start...  file contents. First file begins exactly at data_start.
                   Each file is followed by one NUL byte, then zero padding so
                   the next file starts on an 8-byte boundary. The last file
                   ends exactly at end-of-archive (no terminator).

(v1 of this script misread the layout by one slot - it paired every name with
the size/offset of the PREVIOUS file. Files extracted with v1 had wrong names
and wrong boundaries, and packing them produced an archive whose real data was
untouched. Use only this version.)

Text inside the scripts is Shift-JIS (use cp932 in Python, a superset).

Usage:
    python3 custom_arc.py list    script.arc
    python3 custom_arc.py extract script.arc [out_dir]    (also writes _index.txt = file order)
    python3 custom_arc.py pack    in_dir new.arc          (order from in_dir/_index.txt)
    python3 custom_arc.py verify  script.arc              (extract -> repack in memory -> must be identical)
"""
import os
import struct
import sys

NAME_SIZE = 64
ENTRY_SIZE = 72
PAD_BYTE = 0xFE


def parse(data):
    if len(data) < 8:
        raise ValueError("file too small")
    data_start, count = struct.unpack_from("<II", data, 0)
    if data_start != 8 + count * ENTRY_SIZE or count == 0 or count > 100000:
        raise ValueError(f"header doesn't look right: data_start={data_start}, count={count} "
                         f"(expected data_start == 8 + count*72)")
    entries = []
    for k in range(count):
        o = 8 + k * ENTRY_SIZE
        raw = data[o:o + NAME_SIZE]
        nul = raw.find(b"\x00")
        if nul <= 0:
            raise ValueError(f"entry {k}: bad name field")
        name = raw[:nul].decode("ascii")
        size, off = struct.unpack_from("<II", data, o + NAME_SIZE)
        if off + size > len(data):
            raise ValueError(f"entry {k} '{name}' runs past end of file")
        entries.append((name, size, off))
    return entries


def build(files):
    """files: list of (name, bytes) in order -> archive bytes."""
    n = len(files)
    data_start = 8 + n * ENTRY_SIZE
    offsets, cur = [], data_start
    for i, (name, content) in enumerate(files):
        offsets.append(cur)
        cur += len(content)
        if i < n - 1:
            cur = (cur + 1 + 7) & ~7  # NUL terminator, then align to 8
    out = bytearray(struct.pack("<II", data_start, n))
    for (name, content), off in zip(files, offsets):
        nb = name.encode("ascii")
        if len(nb) >= NAME_SIZE:
            raise ValueError(f"name too long: {name}")
        out += nb + b"\x00" + bytes([PAD_BYTE]) * (NAME_SIZE - len(nb) - 1)
        out += struct.pack("<II", len(content), off)
    for (name, content), off in zip(files, offsets):
        assert len(out) <= off
        out += b"\x00" * (off - len(out))
        out += content
    return bytes(out)


def cmd_list(path):
    d = open(path, "rb").read()
    for name, size, off in parse(d):
        print(f"{name:<32} size={size:<9} offset={off}")


def cmd_extract(path, out_dir=None):
    d = open(path, "rb").read()
    ents = parse(d)
    out_dir = out_dir or os.path.splitext(os.path.basename(path))[0] + "_extracted"
    os.makedirs(out_dir, exist_ok=True)
    for name, size, off in ents:
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(d[off:off + size])
    with open(os.path.join(out_dir, "_index.txt"), "w", encoding="ascii") as f:
        f.write("\n".join(n for n, _, _ in ents) + "\n")
    print(f"extracted {len(ents)} files to {out_dir}/  (order saved in _index.txt)")


def cmd_pack(in_dir, out_path):
    idx = os.path.join(in_dir, "_index.txt")
    if os.path.exists(idx):
        names = [l.strip() for l in open(idx, encoding="ascii") if l.strip()]
    else:
        names = sorted(n for n in os.listdir(in_dir) if os.path.isfile(os.path.join(in_dir, n)))
        print("WARNING: no _index.txt; using alphabetical order (the game may care about order)")
    files = [(n, open(os.path.join(in_dir, n), "rb").read()) for n in names]
    arc = build(files)
    open(out_path, "wb").write(arc)
    print(f"packed {len(files)} files -> {out_path} ({len(arc)} bytes)")


def cmd_verify(path):
    d = open(path, "rb").read()
    ents = parse(d)
    rebuilt = build([(n, d[o:o + s]) for n, s, o in ents])
    if rebuilt == d:
        print(f"OK: {path} rebuilds byte-for-byte identical ({len(d)} bytes, {len(ents)} files)")
    else:
        i = next((i for i in range(min(len(d), len(rebuilt))) if d[i] != rebuilt[i]), None)
        print(f"MISMATCH: sizes {len(d)} vs {len(rebuilt)}, first difference at byte {i}")
        sys.exit(1)


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        sys.exit(1)
    cmds = {"list": cmd_list, "extract": cmd_extract, "pack": cmd_pack, "verify": cmd_verify}
    if a[0] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[a[0]](*a[1:])


if __name__ == "__main__":
    main()
