#!/usr/bin/env python3
"""
align_apply.py - takes your reviewed review.tsv (from align_extract.py,
with the english_draft column corrected/approved) plus its manifest.json,
and writes new translated Switch .txt files with each Japanese dialogue
string replaced by its English counterpart - ready for custom_arc.py pack.

Rows with an empty english_draft are skipped (original Japanese kept
untouched for that line) - use this to leave drifted/misaligned rows
alone rather than force a bad substitution.

Usage:
    python3 align_apply.py review.tsv manifest.json --out-dir translated/
"""

import argparse
import csv
import json
import os


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("review_tsv")
    ap.add_argument("manifest_json")
    ap.add_argument("--out-dir", default="translated_switch")
    args = ap.parse_args()

    with open(args.manifest_json, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    rows = []
    with open(args.review_tsv, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)

    if len(rows) != len(manifest):
        print(f"WARNING: review.tsv has {len(rows)} rows but manifest.json has "
              f"{len(manifest)} entries - did you add/remove rows? Proceeding "
              f"with min(len) to stay safe.")

    n = min(len(rows), len(manifest))

    # group replacements by source file, so we can rewrite each file once
    by_file = {}
    for i in range(n):
        entry = manifest[i]
        english = rows[i]["english_draft"].strip()
        if not english:
            continue  # skipped row - leave original text
        by_file.setdefault(entry["file"], []).append((entry["start"], entry["end"], english))

    os.makedirs(args.out_dir, exist_ok=True)
    total_replacements = 0

    for path, replacements in by_file.items():
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("shift_jis", errors="replace")

        # apply from the END of the file backward so earlier byte offsets
        # stay valid as we go
        replacements.sort(key=lambda r: r[0], reverse=True)
        for start, end, english in replacements:
            text = text[:start] + english + text[end:]
            total_replacements += 1

        out_name = os.path.basename(path)
        out_path = os.path.join(args.out_dir, out_name)
        with open(out_path, "wb") as f:
            f.write(text.encode("shift_jis"))
        print(f"{out_name}: applied {len(replacements)} replacement(s) -> {out_path}")

    print(f"\nDone. {total_replacements} line(s) translated across {len(by_file)} file(s), "
          f"output in '{args.out_dir}'.")
    print("Any files from your --switch list that had ALL rows skipped won't "
          "appear here - copy those over from script_extracted/ unchanged "
          "before packing.")


if __name__ == "__main__":
    main()