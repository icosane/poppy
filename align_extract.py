#!/usr/bin/env python3
"""
align_extract.py - draft-align Switch (Japanese, plaintext-tag scripts) dialogue
against PC (English, strings dumped by bgi_strings.py) dialogue.

Step 1 of 2. Writes review.tsv with columns:
    idx, switch_file, kind, japanese, english_draft, status
You review/fix the english_draft column, then run align_apply.py.

How the matching works (no AI, just heuristics):
  * Switch side: every <text ...> and <registertexttohistory NULL,"..."> string.
  * PC side: the string pool is in order of use but mixed with command names and
    speaker labels, so it is filtered down to real English dialogue (drops
    anything with kana/kanji, anything starting with "PrintMessage", paths,
    bare identifiers like steamacv!acv01 or Protag(First)).
  * Both sides are tagged SPEECH (Switch 「...」 / PC "...") or NARRATION.
  * A gap-tolerant alignment (like diff) pairs them in order: speech only pairs
    with speech, narration with narration, and a length-ratio score plus agreement
    of ? ! … marks breaks ties. A Switch line with no PC counterpart is left BLANK (status NO-MATCH)
    instead of shifting every following line by one.
  * PC placeholders Protag(First)/Protag(Last) become 主人公（名）/主人公（姓）,
    the placeholders the Switch scripts already use.

The PC side may cover MORE story than your Switch files (extra PC lines at the
start/end are skipped for free), but long unrelated stretches in the middle can
still confuse it - align one chapter at a time and skim the status column.

Usage:
    python3 align_extract.py --switch script_jp/001_prologue_01.txt [more files in story order] \\
        --pc 001_prologue_01pc.txt [more] --out-review review.tsv
"""
import argparse
import json
import math
import re

ENC = "cp932"  # superset of Shift-JIS
TAG = re.compile(r'<text ([^>]+)>|<registertexttohistory NULL,"([^"]*)">')
PLACEHOLDERS = {"Protag(First)": "主人公（名）", "Protag(Last)": "主人公（姓）"}


def read_sjis(path):
    with open(path, "rb") as f:
        return f.read().decode(ENC, errors="surrogateescape")


def extract_switch(paths):
    out = []
    for p in paths:
        text = read_sjis(p)
        for m in TAG.finditer(text):
            g = 1 if m.group(1) is not None else 2
            out.append({"file": p, "start": m.start(g), "end": m.end(g),
                        "kind": "text" if g == 1 else "history", "text": m.group(g)})
    return out


def is_dialogue(s):
    t = s.rstrip(" \u3000<>\r\n")
    if len(t) < 2:
        return False
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", t):
        return False
    if t.startswith("PrintMessage") or "\\" in t:
        return False
    if t.startswith('"'):
        return True
    if " " in t and re.search(r"[A-Za-z]", t):
        return True
    return bool(re.search(r"[.!?…]$", t) and re.search(r"[a-z]", t))


def clean_pc(s):
    s = s.rstrip(" \u3000<>\r\n")
    for k, v in PLACEHOLDERS.items():
        s = s.replace(k, v)
    return s


def extract_pc(paths):
    out = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if line.strip() and is_dialogue(line):
                    out.append(clean_pc(line))
    return out


def is_speech_jp(s):
    return s.lstrip().startswith("「")


def is_speech_en(s):
    return s.startswith('"')


def length_score(jp, en):
    r = (len(en) + 1) / (len(jp) + 1)
    return max(-1.5, min(0.3, 0.3 - 0.5 * abs(math.log(r / 2.5))))


def punct_sig(s):
    """Which of ? ! … appear (JP full-width and EN ASCII forms both count)."""
    return (("?" in s or "？" in s), ("!" in s or "！" in s), ("…" in s or "..." in s))


def punct_score(jp, en):
    """+0.5 per mark present on both sides, -0.7 per mark present on only one side."""
    sc = 0.0
    for a, b in zip(punct_sig(jp), punct_sig(en)):
        if a and b:
            sc += 0.5
        elif a != b:
            sc -= 0.7
    return sc


def align(sw, pc):
    """Semi-global alignment. Returns {switch_idx: pc_idx} for matched pairs."""
    n, m = len(sw), len(pc)
    GAP = -1.5
    NEG = -1e9
    jp_sp = [is_speech_jp(e["text"]) for e in sw]
    en_sp = [is_speech_en(s) for s in pc]
    # dp rows are rolled (only previous+current kept); bt keeps the traceback.
    bt = [bytearray(m + 1) for _ in range(n + 1)]  # 1=pair 2=skip switch 3=skip pc
    prev = [0.0] * (m + 1)  # free leading PC lines
    for i in range(1, n + 1):
        cur = [NEG] * (m + 1)
        cur[0] = prev[0] + GAP
        bt[i][0] = 2
        for j in range(1, m + 1):
            best, how = prev[j] + GAP, 2
            skip_pc = cur[j - 1] + GAP
            if skip_pc > best:
                best, how = skip_pc, 3
            if jp_sp[i - 1] == en_sp[j - 1]:
                pair = prev[j - 1] + 2.0 + length_score(sw[i - 1]["text"], pc[j - 1]) + punct_score(sw[i - 1]["text"], pc[j - 1])
                if pair > best:
                    best, how = pair, 1
            cur[j], bt[i][j] = best, how
        prev = cur
    last_row = prev
    j = max(range(m + 1), key=lambda k: last_row[k])  # free trailing PC lines
    i, pairs = n, {}
    while i > 0:
        how = bt[i][j] if j > 0 or i > 0 else 0
        if j == 0:
            i -= 1
        elif how == 1:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif how == 2:
            i -= 1
        else:
            j -= 1
    return pairs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--switch", nargs="+", required=True)
    ap.add_argument("--pc", nargs="+", required=True)
    ap.add_argument("--out-review", default="review.tsv")
    ap.add_argument("--out-manifest", default=None, help="optional; align_apply.py no longer needs it")
    a = ap.parse_args()

    sw = extract_switch(a.switch)
    pc = extract_pc(a.pc)
    print(f"Switch dialogue strings: {len(sw)}   PC dialogue strings: {len(pc)}")
    pairs = align(sw, pc)

    nomatch = checks = 0
    with open(a.out_review, "w", encoding="utf-8", newline="") as f:
        f.write("idx\tswitch_file\tkind\tjapanese\tenglish_draft\tstatus\n")
        for i, e in enumerate(sw):
            jp = e["text"].replace("\t", " ")
            en, status = "", "NO-MATCH"
            if i in pairs:
                en = pc[pairs[i]].replace("\t", " ")
                if en.startswith('"'):           # PC speech is wrapped in "..." - strip it so no
                    en = en[1:]                  # field starts with a quote (spreadsheets/CSV
                    if en.endswith('"'):         # readers mangle those). align_apply.py can
                        en = en[:-1]             # re-add quotes with --wrap-quotes.
                r = (len(en) + 1) / (len(jp) + 1)
                same_punct = punct_sig(jp) == punct_sig(en)
                status = "OK" if (0.8 <= r <= 8 and same_punct) else "CHECK"
            if status == "NO-MATCH":
                nomatch += 1
            elif status == "CHECK":
                checks += 1
            f.write(f"{i}\t{e['file']}\t{e['kind']}\t{jp}\t{en}\t{status}\n")
    if a.out_manifest:
        with open(a.out_manifest, "w", encoding="utf-8") as f:
            json.dump(sw, f, ensure_ascii=False, indent=1)

    print(f"Matched {len(pairs)}/{len(sw)}  (NO-MATCH: {nomatch}, CHECK: {checks})")
    print(f"Review '{a.out_review}' (tab-separated; open in a spreadsheet), fill/fix english_draft,")
    print("then run align_apply.py. Empty english_draft = line left in Japanese.")


if __name__ == "__main__":
    main()
