#!/usr/bin/env python3
"""
ext_tool.py (v2) - convert the game's .ext.gz image assets to PNG and back.

FORMAT (verified on sys_title_00 / sys_title_01 .ext.gz):
    gzip( header 256 bytes + width*height*4 bytes of BGRA pixels, PREMULTIPLIED alpha )
    header (little-endian):
        0   "EXT0"
        4   float32 x offset      8   float32 y offset        (e.g. -5.0, -5.0 on small UI sprites)
        12  uint32 width          16  uint32 height
        20  uint32 width2         24  uint32 height2          (inner/visible size, e.g. 392x1016 in a 400x1024 sprite)
        28  int32 -9999           32  int32 -9999             (unknown; always seen as -9999)
        36  uint32 32             (bits per pixel)
        48  uint32 8, 52 uint32 8, 56 uint32 1   (seen on sprites; unknown meaning)
    The rest of the header is zero.

WHY v1 PACKING FAILED: it wrote a 232-byte header (real: 256, so every pixel shifted 24 bytes), put the
size fields in the wrong place and zeroed the others (bits-per-pixel = 0, -9999 fields = 0), and wrote
straight alpha where the game stores premultiplied alpha. v2 keeps the ORIGINAL header.

Usage:
    python3 ext_tool.py unpack sys_title_01.ext.gz              -> sys_title_01.png + sys_title_01.ext.hdr
    python3 ext_tool.py pack   sys_title_01.png                 -> sys_title_01.ext.gz  (uses sys_title_01.ext.hdr)
    python3 ext_tool.py pack   new.png out.ext.gz --template sys_title_01.ext.gz   (borrow a header)
    python3 ext_tool.py verify sys_title_01.ext.gz              (unpack -> pack -> compare)
    python3 ext_tool.py info   file.ext.gz
Options: --raw  keep the pixel bytes exactly as stored (no alpha conversion; edit-unfriendly but lossless).
Needs Pillow and numpy:  pip install pillow numpy
"""
import gzip
import os
import struct
import sys

import numpy as np
from PIL import Image

MAGIC = b"EXT0"
HEADER_SIZE = 256


def read_ext(path):
    d = gzip.open(path, "rb").read() if path.lower().endswith(".gz") else open(path, "rb").read()
    if d[:4] != MAGIC:
        raise ValueError(f"{path}: not an EXT0 image (magic {d[:4]!r})")
    w, h = struct.unpack_from("<II", d, 12)
    hdr_len = len(d) - w * h * 4
    if hdr_len < 40:
        raise ValueError(f"{path}: size does not fit {w}x{h} BGRA (header would be {hdr_len} bytes)")
    return d[:hdr_len], d[hdr_len:], w, h


def describe(hdr):
    fx, fy = struct.unpack_from("<ff", hdr, 4)
    w, h, w2, h2 = struct.unpack_from("<IIII", hdr, 12)
    a, b, bpp = struct.unpack_from("<iiI", hdr, 28)
    extra = struct.unpack_from("<III", hdr, 48)
    return (f"header {len(hdr)} bytes | size {w}x{h} | inner {w2}x{h2} | offset ({fx:g}, {fy:g}) | "
            f"fields {a},{b} | bpp {bpp} | extra {extra}")


def default_header(w, h):
    hdr = bytearray(HEADER_SIZE)
    hdr[0:4] = MAGIC
    struct.pack_into("<IIII", hdr, 12, w, h, w, h)
    struct.pack_into("<iiI", hdr, 28, -9999, -9999, 32)
    return bytes(hdr)


def bgra_to_png_array(pix, w, h, raw):
    a = np.frombuffer(pix, dtype=np.uint8).reshape(h, w, 4).copy()
    b, g, r, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    rgba = np.stack([r, g, b, al], axis=-1)
    if not raw:
        m = al > 0
        for c in range(3):
            ch = rgba[..., c].astype(np.uint32)
            ch[m] = np.minimum(255, (ch[m] * 255 + al[m] // 2) // al[m])
            ch[~m] = 0
            rgba[..., c] = ch.astype(np.uint8)
    return rgba


def png_array_to_bgra(rgba, raw):
    r, g, b, al = (rgba[..., i].astype(np.uint32) for i in range(4))
    if not raw:
        r, g, b = ((c * al + 127) // 255 for c in (r, g, b))
    return np.stack([b, g, r, al], axis=-1).astype(np.uint8).tobytes()


def write_gz(path, payload):
    name = os.path.basename(path)[:-3] if path.lower().endswith(".gz") else os.path.basename(path)
    with open(path, "wb") as f, gzip.GzipFile(filename=name, mode="wb", fileobj=f, compresslevel=9, mtime=0) as gz:
        gz.write(payload)


def cmd_unpack(path, raw=False):
    hdr, pix, w, h = read_ext(path)
    base = path[:-7] if path.lower().endswith(".ext.gz") else os.path.splitext(path)[0]
    Image.fromarray(bgra_to_png_array(pix, w, h, raw), "RGBA").save(base + ".png")
    open(base + ".ext.hdr", "wb").write(hdr)
    print(describe(hdr))
    print(f"wrote {base}.png and {base}.ext.hdr (keep the .hdr next to the PNG: pack uses it)")


def cmd_pack(png, out=None, template=None, raw=False):
    img = Image.open(png).convert("RGBA")
    w, h = img.size
    base = png[:-4] if png.lower().endswith(".png") else png
    out = out or base + ".ext.gz"
    if template:
        hdr = read_ext(template)[0]
    elif os.path.exists(base + ".ext.hdr"):
        hdr = open(base + ".ext.hdr", "rb").read()
    else:
        hdr = default_header(w, h)
        print("WARNING: no original header found (no .ext.hdr, no --template); using a generic one. "
              "Safer: pack with --template <an original .ext.gz of the same kind>.")
    hdr = bytearray(hdr)
    ow, oh, ow2, oh2 = struct.unpack_from("<IIII", hdr, 12)
    if (w, h) != (ow, oh):
        print(f"WARNING: PNG is {w}x{h} but the template header says {ow}x{oh}. The game may expect the original size.")
        struct.pack_into("<II", hdr, 12, w, h)
        struct.pack_into("<II", hdr, 20, w if ow2 == ow else ow2, h if oh2 == oh else oh2)
    payload = bytes(hdr) + png_array_to_bgra(np.asarray(img), raw)
    assert len(payload) == len(hdr) + w * h * 4
    write_gz(out, payload)
    print(f"wrote {out}: {len(payload)} bytes uncompressed ({describe(hdr)})")


def cmd_verify(path, raw=False):
    hdr, pix, w, h = read_ext(path)
    rebuilt = png_array_to_bgra(bgra_to_png_array(pix, w, h, raw), raw)
    diff = np.abs(np.frombuffer(pix, np.uint8).astype(int) - np.frombuffer(rebuilt, np.uint8).astype(int))
    print(describe(hdr))
    print(f"unpack -> pack: {w*h*4} pixel bytes, differing bytes: {int((diff > 0).sum())}, max difference: {int(diff.max())}"
          + ("   => lossless" if diff.max() == 0 else "   (premultiply rounding only)" if diff.max() <= 2 else "   !!! check"))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    raw = "--raw" in sys.argv
    tmpl = None
    if "--template" in sys.argv:
        i = sys.argv.index("--template")
        tmpl = sys.argv[i + 1]
        a = [x for x in a if x != tmpl]
    if len(a) < 2 or a[0] not in ("unpack", "pack", "verify", "info"):
        print(__doc__)
        sys.exit(1)
    if a[0] == "unpack":
        cmd_unpack(a[1], raw)
    elif a[0] == "pack":
        cmd_pack(a[1], a[2] if len(a) > 2 else None, tmpl, raw)
    elif a[0] == "verify":
        cmd_verify(a[1], raw)
    else:
        print(describe(read_ext(a[1])[0]))


if __name__ == "__main__":
    main()
