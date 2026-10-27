#!/usr/bin/env python3
"""
make_text_test.py - find out, in one in-game test, how the Switch engine treats commas and quotes in <text ...>.

It replaces the first 8 normal-size <text> lines of 001_prologue_01.txt with labelled variants A-H, so you can
start a new game, click through the prologue and look at what each variant looks like:

  A  plain ASCII commas              (expected: commas disappear - that's the bug you saw)
  B  full-width comma  ，             (expected: visible, with extra space after it)
  C  half-width ideographic comma ､   (small comma-like mark)
  D  backslash-escaped  \\,           (shows either a comma or a backslash)
  E  the whole line in ASCII quotes   (do the quotes show? do the commas survive?)
  F  curly quotes “ ”
  G  corner brackets 「 」             (the game's own speech brackets - always safe)
  H  odd characters: ' " : ; % & # /

Then choose:  script_postprocess.py --comma  fullwidth | halfwidth | backslash | quote | keep
              align_apply.py --quote-style   none | ascii | curly | corner

Usage:
    python3 make_text_test.py --src-dir script_jp --out-dir script_texttest
    python3 custom_arc.py pack script_texttest script_text_test.arc
"""
import argparse
import os
import shutil

ENC = "cp932"
VARIANTS = [
    ("A", "plain ASCII commas", "A) Wait, that's perfect! Hey, mind if I use that later?"),
    ("B", "full-width comma", "B) Wait\uff0c that's perfect! Hey\uff0c mind if I use that later?"),
    ("C", "half-width ideographic comma", "C) Wait\uff64 that's perfect! Hey\uff64 mind if I use that later?"),
    ("D", "backslash-escaped comma", "D) Wait\\, that's perfect! Hey\\, mind if I use that later?"),
    ("E", "whole line in ASCII quotes", '"E) Wait, that\'s perfect! Hey, mind if I use that later?"'),
    ("F", "curly quotes + full-width comma", "\u201cF) Wait\uff0c that's perfect!\u201d"),
    ("G", "corner brackets + full-width comma", "\u300cG) Wait\uff0c that's perfect!\u300d"),
    ("H", "odd characters", "H) Miu's \"best\" friend: 100% sure; really & truly #1 / 2!"),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--file", default="001_prologue_01.txt")
    a = ap.parse_args()
    if os.path.abspath(a.src_dir) != os.path.abspath(a.out_dir):
        if os.path.exists(a.out_dir):
            shutil.rmtree(a.out_dir)
        shutil.copytree(a.src_dir, a.out_dir)
    path = os.path.join(a.out_dir, a.file)
    lines = open(path, "rb").read().split(b"\r\n")
    in_region, todo, key = False, list(VARIANTS), []
    for i, line in enumerate(lines):
        if line.startswith(b"<font"):
            in_region = line.startswith(b"<font size:")
        elif line.startswith(b"<text ") and not in_region and todo:
            label, what, text = todo.pop(0)
            old = line[6:-1].decode(ENC, errors="replace")
            lines[i] = b"<text " + text.encode(ENC) + b">"
            key.append((label, what, old))
        if not todo:
            break
    open(path, "wb").write(b"\r\n".join(lines))
    print(f"wrote {len(key)} test lines into {path}. Order you will meet them in-game (Japanese lines in between are normal):")
    for label, what, old in key:
        print(f"  {label}  {what:<36} (replaced: {old[:24]})")


if __name__ == "__main__":
    main()
