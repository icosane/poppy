#!/usr/bin/env python3
"""
pc_prepare.py - batch helper for the PC (BGI/Ethornell) reference side.

Walks a folder of files extracted with bgi_arc.py, and for every compiled script
(either 'DSC FORMAT 1.00' compressed, or already decompressed
'BurikoCompiledScriptVer1.00') writes <name>_strings.txt: the readable strings,
one per line, ready to feed to align_extract.py --pc.

Usage:
    python3 pc_prepare.py <extracted_dir> <out_dir>

Files that are neither (images, sounds, ...) are skipped silently.
Needs dsc_codec.py and bgi_strings.py in the same folder.
"""
import os
import sys

from dsc_codec import decompress, MAGIC
from bgi_strings import extract_strings

SCRIPT_MAGIC = b"BurikoCompiledScriptVer"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    done = 0
    for root, _, files in os.walk(src):
        for name in sorted(files):
            path = os.path.join(root, name)
            try:
                data = open(path, "rb").read()
            except OSError:
                continue
            if data[:16] == MAGIC:
                try:
                    data = decompress(data)
                except Exception as e:  # keep going on a bad file
                    print(f"SKIP {path}: {e}")
                    continue
            if data[:len(SCRIPT_MAGIC)] != SCRIPT_MAGIC:
                continue
            strings = extract_strings(data)
            target = os.path.join(out, name + "_strings.txt")
            with open(target, "w", encoding="utf-8") as f:
                f.write("\n".join(strings) + "\n")
            print(f"{path}: {len(strings)} strings -> {target}")
            done += 1
    print(f"done: {done} script file(s) processed")


if __name__ == "__main__":
    main()
