#!/usr/bin/env python3
"""Post-process extracted Switch scripts for English font sizes and speaker names.

Reads/writes cp932 (the encoding used by Switch script.arc). By default the name
map is name_map.tsv next to this script. Only <name ...> tag values are mapped;
protagonist placeholders are replaced wherever they occur in script text.

Usage:
    python3 script_postprocess.py --src-dir script_en --out-dir script_ready
    python3 script_postprocess.py --src-dir script_en --out-dir script_en --in-place
"""
import argparse
import os
import re
import shutil

ENC = "cp932"
FONT_SIZES = {"33": "30", "45": "43"}
FONT_RE = re.compile(rb"<font size:(\d+)")
NAME_TAG_RE = re.compile(r"(<name\s+)([^>]+)(>)")


def read_name_map(path):
    mapping = {}
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line or line.lstrip().startswith("#"):
                continue
            cells = line.split("\t", 1)
            if len(cells) != 2 or not cells[0]:
                raise ValueError(f"{path}:{line_no}: expected Japanese<TAB>English")
            mapping[cells[0]] = cells[1]
    return mapping


def transform(data, mapping):
    # Font tags are ASCII bytes, so changing them at byte level preserves all
    # other original bytes and avoids accidental encoding/newline changes.
    font_counts = {old: 0 for old in FONT_SIZES}
    def font_sub(m):
        old = m.group(1).decode("ascii")
        if old not in FONT_SIZES:
            return m.group(0)
        font_counts[old] += 1
        return b"<font size:" + FONT_SIZES[old].encode("ascii")
    data = FONT_RE.sub(font_sub, data)

    text = data.decode(ENC)
    name_counts = {jp: 0 for jp in mapping if jp not in ("主人公（名）", "主人公（姓）")}
    placeholder_counts = {jp: 0 for jp in mapping if jp in ("主人公（名）", "主人公（姓）")}

    def name_sub(m):
        old = m.group(2)
        new = mapping.get(old, old)
        if new != old and old in name_counts:
            name_counts[old] += 1
        return m.group(1) + new + m.group(3)
    text = NAME_TAG_RE.sub(name_sub, text)

    # Placeholder tokens can also occur inside text/history strings.
    for jp in placeholder_counts:
        en = mapping[jp]
        count = text.count(jp)
        placeholder_counts[jp] += count
        text = text.replace(jp, en)

    return text.encode(ENC), font_counts, name_counts, placeholder_counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-dir", required=True, help="directory containing extracted Switch scripts")
    ap.add_argument("--out-dir", help="output directory; defaults to in-place only with --in-place")
    ap.add_argument("--name-map", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "name_map.tsv"))
    ap.add_argument("--in-place", action="store_true", help="modify files in --src-dir directly")
    a = ap.parse_args()
    if a.in_place and a.out_dir and os.path.abspath(a.out_dir) != os.path.abspath(a.src_dir):
        ap.error("--in-place cannot be combined with a different --out-dir")
    if not a.in_place and not a.out_dir:
        ap.error("provide --out-dir or use --in-place")

    src = os.path.abspath(a.src_dir)
    out = src if a.in_place else os.path.abspath(a.out_dir)
    if not os.path.isdir(src):
        ap.error(f"source directory not found: {src}")
    if src != out:
        if os.path.exists(out):
            shutil.rmtree(out)
        shutil.copytree(src, out)

    mapping = read_name_map(a.name_map)
    totals_font = {old: 0 for old in FONT_SIZES}
    totals_names = {jp: 0 for jp in mapping if jp not in ("主人公（名）", "主人公（姓）")}
    totals_placeholders = {jp: 0 for jp in mapping if jp in ("主人公（名）", "主人公（姓）")}
    files_changed = 0
    for root, _, files in os.walk(out):
        for filename in sorted(files):
            if not filename.lower().endswith(".txt"):
                continue
            path = os.path.join(root, filename)
            with open(path, "rb") as f:
                original = f.read()
            updated, fonts, names, placeholders = transform(original, mapping)
            if updated != original:
                with open(path, "wb") as f:
                    f.write(updated)
                files_changed += 1
            for k, v in fonts.items(): totals_font[k] += v
            for k, v in names.items(): totals_names[k] += v
            for k, v in placeholders.items(): totals_placeholders[k] += v

    print(f"Processed {files_changed} changed .txt file(s) in {out}")
    print("Font size replacements: " + ", ".join(f"{k}->{FONT_SIZES[k]}: {v}" for k, v in totals_font.items()))
    print("Speaker-name tag replacements: " + ", ".join(f"{k}->{mapping[k]}: {n}" for k, n in totals_names.items()))
    print("Placeholder replacements: " + ", ".join(f"{k}->{mapping[k]}: {n}" for k, n in totals_placeholders.items()))


if __name__ == "__main__":
    main()
