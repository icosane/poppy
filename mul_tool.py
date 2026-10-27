#!/usr/bin/env python3
"""
mul_tool.py - extract / rebuild the system text tables system_mes.mul and sysgra_mes.mul.

FORMAT (verified: an untouched rebuild is byte-identical for both files):
    48-byte header = 12 x uint32: [ (groups<<8)|4 , record_count , group sizes... (zero padded) ]
        the low byte 4 = number of languages, the high byte = number of groups
        group sizes are counts of MESSAGES; record_count = 4 * sum(group sizes)
    record table : record_count x (uint32 offset, uint32 length), offsets relative to the text area
    text area    : UTF-8 strings packed back to back, no terminators (starts at 48 + 8*record_count)
    Every message = 4 consecutive records in the order  Japanese, English, Simplified Chinese, Traditional Chinese.
    "#n" inside a string is the engine's line break code.

Usage:
    python3 mul_tool.py extract system_mes.mul system_mes.tsv
    python3 mul_tool.py build   system_mes.tsv system_mes.mul --like original_system_mes.mul [--force-english]
    python3 mul_tool.py verify  system_mes.mul        (extract -> build in memory -> must be identical)

extract writes one row per message: idx, group, jp, en, zh_hans, zh_hant, status
    status "EN=JP" means the English column is still Japanese (needs translating).
--force-english on build copies the English column into all four languages, so the menus are English
whatever language the game is set to.
"""
import re
import struct
import sys

JP_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
LANGS = 4


def parse(data):
    hdr = list(struct.unpack_from("<12I", data, 0))
    n = hdr[1]
    recs = [struct.unpack_from("<II", data, 48 + 8 * i) for i in range(n)]
    base = 48 + 8 * n
    strs = [data[base + o: base + o + l].decode("utf-8") for o, l in recs]
    groups = [g for g in hdr[2:] if g]
    if (hdr[0] & 0xFF) != LANGS or n != LANGS * sum(groups):
        raise ValueError("header does not match the expected 4-language layout")
    return hdr, groups, strs


def build(hdr, strs):
    n = len(strs)
    if n != hdr[1]:
        raise ValueError(f"expected {hdr[1]} strings, got {n}")
    blobs = [s.encode("utf-8") for s in strs]
    recs, off = [], 0
    for b in blobs:
        recs.append((off, len(b)))
        off += len(b)
    out = bytearray(struct.pack("<12I", *hdr))
    for o, l in recs:
        out += struct.pack("<II", o, l)
    for b in blobs:
        out += b
    return bytes(out)


def cmd_extract(mul, tsv):
    hdr, groups, strs = parse(open(mul, "rb").read())
    with open(tsv, "w", encoding="utf-8", newline="") as f:
        f.write("idx\tgroup\tjp\ten\tzh_hans\tzh_hant\tstatus\n")
        idx = 0
        for g, size in enumerate(groups):
            for _ in range(size):
                jp, en, zs, zt = strs[idx * 4: idx * 4 + 4]
                for s in (jp, en, zs, zt):
                    if "\t" in s or "\n" in s or "\r" in s:
                        raise ValueError(f"message {idx} contains a tab/newline; unsupported")
                status = "EN=JP" if JP_CHARS.search(en) else ""
                f.write(f"{idx}\t{g}\t{jp}\t{en}\t{zs}\t{zt}\t{status}\n")
                idx += 1
    todo = sum(1 for l in open(tsv, encoding="utf-8").read().split("\n")[1:] if l.endswith("\tEN=JP"))
    print(f"{idx} messages in {len(groups)} groups -> {tsv}  ({todo} still Japanese in the English column)")


def read_tsv(tsv):
    rows = []
    for l in open(tsv, encoding="utf-8-sig").read().replace("\r\n", "\n").split("\n")[1:]:
        if not l.strip():
            continue
        c = l.split("\t")
        c += [""] * (7 - len(c))
        rows.append(c)
    return rows


def cmd_build(tsv, out, like, force_english):
    hdr, groups, _ = parse(open(like, "rb").read())
    rows = read_tsv(tsv)
    if len(rows) != sum(groups):
        raise ValueError(f"{tsv} has {len(rows)} messages, the original has {sum(groups)}; don't add or remove rows")
    strs = []
    for c in rows:
        jp, en, zs, zt = c[2], c[3], c[4], c[5]
        strs += [en, en, en, en] if force_english else [jp, en, zs, zt]
    data = build(hdr, strs)
    open(out, "wb").write(data)
    print(f"wrote {out} ({len(data)} bytes, {len(rows)} messages{', English in every language slot' if force_english else ''})")


def cmd_verify(mul):
    data = open(mul, "rb").read()
    hdr, groups, strs = parse(data)
    ok = build(hdr, strs) == data
    print(f"{mul}: {len(strs)//4} messages, groups {groups} -> rebuild {'IDENTICAL' if ok else 'DIFFERENT'}")
    sys.exit(0 if ok else 1)


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    force = "--force-english" in sys.argv
    like = None
    if "--like" in sys.argv:
        like = sys.argv[sys.argv.index("--like") + 1]
        a = [x for x in a if x != like]
    if not a or a[0] not in ("extract", "build", "verify") or len(a) < 2:
        print(__doc__); sys.exit(1)
    if a[0] == "extract" and len(a) >= 3:
        cmd_extract(a[1], a[2])
    elif a[0] == "build" and len(a) >= 3 and like:
        cmd_build(a[1], a[2], like, force)
    elif a[0] == "verify":
        cmd_verify(a[1])
    else:
        print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
