#!/usr/bin/env python3
"""
align_apply.py (v2) - apply a reviewed review.tsv to the REAL extracted script
files (from custom_arc.py v2) by matching each Japanese string, in order.

Each row with a non-empty english_draft replaces the Japanese string inside its
tag:  <text JP>  or  <registertexttohistory NULL,"JP">.  Rows with an empty
english_draft are left in Japanese. Works on raw bytes (cp932), so nothing else
in the file is touched.

Target file per row = basename of the row's switch_file; a trailing 'sw' before
the extension is stripped (001_prologue_01sw.txt -> 001_prologue_01.txt).
Override with --file NAME to apply every row to one file.

Quotes: speech is written WITHOUT quotes by default; --wrap-quotes adds straight double quotes
around lines whose Japanese is a speech line.
Safety: curly quotes/dashes are normalised to ASCII; '>' inside <text> and '"'
inside history strings would break the tag, so they are replaced and reported;
anything cp932 can't encode is reported and written as '?'.

Usage:
    python3 align_apply.py review.tsv --src-dir script_jp --out-dir script_en [--file 001_prologue_01.txt]
Then:  python3 custom_arc.py pack script_en script.arc
"""
import argparse, os, re, shutil

ENC = "cp932"
NORMALISE = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
             "\u2026": "...", "\u00a0": " "}


def read_tsv(raw):
    """Literal tab-separated reader (NO quote parsing: Python's csv module eats leading quotes
    and can swallow tabs/newlines). Tolerates files re-saved by a spreadsheet: a field that is
    entirely wrapped in quotes with every inner quote doubled is unescaped."""
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode(ENC)
    lines = [l for l in txt.replace("\r\n", "\n").replace("\r", "\n").split("\n") if l.strip()]
    head = lines[0].split("\t")
    rows = []
    for l in lines[1:]:
        cells = l.split("\t")
        cells += [""] * (len(head) - len(cells))
        row = dict(zip(head, cells))
        for k, v in row.items():
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"' and '"' not in v[1:-1].replace('""', ""):
                row[k] = v[1:-1].replace('""', '"')
        rows.append(row)
    return rows


def target_name(switch_file, override):
    if override:
        return override
    b = os.path.basename(switch_file)
    return re.sub(r"sw(\.[^.]+)$", r"\1", b)


def clean_en(en, kind, notes):
    for k, v in NORMALISE.items():
        en = en.replace(k, v)
    if kind == "text" and ">" in en:
        en = en.replace(">", ")"); notes.append("'>' replaced with ')'")
    if kind == "history" and '"' in en:
        en = en.replace('"', "'"); notes.append('double quotes replaced with single quotes')
    try:
        return en.encode(ENC)
    except UnicodeEncodeError:
        notes.append("has characters cp932 can't encode -> '?'")
        return en.encode(ENC, errors="replace")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("review_tsv")
    ap.add_argument("--src-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--file")
    ap.add_argument("--wrap-quotes", action="store_true",
                    help="wrap english in straight double quotes when the Japanese line is a "
                         "speech line (off by default; test one speech line in-game first)")
    a = ap.parse_args()

    rows = read_tsv(open(a.review_tsv, "rb").read())

    if os.path.abspath(a.src_dir) != os.path.abspath(a.out_dir):
        if os.path.exists(a.out_dir):
            shutil.rmtree(a.out_dir)
        shutil.copytree(a.src_dir, a.out_dir)

    buffers, cursors = {}, {}
    done = skipped = missing = 0
    for r in rows:
        en = (r.get("english_draft") or "").strip()
        if not en:
            skipped += 1
            continue
        name = target_name(r["switch_file"], a.file)
        path = os.path.join(a.out_dir, name)
        if name not in buffers:
            buffers[name] = open(path, "rb").read(); cursors[name] = 0
        data, cur = buffers[name], cursors[name]
        jp = r["japanese"].encode(ENC)
        kind = r["kind"]
        needle = (b"<registertexttohistory NULL,\"" + jp + b"\">") if kind == "history" else (b"<text " + jp + b">")
        pos = data.find(needle, cur)
        if pos < 0:
            print(f"  row {r['idx']}: NOT FOUND in {name} (after previous match) -> {r['japanese'][:30]}")
            missing += 1
            continue
        notes = []
        if a.wrap_quotes and r["japanese"].lstrip().startswith("「") and kind == "text" and not en.startswith('"'):
            en = '"' + en + '"'
        new_inner = clean_en(en, kind, notes)
        new_tag = needle.replace(jp, new_inner, 1)
        buffers[name] = data[:pos] + new_tag + data[pos + len(needle):]
        cursors[name] = pos + len(new_tag)
        done += 1
        if notes:
            print(f"  row {r['idx']}: " + "; ".join(notes))
    for name, data in buffers.items():
        open(os.path.join(a.out_dir, name), "wb").write(data)
    print(f"applied {done}, skipped (empty) {skipped}, not found {missing}; files changed: {', '.join(buffers) or 'none'}")


if __name__ == "__main__":
    main()
