#!/usr/bin/env python3
"""
script_postprocess.py (v2) - post-process extracted Switch scripts: speaker names + English text size.

DEFAULT NAME  <setdefaultname 0,八乙女,哲也> in 00_init.txt becomes Yaotome,Tetsuya (family, given), as in the PC build.
COMMAS  the Switch engine drops ASCII commas inside <text ...>; they are rewritten with --comma. Advance widths in the
        game's font: ASCII comma 0.30 em, half-width ､ 0.50 em, full-width ， 1.00 em - so the default is the half-width
        one (keep the space after it); fullwidth-tight drops the space after a full-width comma instead.

NAMES   <name X> values are translated using name_map.tsv (build it with build_name_map.py).
        The protagonist tokens 主人公（名） / 主人公（姓） are NEVER touched, anywhere: the engine
        replaces exactly those tokens with the name the player typed (00_init.txt registers them with
        <setsubstitutionname>). Rewriting them to literal text freezes the name.

SIZE    Only ~3% of dialogue lines carry an explicit <font size:N>; the other ~97% use the engine's
        default size, which no script sets. So there are two independent controls:
          --shrink N   lower every EXISTING explicit size by N (default 3, never below --min-size 20)
          --base S     give every translated line outside an explicit region its own <font size:S> tag
                       (default 27; --base 0 leaves the engine default alone). Untranslated Japanese lines
                       are left alone.
          --fit/--no-fit  long lines step down from the base size (on by default):
                       "90:3,130:5,170:8" = over 90 chars -> S-3, over 130 -> S-5, over 170 -> S-8
                       (change with --fit-steps). The player-name token counts as 6 characters.
        Estimate from the scripts: the engine default is around 32 (sizes below ~31 are used by the
        developers for long lines, 33+ for short shouts). Confirm in-game and adjust.

Examples:
    python3 script_postprocess.py --src-dir script_en --out-dir script_ready          # names, default name, commas, size 27
    python3 script_postprocess.py --src-dir script_en --out-dir script_ready --base 24
    python3 script_postprocess.py --src-dir script_en --out-dir script_ready --names-only
"""
import argparse
import os
import re
import shutil

ENC = "cp932"
PROTAG = ("主人公（名）", "主人公（姓）")
PROTAG_LEN = 6
NAME_TAG = re.compile(r"(<name\s+)([^>]+)(>)")
DEFAULT_NAME = re.compile(r"(<setdefaultname\s+\d+,)([^,>]*),([^,>]*)(>)")
COMMAS = {"fullwidth": "\uff0c", "halfwidth": "\uff64", "backslash": "\\,"}
FONT_SIZE = re.compile(rb"<font size:(\d+)")
JP_CHARS = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
RUBY = re.compile(r"/ruby:[^&/]*&[^/]*/")
COLOR = re.compile(r"/color:0x[0-9A-Fa-f]+(?:\[\d+\])?")


def read_name_map(path):
    mapping, skipped = {}, []
    with open(path, "r", encoding="utf-8-sig") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line or line.lstrip().startswith("#"):
                continue
            cells = line.split("\t")
            if len(cells) < 2 or not cells[0]:
                raise ValueError(f"{path}:{n}: expected Japanese<TAB>English")
            if cells[0] in PROTAG:
                skipped.append(cells[0])
                continue
            if cells[1].strip():
                mapping[cells[0]] = cells[1].strip()
    return mapping, skipped


def visible_text(raw_line):
    """Decoded text of a <text ...> line without tag wrapper, ruby and colour codes."""
    s = raw_line[len(b"<text "):-1].decode(ENC, errors="replace")
    s = RUBY.sub("", s)
    s = COLOR.sub("", s)
    return s


def effective_len(s):
    n = len(s)
    for tok in PROTAG:
        n += s.count(tok) * (PROTAG_LEN - len(tok))
    return n


def has_japanese(s):
    for tok in PROTAG:
        s = s.replace(tok, "")
    return bool(JP_CHARS.search(s))


def size_for(length, base, steps):
    size = base
    for limit, drop in steps:          # steps sorted ascending by limit
        if length > limit:
            size = base - drop
    return size


def process(data, mapping, a, steps, stats):
    # --- names (text level; tokens untouched) ---
    text = data.decode(ENC)
    def name_sub(m):
        new = mapping.get(m.group(2).strip())
        if new is None:
            return m.group(0)
        stats["names"] += 1
        return m.group(1) + new + m.group(3)
    text = NAME_TAG.sub(name_sub, text)
    # --- default player name (00_init.txt): <setdefaultname 0,family,given> ---
    if a.default_name:
        family, given = [x.strip() for x in a.default_name.split(",")]
        def dn_sub(m):
            stats["default_name"] += 1
            return m.group(1) + family + "," + given + m.group(4)
        text = DEFAULT_NAME.sub(dn_sub, text)
    # --- quotes: ASCII double quotes are invisible/problematic in the tested Switch runtime. ---
    # Only change visible translated <text ...> lines; do not touch script syntax or Japanese lines.
    if a.quotes == "single":
        out_lines = []
        for line in text.split("\r\n"):
            if line.startswith("<text ") and not has_japanese(line):
                if '"' in line:
                    line = line.replace('"', "'")
                    stats["quotes"] += 1
            out_lines.append(line)
        text = "\r\n".join(out_lines)
    # --- commas: the engine drops ASCII commas inside <text ...> (see make_text_test.py) ---
    if a.comma != "keep":
        out_lines = []
        for line in text.split("\r\n"):
            if line.startswith("<text ") and "," in line and not has_japanese(line):
                body = line[6:-1]
                if a.comma == "quote":
                    body = '"' + body + '"'
                elif a.comma == "fullwidth-tight":     # full-width comma, drop the space after it
                    body = body.replace(", ", "\uff0c").replace(",", "\uff0c")
                else:
                    body = body.replace(",", COMMAS[a.comma])
                line = "<text " + body + ">"
                stats["commas"] += 1
            out_lines.append(line)
        text = "\r\n".join(out_lines)
    data = text.encode(ENC)
    if a.names_only:
        return data

    # --- existing explicit sizes ---
    if a.shrink:
        def font_sub(m):
            old = int(m.group(1))
            new = max(a.min_size, old - a.shrink)
            if new != old:
                stats["shrunk"] += 1
            return b"<font size:" + str(new).encode()
        data = FONT_SIZE.sub(font_sub, data)

    # --- base size for lines outside explicit regions ---
    if a.base:
        out, in_region = [], False
        for line in data.split(b"\r\n"):
            if line.startswith(b"<font"):
                in_region = line.startswith(b"<font size:")
            elif line.startswith(b"<text ") and not in_region:
                s = visible_text(line)
                if not has_japanese(s):
                    size = size_for(effective_len(s), a.base, steps) if a.fit else a.base
                    out.append(b"<font size:" + str(size).encode() + b">")
                    stats["injected"] += 1
                    stats["by_size"][size] = stats["by_size"].get(size, 0) + 1
            out.append(line)
        data = b"\r\n".join(out)
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src-dir", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--name-map", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "name_map.tsv"))
    ap.add_argument("--shrink", type=int, default=3, help="lower existing explicit sizes by N (default 3)")
    ap.add_argument("--min-size", type=int, default=20)
    ap.add_argument("--base", type=int, default=27,
                    help="size for every translated line outside explicit regions (default 27; 0 = don't touch the default size)")
    ap.add_argument("--fit", dest="fit", action="store_true", help="step long lines down (on by default)")
    ap.add_argument("--no-fit", dest="fit", action="store_false", help="same size for every line")
    ap.set_defaults(fit=True)
    ap.add_argument("--max-bytes", type=int, default=178,
                    help="warn about English lines longer than this many bytes (178 = the longest line in the original Japanese script)")
    ap.add_argument("--fit-steps", default="90:3,130:5,170:8")
    ap.add_argument("--names-only", action="store_true", help="skip all text-size changes (names, default name and commas still apply)")
    ap.add_argument("--default-name", default="Yaotome,Tetsuya",
                    help='default player name as "Family,Given" written into <setdefaultname> (default Yaotome,Tetsuya; "" = leave as is)')
    ap.add_argument("--quotes", choices=["single", "keep"], default="single",
                    help="replace ASCII double quotes with single quotes in translated text (default: single)")
    ap.add_argument("--comma", choices=["halfwidth", "fullwidth", "fullwidth-tight", "backslash", "quote", "keep"], default="fullwidth",
                    help="how to write commas inside <text> lines (default halfwidth: a half-em comma, keep the space after it)")
    a = ap.parse_args()
    if a.in_place and a.out_dir:
        ap.error("--in-place cannot be combined with --out-dir")
    if not a.in_place and not a.out_dir:
        ap.error("provide --out-dir or use --in-place")
    steps = sorted((int(x.split(":")[0]), int(x.split(":")[1])) for x in a.fit_steps.split(","))

    src = os.path.abspath(a.src_dir)
    out = src if a.in_place else os.path.abspath(a.out_dir)
    if src != out:
        if os.path.exists(out):
            shutil.rmtree(out)
        shutil.copytree(src, out)

    mapping, skipped = read_name_map(a.name_map)
    if skipped:
        print(f"note: ignored protagonist-token rows in the name map ({', '.join(sorted(set(skipped)))}) - they must stay as they are")

    stats = {"names": 0, "default_name": 0, "commas": 0, "quotes": 0, "shrunk": 0, "injected": 0, "by_size": {}}
    long_lines = []
    tok_before = tok_after = 0
    changed = 0
    for root, _, files in os.walk(out):
        for fn in sorted(files):
            if not fn.lower().endswith(".txt"):
                continue
            path = os.path.join(root, fn)
            original = open(path, "rb").read()
            tok_before += sum(original.decode(ENC, errors="replace").count(t) for t in PROTAG)
            updated = process(original, mapping, a, steps, stats)
            tok_after += sum(updated.decode(ENC, errors="replace").count(t) for t in PROTAG)
            for ln in updated.split(b"\r\n"):
                if ln.startswith(b"<text ") and len(ln) - 7 > a.max_bytes and not has_japanese(visible_text(ln)):
                    long_lines.append((len(ln) - 7, fn, visible_text(ln)[:70]))
            if updated != original:
                open(path, "wb").write(updated)
                changed += 1
    print(f"changed {changed} file(s) in {out}")
    print(f"speaker-name tags translated: {stats['names']}")
    print(f"default player name set ({a.default_name or 'unchanged'}): {stats['default_name']} tag(s); lines with commas rewritten ({a.comma}): {stats['commas']}; lines with double quotes converted ({a.quotes}): {stats['quotes']}")
    if not a.names_only:
        print(f"existing explicit sizes lowered by {a.shrink}: {stats['shrunk']}")
        if a.base:
            print(f"lines given an explicit size ({'fit' if a.fit else 'flat'} from base {a.base}): {stats['injected']}  by size: "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(stats['by_size'].items(), reverse=True)))
    if long_lines:
        long_lines.sort(reverse=True)
        print(f"\nWARNING: {len(long_lines)} English line(s) are longer than {a.max_bytes} bytes (the longest original Japanese line). "
              f"They may overflow the box and are the first suspects for log/backlog crashes - shorten them in review.tsv:")
        for n, fn, pre in long_lines[:20]:
            print(f"   {n:>4} bytes  {fn:<24} {pre}")
    print(f"protagonist tokens before/after: {tok_before}/{tok_after}" + ("   OK, untouched" if tok_before == tok_after else "   !!! CHANGED"))


if __name__ == "__main__":
    main()
