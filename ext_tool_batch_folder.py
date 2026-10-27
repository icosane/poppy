#!/usr/bin/env python3
"""
ext_tool.py (v4) - convert the game's .ext.gz image assets to PNG and back with Batch Support.

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

Usage:
    python3 ext_tool.py unpack *.ext.gz --out-dir extracted_pngs
    python3 ext_tool.py pack   *.png    --out-dir packed_exts
    
    python3 ext_tool.py unpack sys_title_01.ext.gz --out-dir out_folder
    python3 ext_tool.py pack   sys_title_01.png    --out-dir out_folder
    python3 ext_tool.py pack   new.png out.ext.gz  --template sys_title_01.ext.gz
Options: 
    --raw      keep the pixel bytes exactly as stored (no alpha conversion; edit-unfriendly but lossless).
    --out-dir  specify a custom directory folder to write output files to.
Needs Pillow and numpy:  pip install pillow numpy
"""
import glob
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


def cmd_unpack(path, out_dir=None, raw=False):
    hdr, pix, w, h = read_ext(path)
    base_name = path[:-7] if path.lower().endswith(".ext.gz") else os.path.splitext(path)[0]
    base_name = os.path.basename(base_name)
    
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        dest_png = os.path.join(out_dir, base_name + ".png")
        dest_hdr = os.path.join(out_dir, base_name + ".ext.hdr")
    else:
        dest_png = base_name + ".png"
        dest_hdr = base_name + ".ext.hdr"

    Image.fromarray(bgra_to_png_array(pix, w, h, raw), "RGBA").save(dest_png)
    open(dest_hdr, "wb").write(hdr)
    print(f"[{os.path.basename(path)}] {describe(hdr)}")
    print(f" -> Wrote {dest_png} and {dest_hdr}")


def cmd_pack(png, out_path=None, out_dir=None, template=None, raw=False):
    img = Image.open(png).convert("RGBA")
    w, h = img.size
    
    base_no_ext = png[:-4] if png.lower().endswith(".png") else png
    base_name = os.path.basename(base_no_ext)
    
    # Locate header file (check original directory next to PNG, then check custom input dir)
    hdr_path = base_no_ext + ".ext.hdr"
    if not os.path.exists(hdr_path) and out_dir:
        hdr_path = os.path.join(out_dir, base_name + ".ext.hdr")

    if template:
        hdr = read_ext(template)[0]
    elif os.path.exists(hdr_path):
        hdr = open(hdr_path, "rb").read()
    else:
        hdr = default_header(w, h)
        print(f"WARNING [{png}]: no original header found; using a generic one.")
        
    hdr = bytearray(hdr)
    ow, oh, ow2, oh2 = struct.unpack_from("<IIII", hdr, 12)
    if (w, h) != (ow, oh):
        print(f"WARNING [{png}]: PNG is {w}x{h} but the template header says {ow}x{oh}.")
        struct.pack_into("<II", hdr, 12, w, h)
        struct.pack_into("<II", hdr, 20, w if ow2 == ow else ow2, h if oh2 == oh else oh2)
        
    payload = bytes(hdr) + png_array_to_bgra(np.asarray(img), raw)
    assert len(payload) == len(hdr) + w * h * 4
    
    if out_path:
        final_out = out_path
    elif out_dir:
        os.makedirs(out_dir, exist_ok=True)
        final_out = os.path.join(out_dir, base_name + ".ext.gz")
    else:
        final_out = base_no_ext + ".ext.gz"

    write_gz(final_out, payload)
    print(f" -> Wrote {final_out}: {len(payload)} bytes uncompressed")


def cmd_verify(path, raw=False):
    hdr, pix, w, h = read_ext(path)
    rebuilt = png_array_to_bgra(bgra_to_png_array(pix, w, h, raw), raw)
    diff = np.abs(np.frombuffer(pix, np.uint8).astype(int) - np.frombuffer(rebuilt, np.uint8).astype(int))
    print(f"[{os.path.basename(path)}] {describe(hdr)}")
    print(f"    unpack -> pack verification: Max diff: {int(diff.max())}" + 
          (" (lossless)" if diff.max() == 0 else " (premultiply rounding limit)" if diff.max() <= 2 else " !!! WARNING"))


def resolve_files(patterns):
    resolved = []
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            resolved.extend(matches)
        else:
            resolved.append(pat)
    return sorted(list(set(resolved)))


def main():
    raw = "--raw" in sys.argv
    
    tmpl = None
    if "--template" in sys.argv:
        i = sys.argv.index("--template")
        if i + 1 < len(sys.argv):
            tmpl = sys.argv[i + 1]
            
    out_dir = None
    if "--out-dir" in sys.argv:
        i = sys.argv.index("--out-dir")
        if i + 1 < len(sys.argv):
            out_dir = sys.argv[i + 1]

    # Clean flags and argument parameter values out of clean_args list
    banned = ("--raw", "--template", tmpl, "--out-dir", out_dir)
    clean_args = [x for x in sys.argv[1:] if x not in banned]
    
    if len(clean_args) < 2:
        print(__doc__)
        sys.exit(1)
        
    mode = clean_args[0]
    file_targets = resolve_files(clean_args[1:])

    if mode not in ("unpack", "pack", "verify", "info"):
        print(__doc__)
        sys.exit(1)

    print(f"Executing '{mode}' command block across {len(file_targets)} target asset file(s)...")

    for idx, target in enumerate(file_targets, start=1):
        if not os.path.exists(target):
            print(f" [{idx}/{len(file_targets)}] File not found: {target}")
            continue

        try:
            if mode == "unpack":
                cmd_unpack(target, out_dir, raw)
            elif mode == "pack":
                # Handle single file explicit layout renaming vs generic directory dumps
                out_path = clean_args[2] if (len(clean_args) == 3 and len(file_targets) == 1) else None
                cmd_pack(target, out_path, out_dir, tmpl, raw)
            elif mode == "verify":
                cmd_verify(target, raw)
            elif mode == "info":
                print(f"[{os.path.basename(target)}] {describe(read_ext(target))}")
        except Exception as e:
            print(f" [ERROR] Failed processing {target}: {e}")


if __name__ == "__main__":
    main()
