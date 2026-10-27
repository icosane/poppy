#!/usr/bin/env python3
"""
find_text.py - search a whole folder (e.g. the full romfs dump) for a string, in every plausible encoding.

Used to answer "where does this text on screen come from?". It looks for the string as Shift-JIS (cp932), UTF-8,
UTF-16 (both byte orders), and also inside .gz files (the game stores fonts/images as .gz).

Usage:
    python3 find_text.py <folder> <text> [<text> ...]
    python3 find_text.py romfs_dump プロローグ
Prints file, encoding, number of hits and a bit of context for the first hit.
(Text packed inside archives such as script.arc is found only after you extract the archive first.)
"""
import gzip
import os
import sys

ENCODINGS = ("cp932", "utf-8", "utf-16le", "utf-16be")
MAX_FILE = 600 * 1024 * 1024


def search(label, data, needles, out):
    for text in needles:
        for enc in ENCODINGS:
            try:
                nd = text.encode(enc)
            except UnicodeEncodeError:
                continue
            c = data.count(nd)
            if c:
                i = data.find(nd)
                ctx = data[max(0, i - 24): i + len(nd) + 40].decode(enc, errors="replace").replace("\r", " ").replace("\n", " ")
                out.append((label, enc, c, i, ctx))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    root, needles = sys.argv[1], sys.argv[2:]
    hits, scanned = [], 0
    for dirpath, _, files in os.walk(root):
        for fn in sorted(files):
            p = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(p) > MAX_FILE:
                    print("skipped (too large):", p)
                    continue
                data = open(p, "rb").read()
            except OSError:
                continue
            scanned += 1
            search(p, data, needles, hits)
            if data[:2] == b"\x1f\x8b":
                try:
                    search(p + "  (inside gzip)", gzip.decompress(data), needles, hits)
                except Exception:
                    pass
    print(f"scanned {scanned} file(s) for {needles}")
    if not hits:
        print("no hits. The text is not stored as plain text in these files (it may be in an archive you haven't "
              "extracted, in the game executable, or built from pieces).")
    for label, enc, c, i, ctx in hits[:60]:
        print(f"{label}\n    {enc}: {c} hit(s), first at byte {i}: ...{ctx}...")


if __name__ == "__main__":
    main()
