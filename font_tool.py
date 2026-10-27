#!/usr/bin/env python3
"""
font_tool.py - inspect and patch the game's font (font_00.ttf.gz on the Switch: Noto Sans JP Medium).

narrow-comma   remap the full-width comma U+FF0C to the font's ordinary comma glyph. The engine drops ASCII
               commas from <text> lines, so we write ， instead; in this font ， is a full 1.00 em wide (a normal
               comma is 0.30 em), which looks like a hole in the sentence. After this patch ，  looks and spaces
               exactly like a normal comma, so script_postprocess.py --comma fullwidth gives natural text.
               Only the cmap changes; no glyph outlines or metrics are edited.

Usage:
    python3 font_tool.py info          font_00.ttf.gz
    python3 font_tool.py narrow-comma  font_00.ttf.gz  font_00_patched.ttf.gz
Put the patched file where the original lives (same name, e.g. via LayeredFS romfs). Not tested in-game.
Needs fontTools:  pip install fonttools
"""
import gzip
import io
import os
import sys

from fontTools.ttLib import TTFont


def load(path):
    raw = gzip.open(path, "rb").read() if path.lower().endswith(".gz") else open(path, "rb").read()
    return TTFont(io.BytesIO(raw)), len(raw)


def cmd_info(path):
    f, n = load(path)
    cmap = f.getBestCmap()
    hm, upm = f["hmtx"], f["head"].unitsPerEm
    print(f"{f['name'].getDebugName(4)} | {n} bytes | {f['maxp'].numGlyphs} glyphs | {len(cmap)} characters | {upm} units/em")
    for label, cp in (("ASCII comma ,", 0x2C), ("half-width comma ､", 0xFF64), ("full-width comma ，", 0xFF0C),
                      ("ideographic comma 、", 0x3001), ("space", 0x20), ("letter a", 0x61)):
        g = cmap.get(cp)
        print(f"  {label:<24} -> glyph {g!s:<10} advance {hm[g][0] / upm:.2f} em" if g else f"  {label:<24} MISSING")


def cmd_narrow(src, dst):
    f, _ = load(src)
    comma = f.getBestCmap()[0x2C]
    n = 0
    for t in f["cmap"].tables:
        if 0xFF0C in t.cmap:
            t.cmap[0xFF0C] = comma
            n += 1
    buf = io.BytesIO()
    f.save(buf)
    data = buf.getvalue()
    if dst.lower().endswith(".gz"):
        with open(dst, "wb") as out, gzip.GzipFile(filename=os.path.basename(dst)[:-3], mode="wb", fileobj=out,
                                                   compresslevel=9, mtime=0) as gz:
            gz.write(data)
    else:
        open(dst, "wb").write(data)
    print(f"remapped U+FF0C to glyph '{comma}' in {n} cmap subtable(s) -> {dst} ({len(data)} bytes uncompressed)")


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "info":
        cmd_info(a[1])
    elif len(a) == 3 and a[0] == "narrow-comma":
        cmd_narrow(a[1], a[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
