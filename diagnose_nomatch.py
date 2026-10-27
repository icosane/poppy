#!/usr/bin/env python3
"""Create candidate diagnostics for NO-MATCH rows in align_extract.py output.

This is a review aid, not an automatic translator: Japanese/English semantic
similarity cannot be inferred reliably from character length alone. Candidates
are ranked using line shape (speech/narration, length, punctuation) and, when
possible, their position between neighboring English matches in the same PC
script dump.
"""
import argparse
import csv
import os
import re
import math
from collections import defaultdict

JP_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
PLACEHOLDERS = {"Protag(First)": "主人公（名）", "Protag(Last)": "主人公（姓）"}


def is_dialogue(s):
    t = s.rstrip(" \u3000<>\r\n")
    if len(t) < 2 or JP_CHARS.search(t) or t.startswith("PrintMessage") or "\\\\" in t:
        return False
    if t.startswith('"'):
        return True
    if " " in t and re.search(r"[A-Za-z]", t):
        return True
    return bool(re.search(r"[.!?…]$", t) and re.search(r"[a-z]", t))


def clean(s):
    s = s.strip().rstrip(" \u3000<>\r\n")
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    for k, v in PLACEHOLDERS.items():
        s = s.replace(k, v)
    return s.strip()


def speech_jp(s):
    return s.lstrip().startswith(("「", "『"))


def speech_en(s):
    return s.lstrip().startswith('"')


def punct(s):
    return (("?" in s or "？" in s), ("!" in s or "！" in s), ("…" in s or "..." in s))


def score_shape(jp, en):
    # Broad length prior only; translations vary greatly in length.
    ratio = (len(en) + 1) / (len(jp) + 1)
    score = max(-2.0, 1.0 - abs(math.log(max(ratio, 0.01) / 2.5)))
    if speech_jp(jp) == speech_en(en):
        score += 1.0
    else:
        score -= 1.0
    for a, b in zip(punct(jp), punct(en)):
        score += 0.35 if a and b else (-0.25 if a != b else 0)
    return score


def read_review(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
        return list(csv.DictReader(f, delimiter=delimiter))


def load_pc(root):
    pc_root = os.path.abspath(root)
    rows = []
    for base, _, files in os.walk(root):
        for fn in sorted(files):
            if not fn.lower().endswith((".txt", ".strings")):
                continue
            path = os.path.join(base, fn)
            try:
                with open(path, encoding="utf-8-sig") as f:
                    lines = f.read().splitlines()
            except (OSError, UnicodeError):
                continue
            for i, raw in enumerate(lines):
                if raw.strip() and is_dialogue(raw):
                    rows.append({"source": os.path.relpath(path, pc_root), "line": i + 1,
                                 "raw": raw, "text": clean(raw)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("review", help="review.tsv/csv from align_extract.py")
    ap.add_argument("--pc-dir", required=True, help="directory containing all pc_prepare string dumps")
    ap.add_argument("--out", default="no_match_diagnostics.tsv")
    ap.add_argument("--top", type=int, default=10, help="candidates per NO-MATCH row (default: 10)")
    a = ap.parse_args()

    review = read_review(a.review)
    pc = load_pc(a.pc_dir)
    by_text = defaultdict(list)
    for j, r in enumerate(pc):
        by_text[r["text"]].append(j)

    # For each review row, locate nearest previous/next reviewed English lines
    # in the all-PC pool. Anchors are only trusted for context if they resolve
    # to the same source dump.
    out_rows = []
    nomatches = [i for i, r in enumerate(review) if r.get("status", "").strip() == "NO-MATCH"]
    for ri in nomatches:
        row = review[ri]
        jp = row.get("japanese", "")
        prev_anchor = next_anchor = None
        for k in range(ri - 1, -1, -1):
            en = clean(review[k].get("english_draft", ""))
            if en and en in by_text:
                prev_anchor = (k, by_text[en][0])
                break
        for k in range(ri + 1, len(review)):
            en = clean(review[k].get("english_draft", ""))
            if en and en in by_text:
                next_anchor = (k, by_text[en][0])
                break

        ranked = []
        for ci, c in enumerate(pc):
            score = score_shape(jp, c["text"])
            reason = ["shape"]
            # Context is useful only when both neighboring matches resolve
            # in order within the same source script.
            if prev_anchor and next_anchor:
                p = pc[prev_anchor[1]]
                n = pc[next_anchor[1]]
                if p["source"] == n["source"] == c["source"] and p["line"] < n["line"]:
                    if p["line"] < c["line"] < n["line"]:
                        score += 6.0
                        reason.append("between-neighbor-matches")
                    else:
                        score -= 1.0
            elif prev_anchor and c["source"] == pc[prev_anchor[1]]["source"]:
                score += 0.5
                reason.append("same-file-as-prev")
            elif next_anchor and c["source"] == pc[next_anchor[1]]["source"]:
                score += 0.5
                reason.append("same-file-as-next")
            ranked.append((score, ci, ";".join(reason)))
        ranked.sort(reverse=True)
        for rank, (score, ci, reason) in enumerate(ranked[:max(1, a.top)], 1):
            c = pc[ci]
            out_rows.append({
                "review_idx": row.get("idx", ri), "switch_file": row.get("switch_file", ""),
                "japanese": jp, "candidate_rank": rank, "score": f"{score:.3f}",
                "candidate_source": c["source"], "candidate_line": c["line"],
                "candidate_english": c["text"], "ranking_reason": reason,
                "note": "Heuristic only; verify in the original PC game/script."
            })

    fields = ["review_idx", "switch_file", "japanese", "candidate_rank", "score",
              "candidate_source", "candidate_line", "candidate_english", "ranking_reason", "note"]
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(out_rows)
    print(f"PC dialogue candidates loaded: {len(pc)}")
    print(f"NO-MATCH rows: {len(nomatches)}; candidates written: {len(out_rows)} -> {a.out}")


if __name__ == "__main__":
    main()
