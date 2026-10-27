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
  * A gap-tolerant alignment pairs speech with speech and narration with narration.
    Voice-ID conflicts are penalized strongly; after the main alignment, a cautious
    local pass can swap adjacent assignments when the Switch/PC voice IDs clearly
    support the crossed pairing. Unmatched voice-ID recovery never reuses an English
    occurrence already assigned to another Switch line.
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
import unicodedata

ENC = "cp932"  # superset of Shift-JIS
TAG = re.compile(r'<text ([^>]+)>|<registertexttohistory NULL,"([^"]*)">')
VOICE = re.compile(r'<voice\b[^>]*?\bvoice:([^,>]+)', re.IGNORECASE)
NAME = re.compile(r'<name\s+([^>]+)>', re.IGNORECASE)
PC_VOICE_ID = re.compile(r'^[A-Za-z]+_?\d+(?:_\d+)?_?$')
PLACEHOLDERS = {"Protag(First)": "主人公（名）", "Protag(Last)": "主人公（姓）"}


def read_sjis(path):
    with open(path, "rb") as f:
        return f.read().decode(ENC, errors="surrogateescape")


def extract_switch(paths):
    out = []
    for p in paths:
        text = read_sjis(p)
        previous_end = 0
        for m in TAG.finditer(text):
            g = 1 if m.group(1) is not None else 2
            # Only inspect commands since the previous text tag, so an earlier
            # speaker/voice cannot accidentally leak onto a later narration line.
            prefix = text[previous_end:m.start()]
            previous_end = m.end()
            voices = list(VOICE.finditer(prefix))
            names = list(NAME.finditer(prefix))
            voice_id = voices[-1].group(1).strip() if voices else ""
            speaker = names[-1].group(1).strip() if names else ""
            out.append({"file": p, "start": m.start(g), "end": m.end(g),
                        "kind": "text" if g == 1 else "history", "text": m.group(g),
                        "voice_id": voice_id, "speaker": speaker})
    return out

def is_dialogue(s):
    """Keep actual dialogue/narration; reject bare UI labels and speaker names.

    PC string dumps contain scene labels such as "Map App" and "Waitress A".
    Treating every multi-word Latin string as dialogue pollutes the alignment
    and can make a bad pairing look like a successful match. Quoted strings are
    strong evidence; unquoted strings must look like a complete sentence.
    """
    t = s.rstrip(" \u3000<>\r\n")
    if len(t) < 2:
        return False
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", t):
        return False
    if t.startswith("PrintMessage") or "\\" in t:
        return False
    if t.startswith('"'):
        return True
    # Unquoted narration/interruptions generally end in sentence punctuation.
    # Exclude labels like "Map App", "Waitress A", and other bare identifiers.
    if not re.search(r"[.!?…][\"'’”)]?$", t):
        return False
    return bool(re.search(r"[A-Za-z]", t))


def clean_pc(s):
    s = s.rstrip(" \u3000<>\r\n")
    for k, v in PLACEHOLDERS.items():
        s = s.replace(k, v)
    return s


def extract_pc(paths):
    """Extract dialogue while retaining nearby PC voice/message IDs.

    The PC dump is a flattened string pool rather than an execution trace. In
    addition to filtering non-dialogue strings, exclude known choice-menu
    strings so that menu options cannot consume Japanese dialogue/narration
    positions during sequence alignment.
    """
    out = []
    label = re.compile(r"LABEL_[A-Z]")
    for p in paths:
        with open(p, encoding="utf-8") as f:
            lines = [line.rstrip("\r\n") for line in f]

        # Choice layout A: option text / selection commands bounded by the
        # engine's InitializeSelectedItem ... _SelectEx markers.
        choice = set()
        start = None
        for i, raw in enumerate(lines):
            t = raw.strip()
            if t == "InitializeSelectedItem":
                start = i
            elif t == "_SelectEx" and start is not None:
                choice.update(range(start, i + 1))
                start = None
            elif start is not None and i - start > 40:
                # Avoid accidentally excluding a long tail if a closing marker
                # is missing in a malformed/partial dump.
                choice.update(range(start, i))
                start = None

        # Choice layout B: N option strings directly precede N LABEL_A/B/... 
        # jump labels. Do not use this fallback when selection commands already
        # identify that same block.
        i = 0
        while i < len(lines):
            if label.fullmatch(lines[i].strip()) and not (i and label.fullmatch(lines[i - 1].strip())):
                k = i
                while k < len(lines) and label.fullmatch(lines[k].strip()):
                    k += 1
                n_labels = k - i
                found = []
                j = i - 1
                while j >= 0 and len(found) < n_labels:
                    if lines[j].strip():
                        found.append(j)
                    j -= 1
                if not any(lines[x].strip() in ("_SelectEx", "InitializeSelectedItem", "select") for x in found):
                    choice.update(found)
                i = k
            else:
                i += 1

        ids = {}
        for i, raw in enumerate(lines):
            candidate = raw.strip()
            if i in choice or not PC_VOICE_ID.match(candidate):
                continue
            for j in range(i + 1, min(i + 7, len(lines))):
                if j in choice:
                    continue
                t = lines[j].strip()
                if t.startswith("PrintMessage") or PC_VOICE_ID.match(t):
                    break
                if t.startswith('"') and is_dialogue(t):
                    ids[j] = candidate
                    break

        for i, line in enumerate(lines):
            if i not in choice and line.strip() and is_dialogue(line):
                out.append({"text": clean_pc(line), "voice_id": ids.get(i, ""),
                            "source": p, "line": i + 1})
    return out

def is_speech_jp(s):
    # Both Japanese corner-quote styles are used for spoken dialogue.
    return s.lstrip().startswith(("「", "『"))


def is_speech_en(s):
    return s.lstrip().startswith('"')


def normalize_match_text(s):
    """Normalize cosmetic differences without erasing meaningful wording."""
    s = unicodedata.normalize("NFKC", s).casefold()
    s = s.replace("…", "...").replace("〜", "~").replace("～", "~")
    s = re.sub(r"[\s\u3000]+", "", s)
    # Ending marks and quote styles often differ between Japanese and English.
    s = re.sub(r"[\"'“”‘’「」『』（）()、。，．,.!?！？:：;；…~～—–-]+$", "", s)
    return s


def length_score(jp, en):
    # Length is a weak clue only: translations can naturally expand or contract.
    r = (len(en) + 1) / (len(jp) + 1)
    return max(-0.8, min(0.35, 0.35 - 0.28 * abs(math.log(r / 2.5))))


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


def punctuation_only_translation(s):
    """Convert a Japanese punctuation-only utterance without consuming a PC line."""
    t = s.strip().replace("\u3000", "")
    paren = False
    if t[:1] in "（(" and t[-1:] in "）)":
        paren, t = True, t[1:-1]
    elif t[:1] in "「『" and t[-1:] in "」』":
        t = t[1:-1]
    out = []
    previous_ellipsis = False
    for ch in t:
        if ch in "…・":
            if not previous_ellipsis:
                out.append("...")
            previous_ellipsis = True
        else:
            previous_ellipsis = False
            if ch in "？！?!": out.append("?" if ch in "？?" else "!")
            elif ch in "。、，,．." or ch.isspace(): continue
            else: return None
    if not out:
        return None
    value = "".join(out)
    return f"({value})" if paren else value


def punctuation_only_jp(s):
    return punctuation_only_translation(s) is not None


def align(sw, pc):
    """Semi-global alignment. Returns {switch_idx: pc_idx} for matched pairs."""
    n, m = len(sw), len(pc)
    sw_id_counts = {}
    pc_id_counts = {}
    for e in sw:
        v = e.get("voice_id", "").strip()
        if v:
            sw_id_counts[v] = sw_id_counts.get(v, 0) + 1
    for e in pc:
        v = e.get("voice_id", "").strip()
        if v:
            pc_id_counts[v] = pc_id_counts.get(v, 0) + 1
    GAP = -1.5
    NEG = -1e9
    jp_sp = [is_speech_jp(e["text"]) for e in sw]
    en_sp = [is_speech_en(e["text"]) for e in pc]
    # Player-name placeholders are deliberately retained in both scripts and
    # are unusually strong alignment anchors when present.
    sw_tokens = [frozenset(t for t in PLACEHOLDERS.values() if t in e["text"]) for e in sw]
    pc_tokens = [frozenset(t for t in PLACEHOLDERS.values() if t in e["text"]) for e in pc]
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
                sw_id = sw[i - 1].get("voice_id", "").strip()
                pc_id = pc[j - 1].get("voice_id", "").strip()
                # IDs are useful evidence, but some voice-bank clips are reused.
                # Repetition counts are computed over the current chapter; common
                # IDs receive a smaller bonus than IDs that identify one occurrence.
                sw_count = sw_id_counts.get(sw_id, 0) if sw_id else 0
                pc_count = pc_id_counts.get(pc_id, 0) if pc_id else 0
                id_bonus = (2.5 if sw_count > 1 or pc_count > 1 else 5.0) if sw_id and pc_id and sw_id == pc_id else 0.0
                # A conflicting explicit ID is meaningful evidence against a pair.
                # Keep it as a penalty rather than a hard ban because the PC dump
                # can associate IDs imperfectly and stock clips may be reused.
                id_penalty = -4.0 if sw_id and pc_id and sw_id != pc_id else 0.0
                pair = prev[j - 1] + 2.0 + length_score(sw[i - 1]["text"], pc[j - 1]["text"]) + punct_score(sw[i - 1]["text"], pc[j - 1]["text"]) + id_bonus + id_penalty
                st, pt = sw_tokens[i - 1], pc_tokens[j - 1]
                if st or pt:
                    pair += 5.0 * len(st & pt) - 5.0 * len(st ^ pt)
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
    # Second pass: recover unmatched Switch occurrences from a known voice ID.
    # This permits reuse of a stock voice clip, but only when the ID match is
    # unique or repeated candidates have a clearly better length/sequence fit.
    used = set(pairs.values())
    by_voice = {}
    for j, e in enumerate(pc):
        v = e.get("voice_id", "").strip()
        if v:
            by_voice.setdefault(v, []).append(j)
    for i, e in enumerate(sw):
        if i in pairs:
            continue
        v = e.get("voice_id", "").strip()
        candidates = by_voice.get(v, []) if v else []
        # Do not silently assign the same PC occurrence to multiple Switch rows.
        candidates = [j for j in candidates if j not in used and jp_sp[i] == en_sp[j]]
        if not candidates:
            continue
        def fallback_score(j):
            score = 1.5 + length_score(e["text"], pc[j]["text"]) + punct_score(e["text"], pc[j]["text"])
            # Nearby already-aligned lines are a useful tie-breaker.
            left = pairs.get(i - 1)
            right = pairs.get(i + 1)
            if left is not None:
                score += max(-1.0, 0.5 - 0.08 * abs(j - left - 1))
            if right is not None:
                score += max(-1.0, 0.5 - 0.08 * abs(right - j - 1))
            return score
        ranked = sorted(((fallback_score(j), j) for j in candidates), reverse=True)
        if len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.65:
            pairs[i] = ranked[0][1]
    # Conservative local correction: if two adjacent Switch rows were paired
    # with two adjacent PC occurrences in the opposite order, swap only when both
    # crossed voice IDs agree and the current pairings contradict them. This targets
    # small local inversions without using semantic translation or an AI model.
    ordered = sorted(pairs)
    for pos in range(len(ordered) - 1):
        i1, i2 = ordered[pos], ordered[pos + 1]
        if i2 != i1 + 1:
            continue
        j1, j2 = pairs[i1], pairs[i2]
        if j1 == j2:
            continue
        s1 = sw[i1].get("voice_id", "").strip()
        s2 = sw[i2].get("voice_id", "").strip()
        p1 = pc[j1].get("voice_id", "").strip()
        p2 = pc[j2].get("voice_id", "").strip()
        crossed = s1 and s2 and p1 and p2 and s1 == p2 and s2 == p1
        current_conflict = (s1 and p1 and s1 != p1) or (s2 and p2 and s2 != p2)
        if crossed and current_conflict and jp_sp[i1] == en_sp[j2] and jp_sp[i2] == en_sp[j1]:
            pairs[i1], pairs[i2] = j2, j1
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
    sw_id_counts = {}
    pc_id_counts = {}
    for e in sw:
        v = e.get("voice_id", "").strip()
        if v: sw_id_counts[v] = sw_id_counts.get(v, 0) + 1
    for e in pc:
        v = e.get("voice_id", "").strip()
        if v: pc_id_counts[v] = pc_id_counts.get(v, 0) + 1
    # Punctuation-only Switch utterances should not consume an arbitrary PC
    # string in the sequence DP. Translate punctuation directly, then recover a
    # short spoken reaction only when its voice ID and punctuation both agree.
    rule = {i: punctuation_only_translation(e["text"]) for i, e in enumerate(sw)}
    rule = {i: value for i, value in rule.items() if value is not None}
    keep = [i for i in range(len(sw)) if i not in rule]
    subpairs = align([sw[i] for i in keep], pc)
    pairs = {keep[k]: v for k, v in subpairs.items()}
    used = set(pairs.values())
    by_voice = {}
    for j, e in enumerate(pc):
        v = e.get("voice_id", "").strip()
        if v:
            by_voice.setdefault(v, []).append(j)
    rule_status = {i: "OK (RULE)" for i in rule}

    # First recover very short spoken reactions with a unique voice-ID match.
    # A punctuation-only Japanese line must not inherit a long line merely
    # because a reused/nearby ID happens to agree.
    for i in list(rule):
        e = sw[i]
        v = e.get("voice_id", "").strip()
        candidates = [j for j in by_voice.get(v, []) if j not in used] if v else []
        if len(candidates) == 1:
            j = candidates[0]
            en = pc[j]["text"]
            if len(en.strip('" ')) <= 10 and punct_sig(e["text"]) == punct_sig(en):
                pairs[i] = j
                used.add(j)
                rule_status[i] = "OK (VOICE ID)"

    # If no ID-backed reaction exists, look only between the already-aligned
    # neighbours. A unique short punctuation-compatible candidate is useful,
    # but remains CHECK because the Japanese line itself contains no words.
    for i in list(rule):
        if i in pairs:
            continue
        lefts = [k for k in pairs if k < i]
        rights = [k for k in pairs if k > i]
        left = max(lefts) if lefts else None
        right = min(rights) if rights else None
        lo = pairs[left] + 1 if left is not None else 0
        hi = pairs[right] if right is not None else len(pc)
        if hi < lo:
            continue
        candidates = []
        for j in range(lo, hi):
            if j in used:
                continue
            en = pc[j]["text"]
            if len(en.strip('" ')) <= 24 and punct_sig(sw[i]["text"]) == punct_sig(en):
                candidates.append(j)
        if len(candidates) == 1:
            pairs[i] = candidates[0]
            used.add(candidates[0])
            rule_status[i] = "CHECK"

    print(f"Switch text tags: {len(sw)} ({len(rule)} punctuation-only by rule)   PC dialogue strings: {len(pc)}")

    nomatch = checks = 0
    with open(a.out_review, "w", encoding="utf-8", newline="") as f:
        f.write("idx\tswitch_file\tkind\tjapanese\tenglish_draft\tstatus\tvoice_id\tspeaker\tpc_voice_id\tpc_source\tpc_line\n")
        for i, e in enumerate(sw):
            jp = e["text"].replace("\t", " ")
            en, status = "", "NO-MATCH"
            if i in rule and i not in pairs:
                en, status = rule[i], rule_status[i]
            elif i in pairs:
                en = pc[pairs[i]]["text"].replace("\t", " ")
                if en.startswith('"'):           # PC speech is wrapped in "..." - strip it so no
                    en = en[1:]                  # field starts with a quote (spreadsheets/CSV
                    if en.endswith('"'):         # readers mangle those). align_apply.py can
                        en = en[:-1]             # re-add quotes with --wrap-quotes.
                r = (len(en) + 1) / (len(jp) + 1)
                same_punct = punct_sig(jp) == punct_sig(en)
                cosmetic_match = normalize_match_text(jp) == normalize_match_text(en)
                sw_id = e.get("voice_id", "").strip()
                pc_id = pc[pairs[i]].get("voice_id", "").strip()
                sw_tokens = {t for t in PLACEHOLDERS.values() if t in e["text"]}
                pc_tokens = {t for t in PLACEHOLDERS.values() if t in pc[pairs[i]]["text"]}
                if i in rule and rule_status.get(i) == "CHECK":
                    status = "CHECK"
                elif sw_tokens != pc_tokens:
                    status = "CHECK"
                elif sw_id and pc_id and sw_id == pc_id:
                    # A unique ID pair is a stronger anchor. Reused IDs are
                    # evidence, not proof, and remain CHECK rather than green.
                    unique_id = sw_id_counts.get(sw_id, 0) == 1 and pc_id_counts.get(pc_id, 0) == 1
                    status = "OK (VOICE ID)" if unique_id and (0.20 <= r <= 15) else "CHECK"
                elif cosmetic_match:
                    status = "OK"
                elif sw_id and pc_id and sw_id != pc_id:
                    # Explicitly contradictory IDs should not be silently accepted.
                    status = "CHECK"
                else:
                    # A plausible length ratio alone does not prove alignment.
                    # Use the ratio only to catch truly extreme pairings.
                    status = "OK" if (0.35 <= r <= 8 and same_punct) else "CHECK"
            if status == "NO-MATCH":
                nomatch += 1
            elif status == "CHECK":
                checks += 1
            pcrow = pc[pairs[i]] if i in pairs else {}
            f.write(f"{i}\t{e['file']}\t{e['kind']}\t{jp}\t{en}\t{status}\t{e.get('voice_id','')}\t{e.get('speaker','')}\t{pcrow.get('voice_id','')}\t{pcrow.get('source','')}\t{pcrow.get('line','')}\n")
    if a.out_manifest:
        with open(a.out_manifest, "w", encoding="utf-8") as f:
            json.dump(sw, f, ensure_ascii=False, indent=1)

    matched = len(sw) - nomatch
    by_rule = sum(1 for i in rule if i not in pairs)
    print(f"Matched {matched}/{len(sw)}  (by rule: {by_rule}, NO-MATCH: {nomatch}, CHECK: {checks})")
    print(f"Review '{a.out_review}' (tab-separated; open in a spreadsheet), fill/fix english_draft,")
    print("then run align_apply.py. Empty english_draft = line left in Japanese.")


if __name__ == "__main__":
    main()
