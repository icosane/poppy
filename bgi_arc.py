#!/usr/bin/env python3
"""
bgi_arc.py - Extractor/packer for BGI/Ethornell "BURIKO ARC20" .arc archives.

Format:
    Header:
        12 bytes   magic "BURIKO ARC20"
         4 bytes   file count (uint32 LE)
    Index (one entry per file, 128 bytes each):
        96 bytes   filename, null-padded/terminated
         4 bytes   offset (uint32 LE, relative to the START of the data
                    section, i.e. right after the last index entry)
         4 bytes   size   (uint32 LE)
        24 bytes   reserved (zero)
    Data:
        raw file bytes back to back, in index order

Notes:
    - This only covers the "BURIKO ARC20" archives (the common modern
      format). Some older titles use a different "Pack"-style header;
      this script will refuse to touch those rather than silently
      producing garbage.
    - Files extracted from an .arc are frequently still individually
      compressed/encrypted (e.g. "DSC FORMAT 1.00", CompressedBG images).
      That's a separate layer handled by other tools (GARbro, bgi script
      tools) - this script only deals with the archive container itself.
    - You almost never need to repack a patched file back into the .arc:
      BGI will load a loose file placed in the game folder over the one
      stored in the archive, as long as the name matches. The pack
      command is included for completeness / cases where you do want a
      rebuilt archive.

Usage:
    python bgi_arc.py extract <archive.arc> [output_dir]
    python bgi_arc.py pack <input_dir> <output.arc>
    python bgi_arc.py list <archive.arc>
"""

import argparse
import os
import struct
import sys

MAGIC = b"BURIKO ARC20"
NAME_FIELD_SIZE = 96
RESERVED_SIZE = 24
INDEX_ENTRY_SIZE = NAME_FIELD_SIZE + 4 + 4 + RESERVED_SIZE  # 128


def read_index(f):
    """Read header + index. Returns list of (name, offset, size) and the
    absolute file offset where the data section begins."""
    magic = f.read(len(MAGIC))
    if magic != MAGIC:
        raise ValueError(
            f"Not a recognized BURIKO ARC20 file (got magic {magic!r}). "
            "This script only supports the 'BURIKO ARC20' archive format; "
            "older BGI titles may use a different header."
        )

    (file_count,) = struct.unpack("<I", f.read(4))

    entries = []
    for _ in range(file_count):
        raw = f.read(INDEX_ENTRY_SIZE)
        if len(raw) != INDEX_ENTRY_SIZE:
            raise ValueError("Unexpected end of file while reading index")

        name_raw = raw[:NAME_FIELD_SIZE]
        name = name_raw.split(b"\x00", 1)[0].decode("shift_jis", errors="replace")

        offset, size = struct.unpack("<II", raw[NAME_FIELD_SIZE:NAME_FIELD_SIZE + 8])
        entries.append((name, offset, size))

    data_start = f.tell()
    return entries, data_start


def extract(arc_path, out_dir):
    with open(arc_path, "rb") as f:
        entries, data_start = read_index(f)

        os.makedirs(out_dir, exist_ok=True)

        for name, offset, size in entries:
            f.seek(data_start + offset)
            data = f.read(size)
            if len(data) != size:
                raise ValueError(
                    f"Truncated read for '{name}': expected {size} bytes, got {len(data)}"
                )

            # Guard against path traversal / weird embedded separators in names
            safe_name = name.replace("\\", "/")
            safe_name = os.path.basename(safe_name) or f"unnamed_{offset:08x}"
            out_path = os.path.join(out_dir, safe_name)

            with open(out_path, "wb") as out_f:
                out_f.write(data)

            print(f"extracted {name!r} ({size} bytes) -> {out_path}")

    print(f"\nDone. {len(entries)} file(s) extracted to '{out_dir}'.")


def list_archive(arc_path):
    with open(arc_path, "rb") as f:
        entries, _ = read_index(f)
        for name, offset, size in entries:
            print(f"{name:<40} offset=0x{offset:08x} size={size}")
        print(f"\n{len(entries)} file(s).")


def pack(in_dir, arc_path, file_order=None):
    """Rebuild a BURIKO ARC20 archive from a directory of loose files.

    file_order: optional explicit list of filenames (relative to in_dir) to
    control ordering; if omitted, files are sorted alphabetically.
    """
    if file_order is None:
        names = sorted(
            n for n in os.listdir(in_dir) if os.path.isfile(os.path.join(in_dir, n))
        )
    else:
        names = file_order

    if not names:
        raise ValueError(f"No files found in '{in_dir}' to pack")

    entries = []
    running_offset = 0
    for name in names:
        name_bytes = name.encode("shift_jis")
        if len(name_bytes) >= NAME_FIELD_SIZE:
            raise ValueError(
                f"Filename '{name}' is too long ({len(name_bytes)} bytes); "
                f"must fit in {NAME_FIELD_SIZE - 1} bytes including the null terminator"
            )
        size = os.path.getsize(os.path.join(in_dir, name))
        entries.append((name, running_offset, size))
        running_offset += size

    with open(arc_path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<I", len(entries)))

        for name, offset, size in entries:
            name_bytes = name.encode("shift_jis")
            name_field = name_bytes + b"\x00" * (NAME_FIELD_SIZE - len(name_bytes))
            f.write(name_field)
            f.write(struct.pack("<II", offset, size))
            f.write(b"\x00" * RESERVED_SIZE)

        for name, offset, size in entries:
            with open(os.path.join(in_dir, name), "rb") as in_f:
                f.write(in_f.read())

    print(f"Packed {len(entries)} file(s) into '{arc_path}'.")


def extract_all(folder, out_root=None, pattern="*.arc"):
    """Extract every .arc archive in a folder, one subfolder per archive.
    Skips (with a warning, not a crash) any file that isn't actually a
    BURIKO ARC20 archive, since a game's data folder often has other
    junk mixed in."""
    import glob
    if out_root is None:
        out_root = folder.rstrip("/\\") + "_extracted"
    arc_paths = sorted(glob.glob(os.path.join(folder, pattern)))
    if not arc_paths:
        print(f"No files matching '{pattern}' found in '{folder}'")
        return
    ok, skipped = 0, 0
    for arc_path in arc_paths:
        name = os.path.splitext(os.path.basename(arc_path))[0]
        out_dir = os.path.join(out_root, name)
        try:
            extract(arc_path, out_dir)
            ok += 1
        except ValueError as e:
            print(f"SKIPPED {arc_path}: {e}")
            skipped += 1
        print()
    print(f"Bulk extract done: {ok} archive(s) extracted, {skipped} skipped, output under '{out_root}'.")


def main():
    parser = argparse.ArgumentParser(description="BGI/Ethornell BURIKO ARC20 archive tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="Extract an .arc archive")
    p_extract.add_argument("archive")
    p_extract.add_argument("out_dir", nargs="?", default=None)

    p_extract_all = sub.add_parser("extract-all", help="Extract every .arc file in a folder")
    p_extract_all.add_argument("folder")
    p_extract_all.add_argument("out_dir", nargs="?", default=None)
    p_extract_all.add_argument("--pattern", default="*.arc", help="glob pattern, default *.arc")

    p_pack = sub.add_parser("pack", help="Pack a directory into an .arc archive")
    p_pack.add_argument("in_dir")
    p_pack.add_argument("archive")

    p_list = sub.add_parser("list", help="List contents of an .arc archive")
    p_list.add_argument("archive")

    args = parser.parse_args()

    if args.command == "extract":
        out_dir = args.out_dir or os.path.splitext(os.path.basename(args.archive))[0] + "_extracted"
        extract(args.archive, out_dir)
    elif args.command == "extract-all":
        extract_all(args.folder, args.out_dir, args.pattern)
    elif args.command == "pack":
        pack(args.in_dir, args.archive)
    elif args.command == "list":
        list_archive(args.archive)


if __name__ == "__main__":
    main()
