#!/usr/bin/env python3
"""
custom_arc.py - Extractor for the .arc format used by AirVelocity's version of LOVEPICAL-POPPY!.

IMPORTANT: This is NOT the BGI/Ethornell "BURIKO ARC20" format. 

Format (reverse-engineered from the sample file):
    Index (no header/magic, starts at byte 0):
        One 72-byte entry per file, count = index_size / 72 (determined by
        scanning until entries stop looking like valid records):
            4 bytes   size   (uint32 LE) - byte length of this file's content
            4 bytes   offset (uint32 LE) - ABSOLUTE byte offset of this
                       file's content, measured from the very start of the
                       .arc file. NOTE: for the very first entry only, this
                       field does not hold a valid offset (it's repurposed
                       for something else) - the first file's content
                       always starts immediately after the index instead.
           64 bytes   filename, null-terminated, padded with 0xFE (not
                       0x00!) after the terminator.
    Data:
        Files are stored back-to-back (in the same order as the index) each
        followed by a few bytes of null padding before the next one starts.
        There is also frequently one extra, undeclared chunk of data after
        the last indexed file, running to the end of the .arc - this script
        recovers it too, as "_trailing_chunk.bin".

Usage:
    python3 custom_arc.py extract myfile.arc [output_dir]
    python3 custom_arc.py list myfile.arc
"""

import os
import struct
import sys

ENTRY_SIZE = 72
NAME_FIELD_SIZE = 64
NAME_PAD_BYTE = 0xFE


def parse_index(data):
    """Scan from byte 0 for consecutive valid-looking 72-byte entries.
    Returns (entries, index_size) where entries is a list of
    (name, size, raw_offset_field)."""
    entries = []
    off = 0
    while off + ENTRY_SIZE <= len(data):
        size, raw_offset = struct.unpack_from("<II", data, off)
        name_field = data[off + 8: off + ENTRY_SIZE]
        nul = name_field.find(b"\x00")
        if nul == -1:
            break  # doesn't look like a name field -> index has ended
        name_bytes = name_field[:nul]
        if not name_bytes or any(b < 0x20 or b > 0x7E for b in name_bytes):
            break  # not printable ASCII -> not a real entry
        # padding after the null should be the 0xFE filler (allow a few
        # exceptions in case the name runs right up to the edge)
        entries.append((name_bytes.decode("ascii"), size, raw_offset))
        off += ENTRY_SIZE
    return entries, off


def resolve_offsets(entries, index_size):
    """Work out each file's real absolute byte offset."""
    offsets = []
    for i, (name, size, raw_offset) in enumerate(entries):
        if i == 0:
            # first entry's offset field is not a real offset; its content
            # always starts right after the index
            offsets.append(index_size)
        else:
            # raw_offset is an ABSOLUTE offset from the start of the file
            offsets.append(raw_offset)
    return offsets


def extract(arc_path, out_dir):
    with open(arc_path, "rb") as f:
        data = f.read()

    entries, index_size = parse_index(data)
    if not entries:
        raise ValueError("No valid-looking index entries found at the start of this file")

    offsets = resolve_offsets(entries, index_size)

    os.makedirs(out_dir, exist_ok=True)

    total_size = len(data)
    last_end = 0
    for (name, size, _raw), offset in zip(entries, offsets):
        end = offset + size
        if end > total_size:
            print(f"WARNING: '{name}' would read past end of file "
                  f"(offset={offset}, size={size}, file size={total_size}) - skipping")
            continue
        chunk = data[offset:end]
        safe_name = os.path.basename(name.replace("\\", "/")) or f"unnamed_{offset:08x}"
        with open(os.path.join(out_dir, safe_name), "wb") as out_f:
            out_f.write(chunk)
        print(f"extracted {name!r} ({size} bytes, offset {offset}) -> {safe_name}")
        last_end = max(last_end, end)

    # recover any undeclared trailing data (seen in the sample file)
    if last_end < total_size:
        trailing = data[last_end:total_size]
        # skip a single leading null separator if present
        if trailing[:1] == b"\x00":
            trailing = trailing[1:]
        trailing_path = os.path.join(out_dir, "_trailing_chunk.bin")
        with open(trailing_path, "wb") as out_f:
            out_f.write(trailing)
        print(f"\nNOTE: found {len(trailing)} bytes of undeclared trailing data "
              f"(not listed in the index) -> _trailing_chunk.bin")
        print("Preview:", trailing[:80])

    print(f"\nDone. {len(entries)} indexed file(s) processed, output in '{out_dir}'.")


def list_archive(arc_path):
    with open(arc_path, "rb") as f:
        data = f.read()
    entries, index_size = parse_index(data)
    offsets = resolve_offsets(entries, index_size)
    for (name, size, raw), offset in zip(entries, offsets):
        print(f"{name:<28} size={size:<10} offset={offset}")
    print(f"\n{len(entries)} entries, index ends at byte {index_size}, file size {len(data)}")


def pack(manifest_entries, out_path):
    """Rebuild the .arc from a list of (name, content_bytes), in the exact
    original order, plus one entry with name=None holding the trailing
    chunk's bytes. Recomputes every offset from scratch (so edited files
    of different lengths are handled correctly) and patches the hidden
    8-byte pointer embedded in the first file's content so it keeps
    pointing at the trailing chunk's new position/size.
    """
    trailing = None
    real_entries = []
    for name, content in manifest_entries:
        if name is None:
            trailing = content
        else:
            real_entries.append((name, content))
    manifest_entries = real_entries
    n = len(manifest_entries)
    index_size = n * ENTRY_SIZE

    offsets = []
    cursor = index_size
    for name, content in manifest_entries:
        offsets.append(cursor)
        cursor += len(content)
    trailing_offset = cursor

    if trailing is not None and manifest_entries:
        first_name, first_content = manifest_entries[0]
        if len(first_content) < 8:
            raise ValueError(
                f"First file '{first_name}' is under 8 bytes - can't patch the "
                f"embedded trailing-chunk pointer. Something is wrong with this file."
            )
        patched_header = struct.pack("<II", len(trailing), trailing_offset)
        first_content = patched_header + first_content[8:]
        manifest_entries[0] = (first_name, first_content)

    with open(out_path, "wb") as f:
        # index
        for i, ((name, content), offset) in enumerate(zip(manifest_entries, offsets)):
            name_bytes = name.encode("ascii")
            if len(name_bytes) >= NAME_FIELD_SIZE:
                raise ValueError(f"Filename '{name}' too long for the 64-byte name field")
            name_field = name_bytes + b"\x00" + bytes([NAME_PAD_BYTE]) * (NAME_FIELD_SIZE - len(name_bytes) - 1)
            offset_field = n if i == 0 else offset  # entry0's offset slot holds the file count
            f.write(struct.pack("<II", len(content), offset_field))
            f.write(name_field)
        # data
        for name, content in manifest_entries:
            f.write(content)
        if trailing is not None:
            f.write(trailing)

    print(f"Packed {n} file(s) + trailing chunk ({len(trailing) if trailing else 0} bytes) "
          f"into '{out_path}' ({os.path.getsize(out_path)} bytes total).")


def pack_from_dir(in_dir, order_arc_path, out_path, encoding="shift_jis"):
    """Convenience wrapper: read the original .arc just to recover the file
    order and the trailing chunk, then read replacement content for each
    named file from in_dir (falling back to the original if a file is
    missing from in_dir), and pack.
    encoding: the text encoding your edited .txt files are saved in
    ("shift_jis" if you kept them as-is, "utf-8" if you converted them).
    """
    with open(order_arc_path, "rb") as f:
        orig_data = f.read()
    entries, index_size = parse_index(orig_data)
    offsets = resolve_offsets(entries, index_size)

    manifest = []
    for (name, size, _raw), offset in zip(entries, offsets):
        edited_path = os.path.join(in_dir, name)
        if os.path.exists(edited_path):
            with open(edited_path, "rb") as ef:
                raw = ef.read()
            if encoding.lower() != "shift_jis":
                if manifest == []:  # this is entry 0
                    prefix, rest = raw[:8], raw[8:]
                    text = rest.decode(encoding)
                    raw = prefix + text.encode("shift_jis")
                else:
                    text = raw.decode(encoding)
                    raw = text.encode("shift_jis")
            content = raw
        else:
            end = offset + size
            content = orig_data[offset:end]
        manifest.append((name, content))

    total_size = len(orig_data)
    last_name, last_size, _ = entries[-1]
    last_offset = offsets[-1]
    trailing_start = last_offset + last_size
    trailing = orig_data[trailing_start:total_size]
    if trailing[:1] == b"\x00":
        trailing = trailing[1:]
    trailing_edit_path = os.path.join(in_dir, "_trailing_chunk.bin")
    if os.path.exists(trailing_edit_path):
        with open(trailing_edit_path, "rb") as tf:
            trailing = tf.read()
    manifest.append((None, trailing))

    pack(manifest, out_path)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    arc_path = sys.argv[2]

    if command == "extract":
        out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.splitext(os.path.basename(arc_path))[0] + "_extracted"
        extract(arc_path, out_dir)
    elif command == "list":
        list_archive(arc_path)
    elif command == "pack":
        # python3 custom_arc.py pack <edited_dir> <original.arc> <output.arc> [encoding]
        if len(sys.argv) < 5:
            print("Usage: python3 custom_arc.py pack <edited_dir> <original.arc> <output.arc> [shift_jis|utf-8]")
            sys.exit(1)
        edited_dir = sys.argv[2]
        original_arc = sys.argv[3]
        output_arc = sys.argv[4]
        encoding = sys.argv[5] if len(sys.argv) > 5 else "shift_jis"
        pack_from_dir(edited_dir, original_arc, output_arc, encoding)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
