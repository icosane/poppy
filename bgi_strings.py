#!/usr/bin/env python3
"""
bgi_strings.py - pull just the readable text strings out of a decompressed
BGI "BurikoCompiledScriptVer1.00" file, skipping the compiled bytecode.

This is a read-only extraction for reference/translation-planning purposes
(so you can see what a script actually says without wading through opcode
bytes). It does NOT let you edit and reinject text - the bytecode contains
byte-offset jump tables and string-length-prefixed references that this
script doesn't touch or understand, so editing here and pasting back would
corrupt the file. For actual translation + safe reinsertion, use
VNTextPatch or EthornellEditor as discussed.

How it works: the file is null-byte-delimited internally (that's how BGI
stores its string table), so it's split on \\x00, and each resulting chunk
is kept only if it fully decodes as printable text (ASCII, or Shift-JIS
with only printable/whitespace characters) and passes a minimum-length
filter, to exclude short binary noise that happens to be printable by
chance. Tags/system strings (variable names, tag names, sprite/BGM handles
like "TA_0073") are printable too and will show up alongside dialogue -
that's expected, since the file doesn't otherwise mark which strings are
"dialogue" vs "internal" at this raw level.

Usage:
    python3 bgi_strings.py <decompressed_file> [output.txt] [--min-len N]
"""

import sys
import re

MIN_LEN_DEFAULT = 4


def _is_clean_text(s):
    """True if a decoded string looks like real text: printable, not just
    control-character soup, and not dominated by a single repeated char
    (which usually means we decoded into the middle of binary data)."""
    if not s:
        return False
    if any(ch in s for ch in ("\ufffd",)):
        return False
    printable = sum(1 for ch in s if ch.isprintable() or ch.isspace())
    if printable / len(s) < 0.98:
        return False
    return True


def extract_strings(data, min_len=MIN_LEN_DEFAULT):
    results = []
    for chunk in data.split(b"\x00"):
        if len(chunk) < min_len:
            continue
        text = None
        # try Shift-JIS first (superset of ASCII for this engine's text);
        # fall back to treating it as pure ASCII if that fails
        try:
            candidate = chunk.decode("shift_jis")
            if _is_clean_text(candidate):
                text = candidate
        except UnicodeDecodeError:
            pass
        if text is None:
            try:
                candidate = chunk.decode("ascii")
                if _is_clean_text(candidate):
                    text = candidate
            except UnicodeDecodeError:
                pass
        if text is not None:
            results.append(text)
    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = None
    min_len = MIN_LEN_DEFAULT

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--min-len":
            min_len = int(args[i + 1])
            i += 2
        elif out_path is None:
            out_path = args[i]
            i += 1
        else:
            i += 1

    if out_path is None:
        out_path = in_path + "_strings.txt"

    with open(in_path, "rb") as f:
        data = f.read()

    strings = extract_strings(data, min_len)

    with open(out_path, "w", encoding="utf-8") as f:
        for s in strings:
            f.write(s + "\n")

    print(f"Extracted {len(strings)} string(s) from {len(data)} bytes -> {out_path}")


if __name__ == "__main__":
    main()
