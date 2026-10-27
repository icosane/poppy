#!/usr/bin/env python3
"""Small regression suite for 001_prologue_01 review.tsv.

Usage: python regression_001.py review.tsv
These tests guard known alignment failure cases; passing them is not a full
semantic review or proof that all other rows are correct.
"""
import csv
import sys


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def find(rows, needle, voice_id=None):
    for row in rows:
        if needle in row["japanese"] and (voice_id is None or row["voice_id"] == voice_id):
            return row
    return None


def main(path):
    rows = load(path)
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    # Known row indices are zero-based Switch text indices.
    at = {int(r["idx"]): r for r in rows}
    check("R1 punctuation-only reaction uses safe punctuation, not narration", at[116]["english_draft"].strip() == "...?", at[116]["english_draft"])
    check("R2 （ヤバッ！！） keeps supported '(Crap!)'", "Crap!" in at[117]["english_draft"], at[117]["english_draft"])
    check("R3a MI_0018 line is aligned", "keep supporting me from now on" in at[200]["english_draft"], at[200]["english_draft"])
    check("R3b thanks line is not paired to unrelated identity question", "do you really not know" not in at[201]["english_draft"], at[201]["english_draft"])
    check("R3c handshake narration is aligned", "They shake hands with the mysterious girl" in at[202]["english_draft"], at[202]["english_draft"])
    check("R3d identity question goes to its own line", "do you really not know who I am" in at[204]["english_draft"], at[204]["english_draft"])
    check("R4a 'あ、はい' is not the self-introduction", "My name is" not in at[600]["english_draft"], at[600]["english_draft"])
    check("R4b self-introduction preserves both player-name placeholders", "My name is 主人公（姓） 主人公（名）" in at[601]["english_draft"], at[601]["english_draft"])
    check("R5a choice block preceding narration is aligned", "Since this is about me" in at[643]["english_draft"], at[643]["english_draft"])
    check("R5b approval line is aligned", "I gotta somehow get their approval" in at[644]["english_draft"], at[644]["english_draft"])
    check("R5c question line is aligned, not a menu choice", "What should I do?" in at[645]["english_draft"], at[645]["english_draft"])
    check("R5d choice aftermath narration is aligned", "just listen to what they have to say" in at[646]["english_draft"], at[646]["english_draft"])
    menu = {"Let them continue talking.", "Lose your shit.", "Get castrated."}
    bad = [r for r in rows if r["english_draft"].strip().strip('"') in menu]
    check("R5e PC menu options do not leak into review dialogue", not bad, "; ".join(f"{r['idx']}:{r['english_draft']}" for r in bad[:3]))
    check("R6a NO_0070 voice ID maps to the mating-dance line", "male doing a mating dance might be effective" in at[1064]["english_draft"], at[1064]["english_draft"])
    check("R6b 'ん？' maps to 'Come again?'", at[1065]["english_draft"].strip() == "Come again?", at[1065]["english_draft"])
    check("R6c three ellipsis reactions do not inherit unrelated dialogue", all(at[i]["english_draft"].strip() == "..." for i in (1066,1067,1068)), "; ".join(at[i]["english_draft"] for i in (1066,1067,1068)))
    check("R7a M25_0001 voice-ID sequence", "Just what the hell's going on" in find(rows, "一体何が起きているんだ", "M25_0001_")["english_draft"])
    check("R7b M26_0001 voice-ID sequence", "Don't you get it?" in find(rows, "くっくっく", "M26_0001_")["english_draft"])
    check("R7c M26_0002 voice-ID sequence", "The game's already begun." in find(rows, "もうゲームは始まってる", "M26_0002_")["english_draft"])

    for name, ok, detail in results:
        print(("PASS" if ok else "FAIL") + "  " + name + ("  -> " + str(detail) if not ok else ""))
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results)-failed}/{len(results)} cases pass")
    return 1 if failed else 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python regression_001.py review.tsv")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
