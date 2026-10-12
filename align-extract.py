#!/usr/bin/env python3
"""
align_extract.py - draft-align Switch (Japanese, plaintext-tag format)
dialogue against PC (English, decompressed BGI) dialogue by POSITION, for
human review before applying.

WHY POSITIONAL ALIGNMENT: there's no shared ID between the two versions'
script formats, so there's nothing to do a "real" match on other than
order-of-appearance - both versions tell the same story in the same
sequence. This works well over short stretches (verified by hand earlier
in this conversation) but WILL drift out of sync over long stretches,
because the two ports don't split dialogue into the same number of pieces
(e.g. the Switch version may page a long line across two <text> tags where
the PC version keeps it as one string, or vice versa). Treat the output as
a draft to review, not a ready-to-apply patch - hence the two-step
extract -> review -> apply workflow instead of one-shot auto-patching.

STEP 1 (this script): extract + align -> writes:
    - review.tsv     : idx, switch_file, japanese, english_draft
                       (edit the english_draft column by hand as needed;
                       leave a row's english_draft EMPTY to skip it and
                       leave the original Japanese untouched)
    - manifest.json  : internal bookkeeping (exact byte spans in each
                       Switch file) so align_apply.py can re-insert
                       correctly. Don't edit this by hand.

STEP 2 (align_apply.py): reads your edited review.tsv + the manifest and
writes new translated Switch .txt files, ready for custom_arc.py pack.

Usage:
    python3 align_extract.py \\
        --switch script_extracted/001_prologue_01.txt script_extracted/002_prologue_02.txt \\
        --pc 001_ex_strings.txt \\
        --out-review review.tsv --out-manifest manifest.json

--pc accepts either a raw decompressed BGI file, OR a strings.txt file
already produced by bgi_strings.py (auto-detected).
"""

import argparse
import json
import re
import sys


TAG_PATTERN = re.compile(r'<text ([^>]+)>|<registertexttohistory NULL,"([^"]*)">')


def extract_switch_dialogue(paths):
    """Returns a list of dicts: {file, start, end, kind, text}, in order,
    across all given files. start/end are byte offsets into that file's
    Shift-JIS-decoded text (so align_apply.py can locate and replace the
    exact same span later)."""
    entries = []
    for path in paths:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("shift_jis", errors="replace")
        for m in TAG_PATTERN.finditer(text):
            if m.group(1) is not None:
                kind, inner = "text", m.group(1)
                inner_start = m.start(1)
                inner_end = m.end(1)
            else:
                kind, inner = "registertexttohistory", m.group(2)
                inner_start = m.start(2)
                inner_end = m.end(2)
            entries.append({
                "file": path,
                "start": inner_start,
                "end": inner_end,
                "kind": kind,
                "text": inner,
            })
    return entries


def is_identifier_like(s):
    """True for things that are clearly NOT dialogue: bare identifiers,
    resource names, file paths - no spaces or punctuation at all."""
    if re.fullmatch(r"[A-Za-z0-9_]+", s):
        return True
    if "\\" in s:
        return True
    return False


def extract_pc_dialogue(paths):
    """Returns a flat list of candidate English dialogue strings, in file
    order, across all given files. Accepts either a raw decompressed BGI
    file or a bgi_strings.py output .txt (auto-detected by trying to
    decode as UTF-8 text first, since bgi_strings.py output is UTF-8
    one-string-per-line, while a raw BGI file starts with a binary
    signature)."""
    out = []
    for path in paths:
        strings = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if content.startswith("BurikoCompiledScriptVer"):
                strings = None  # this is bgi_strings output that happens to
                                 # start with that literal line - fine, treat
                                 # as strings list below
            strings = [line.rstrip("\n") for line in content.split("\n") if line.strip()]
        except UnicodeDecodeError:
            strings = None

        if strings is None:
            # raw decompressed BGI file - do the same extraction
            # bgi_strings.py does
            with open(path, "rb") as f:
                data = f.read()
            strings = []
            for chunk in data.split(b"\x00"):
                if len(chunk) < 4:
                    continue
                try:
                    candidate = chunk.decode("shift_jis")
                except UnicodeDecodeError:
                    continue
                printable = sum(1 for ch in candidate if ch.isprintable() or ch in "\r\n\t")
                if candidate and printable / len(candidate) >= 0.98:
                    strings.append(candidate)

        for s in strings:
            if len(s) >= 2 and not is_identifier_like(s):
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--switch", nargs="+", required=True, help="Switch plaintext .txt files, in story order")
    ap.add_argument("--pc", nargs="+", required=True, help="PC decompressed BGI file(s) or bgi_strings.py output(s), in story order")
    ap.add_argument("--out-review", default="review.tsv")
    ap.add_argument("--out-manifest", default="manifest.json")
    args = ap.parse_args()

    switch_entries = extract_switch_dialogue(args.switch)
    pc_lines = extract_pc_dialogue(args.pc)

    print(f"Switch dialogue lines: {len(switch_entries)}")
    print(f"PC dialogue candidates: {len(pc_lines)}")
    if len(switch_entries) != len(pc_lines):
        print(f"WARNING: counts don't match (diff = {len(switch_entries) - len(pc_lines)}). "
              f"Positional alignment WILL drift somewhere in this range - "
              f"review carefully, especially past the shorter file's line count.")

    n = min(len(switch_entries), len(pc_lines))
    with open(args.out_review, "w", encoding="utf-8") as f:
        f.write("idx\tswitch_file\tjapanese\tenglish_draft\n")
        for i in range(n):
            se = switch_entries[i]
            jp = se["text"].replace("\t", " ")
            en = pc_lines[i].replace("\t", " ").replace("\n", " ")
            f.write(f"{i}\t{se['file']}\t{jp}\t{en}\n")

    with open(args.out_manifest, "w", encoding="utf-8") as f:
        json.dump(switch_entries[:n], f, ensure_ascii=False, indent=1)

    print(f"\nWrote {n} aligned row(s) to '{args.out_review}' for review, "
          f"and bookkeeping to '{args.out_manifest}'.")
    print("Open the .tsv in a spreadsheet app (it's tab-separated), scan for "
          "drift/misalignment, fix the english_draft column as needed, then "
          "run align_apply.py on the reviewed file.")


if __name__ == "__main__":
    main()