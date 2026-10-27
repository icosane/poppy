#!/usr/bin/env python3
"""Remove unsupported italic markup from plaintext-tag Switch script files.

The contents between the tags are preserved. Both normal forms (<i>, </i>)
and malformed PC-style forms (<i), </i)) are removed, because the latter
were found in the translated script data and did not render correctly in-game.

Usage:
    python strip_italic_tags.py INPUT_DIR OUTPUT_DIR

The input directory is not modified. Files and subdirectories are copied to
OUTPUT_DIR; only matching tags in .txt files are changed.
"""
import argparse
from pathlib import Path
import re
import shutil

# Handles <i>, </i>, <i), and </i), case-insensitively.
ITALIC_TAG = re.compile(rb"</?i[)>]", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_dir", type=Path, help="directory containing translated script files")
    parser.add_argument("output_dir", type=Path, help="destination directory; must not be inside input_dir")
    args = parser.parse_args()

    source = args.input_dir.resolve()
    destination = args.output_dir.resolve()
    if not source.is_dir():
        parser.error(f"input directory does not exist: {source}")
    if source == destination or source in destination.parents:
        parser.error("output directory must be separate from and outside the input directory")
    if destination.exists() and any(destination.iterdir()):
        parser.error(f"output directory is not empty: {destination}")

    destination.mkdir(parents=True, exist_ok=True)
    files = removed_open = removed_close = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        if path.suffix.lower() == ".txt":
            removed_open += len(re.findall(rb"<i[)>]", data, re.IGNORECASE))
            removed_close += len(re.findall(rb"</i[)>]", data, re.IGNORECASE))
            data = ITALIC_TAG.sub(b"", data)
        target.write_bytes(data)
        files += 1

    print(f"Copied {files} file(s) to {destination}.")
    print(f"Removed {removed_open} opening and {removed_close} closing italic tag(s). Text was preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
