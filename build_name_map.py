#!/usr/bin/env python3
"""
build_name_map.py - build name_map.tsv covering EVERY speaker name used in the Switch scripts.

Sources of English names, in priority order:
  1. PC string pools (pc_prepare.py output): in the PC build, `PrintMessage <JP name>` is followed
     a few entries later by the English display name (e.g. PrintMessage 星九頭 ... Hoshikuzu).
     Pairs are collected from every file and the most frequent one wins.
  2. Compounds like 希未・涼花 are built from their parts ("Nozomi & Suzuka").
  3. Lettered extras like 寮生Ａ / 客Ｂ are built from the base word + the letter.
  4. Anything left is written with an EMPTY english column so you can fill it in.
An existing name_map.tsv is respected: rows you already filled in are never overwritten.

The protagonist tokens 主人公（名） / 主人公（姓） are NEVER mapped: the engine substitutes the name
the player typed for those exact tokens (see <setsubstitutionname> in 00_init.txt).

Usage:
    python3 build_name_map.py --switch-dir script_jp --pc-dir pc_strings --out name_map.tsv
    (--existing name_map.tsv  to merge with your hand-made entries; defaults to --out if it exists)
"""
import argparse
import collections
import os
import re

ENC = "cp932"
PROTAG = {"主人公（名）", "主人公（姓）"}
NAME_TAG = re.compile(r"<name\s+([^>]*)>")
EN_NAME = re.compile(r"^[A-Z][a-z][A-Za-z'’.\- ]{0,38}$")      # e.g. Hoshikuzu, Miu's Friend A, Customer G
LETTER_JP = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"


def switch_names(src):
    counts = collections.Counter()
    for n in sorted(os.listdir(src)):
        if n.startswith("_") or n.endswith(".bin"):
            continue
        t = open(os.path.join(src, n), "rb").read().decode(ENC, errors="replace")
        for m in NAME_TAG.finditer(t):
            counts[m.group(1).strip()] += 1
    return counts


def mine_pc(pc_dir):
    votes = collections.defaultdict(collections.Counter)
    for n in sorted(os.listdir(pc_dir)):
        lines = open(os.path.join(pc_dir, n), encoding="utf-8", errors="replace").read().split("\n")
        seen = set()
        for i, l in enumerate(lines):
            m = re.match(r"^PrintMessage (.+)$", l.strip("\r"))
            if not m:
                continue
            jp = m.group(1).strip()
            if jp in seen or jp in PROTAG:
                continue
            seen.add(jp)
            for k in range(i + 1, min(i + 9, len(lines))):
                c = lines[k].strip("\r ")
                if " " not in c and re.search(r"[a-z][A-Z]", c):      # CamelCase = engine function name
                    continue
                if EN_NAME.match(c) and not c.startswith("PrintMessage"):
                    votes[jp][c] += 1
                    break
    return votes


# Drafts for names the PC string pool doesn't provide. Marked "draft" in the output - check them.
DRAFT = {
    "父": "Dad", "エミ": "Emi", "ＴＶアナウンサー": "TV Announcer", "ガキ": "Kid", "ＭＣ": "MC", "ＰＣ": "PC",
    "Ｍｅ－Ｙｏｕ社員Ａ": "Me-You Employee A", "Ｍｅ－Ｙｏｕ社員Ｂ": "Me-You Employee B",
    "ウサギの飼い主（？）": "Rabbit's Owner (?)", "ＤＪ ＴＡＭＡＫＩ": "DJ TAMAKI",
    "男": "Man", "客１": "Customer 1", "客２": "Customer 2",
}


# Corrections for rows where the PC pool's neighbouring string is misleading (checked by hand).
OVERRIDE = {"店員Ａ": "Clerk A", "店員Ｂ": "Clerk B", "店員Ａ・Ｂ": "Clerk A & B",
            "？？？": "???", "園内放送": "Park Announcement"}


def read_existing(path):
    out = {}
    if path and os.path.exists(path):
        for l in open(path, encoding="utf-8-sig"):
            l = l.rstrip("\r\n")
            if not l or l.lstrip().startswith("#"):
                continue
            c = l.split("\t")
            if len(c) >= 2 and c[0]:
                out[c[0]] = c[1]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--switch-dir", required=True)
    ap.add_argument("--pc-dir", required=True)
    ap.add_argument("--out", default="name_map.tsv")
    ap.add_argument("--existing")
    a = ap.parse_args()

    counts = switch_names(a.switch_dir)
    votes = mine_pc(a.pc_dir)
    existing = read_existing(a.existing or a.out)
    result, source = {}, {}

    def single(jp):
        if jp in PROTAG:
            return None
        if jp in existing and existing[jp]:
            return existing[jp], "yours"
        if jp in OVERRIDE:
            return OVERRIDE[jp], "checked"
        if jp in votes:
            top, n = votes[jp].most_common(1)[0]
            return top, (f"PC x{n}" if n >= 3 else f"PC x{n} CHECK")
        return None

    values = sorted(counts, key=lambda v: -counts[v])
    for jp in values:                                     # pass 1: direct hits (compounds wait for pass 2)
        if jp in PROTAG or ("・" in jp and jp not in existing and jp not in OVERRIDE):
            continue
        r = single(jp)
        if r:
            result[jp], source[jp] = r
    for jp in values:                                     # pass 2: compounds and lettered extras
        if jp in result or jp in PROTAG:
            continue
        if "・" in jp:
            parts = jp.split("・")
            en = []
            for p in parts:
                if p in PROTAG:
                    en.append(p)                          # token stays: engine substitutes it
                elif p in result:
                    en.append(result[p])
                else:
                    en = None
                    break
            if en:
                result[jp], source[jp] = " & ".join(en), "compound"
                continue
        m = re.match(r"^(.*?)([Ａ-Ｚ])$", jp)
        if m and m.group(1) in result:
            letter = chr(ord("A") + LETTER_JP.index(m.group(2)))
            result[jp], source[jp] = f"{result[m.group(1)]} {letter}", "base+letter"
    # compounds whose parts were resolved only in pass 2 (e.g. 寮生Ａ・Ｂ) - one more sweep
    for jp in values:
        if jp in result or jp in PROTAG or "・" not in jp:
            continue
        parts = jp.split("・")
        en = [p if p in PROTAG else result.get(p) for p in parts]
        if all(en):
            result[jp], source[jp] = " & ".join(en), "compound"

    for jp in values:                                     # pass 3: "寮生Ｊ・Ｋ" style, base taken from lettered siblings
        if jp in result:
            continue
        m = re.match(r"^(.*?)([Ａ-Ｚ])・([Ａ-Ｚ])$", jp)
        if m:
            sib = result.get(m.group(1) + "Ａ") or result.get(m.group(1) + "Ｂ")
            if sib:
                base = re.sub(r" [A-Z]$", "", sib)
                l1 = chr(ord("A") + LETTER_JP.index(m.group(2)))
                l2 = chr(ord("A") + LETTER_JP.index(m.group(3)))
                result[jp], source[jp] = f"{base} {l1} & {l2}", "base+letters"
    for jp in values:
        if jp not in result and jp in DRAFT:
            result[jp], source[jp] = DRAFT[jp], "draft CHECK"

    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write("# Japanese speaker name<TAB>English<TAB>source/uses  (edit the English column; only the first two columns are read)\n")
        f.write("# Protagonist tokens (主人公（名）/主人公（姓）) are deliberately absent: the engine fills in the player's name.\n")
        unresolved = []
        for jp in values:
            if jp in PROTAG:
                continue
            en = result.get(jp, "")
            if not en:
                unresolved.append(jp)
            f.write(f"{jp}\t{en}\t{source.get(jp, 'UNMAPPED')} / {counts[jp]} lines\n")
    covered = sum(counts[j] for j in result)
    total = sum(counts[j] for j in values if j not in PROTAG)
    print(f"{len(result)}/{len([v for v in values if v not in PROTAG])} distinct names mapped "
          f"({100*covered/total:.1f}% of all non-protagonist name tags)")
    check = [j for j in values if j in source and "CHECK" in source[j]]
    if check:
        print(f"\n{len(check)} entries are low-confidence (fewer than 3 PC votes, or my own draft). Review these first, most used first:")
        for jp in check[:25]:
            print(f"   {jp:<18} -> {result[jp]:<28} ({counts[jp]} lines, {source[jp]})")
        if len(check) > 25:
            print(f"   ... and {len(check) - 25} more marked CHECK in {a.out}")
    if unresolved:
        print(f"{len(unresolved)} still empty - fill them in {a.out}:")
        for jp in unresolved:
            print(f"   {jp}   ({counts[jp]} lines)")


if __name__ == "__main__":
    main()
