#!/usr/bin/env python3
"""Conservative string patcher for sysgra_mes.mul.

This first-pass tool patches UTF-8 string bytes in place, preserving the binary's
length and every offset. Replacements MUST encode to exactly the same number of
bytes as the source. It deliberately refuses variable-length edits until the
resource's complete index/layout is understood.

Usage:
  python mul_patch.py scan sysgra_mes.mul -o mul_strings.tsv
  python mul_patch.py patch sysgra_mes.mul ui_map.tsv -o sysgra_mes_patched.mul

TSV map columns: source<TAB>replacement
Use literal Japanese/English text, no quotes. Lines starting with # are ignored.
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

# Printable ASCII strings are easy to inventory. Japanese/Chinese UTF-8 strings
# are also detected by decoding valid UTF-8 spans and extracting non-ASCII runs.
ASCII_RUN = re.compile(rb'[\x20-\x7e]{3,}')
CJK_RUN = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]{2,}')


def extract_runs(data: bytes):
    seen = set()
    rows = []
    for m in ASCII_RUN.finditer(data):
        key = (m.start(), m.end(), m.group().decode('ascii'))
        if key not in seen:
            seen.add(key); rows.append(key)
    # Find UTF-8 strings by decoding each valid UTF-8 segment; preserve byte offsets.
    # Latin text mixed with CJK is retained as whole runs when it has CJK characters.
    i = 0
    while i < len(data):
        try:
            # Decode a maximal valid UTF-8 sequence from the current byte.
            s = data[i:].decode('utf-8')
            end = len(data)
        except UnicodeDecodeError as e:
            if e.start:
                s = data[i:i+e.start].decode('utf-8', errors='strict')
                end = i+e.start
            else:
                i += max(1, e.end)
                continue
        for m in CJK_RUN.finditer(s):
            # Map character offset to UTF-8 byte offset.
            start_b = i + len(s[:m.start()].encode('utf-8'))
            end_b = i + len(s[:m.end()].encode('utf-8'))
            key = (start_b, end_b, m.group())
            if key not in seen:
                seen.add(key); rows.append(key)
        # Advance after a decode error, or finish after a fully valid tail.
        if end == len(data): break
        i = end + 1
    return sorted(rows)


def load_map(path: Path):
    mapping = []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip('\r\n')
            if not line or line.lstrip().startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) != 2:
                raise ValueError(f'{path}:{line_no}: expected source<TAB>replacement')
            if not parts[0]:
                raise ValueError(f'{path}:{line_no}: empty source string')
            mapping.append((parts[0], parts[1]))
    return mapping


def scan(src: Path, out: Path | None):
    data = src.read_bytes()
    rows = extract_runs(data)
    if out:
        with out.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, delimiter='\t', lineterminator='\n')
            w.writerow(['offset_hex', 'offset_dec', 'byte_length', 'text'])
            for start, end, text in rows:
                w.writerow([f'0x{start:X}', start, end-start, text])
        print(f'Wrote {len(rows)} string candidates to {out}')
    else:
        for start, end, text in rows:
            print(f'0x{start:04X}\t{end-start}\t{text}')


def patch(src: Path, map_path: Path, out: Path):
    data = bytearray(src.read_bytes())
    mapping = load_map(map_path)
    total = 0
    for old, new in mapping:
        old_b = old.encode('utf-8')
        new_b = new.encode('utf-8')
        if len(old_b) != len(new_b):
            raise ValueError(
                f'Cannot safely patch {old!r} -> {new!r}: UTF-8 byte lengths '
                f'differ ({len(old_b)} vs {len(new_b)}). This conservative '
                'patcher preserves all offsets; do not pad or truncate strings.'
            )
        positions = []
        start = 0
        while True:
            idx = data.find(old_b, start)
            if idx < 0: break
            positions.append(idx)
            start = idx + len(old_b)
        if not positions:
            print(f'WARNING: not found: {old!r}', file=sys.stderr)
            continue
        for idx in positions:
            data[idx:idx+len(old_b)] = new_b
        total += len(positions)
        print(f'{old!r} -> {new!r}: {len(positions)} occurrence(s)')
    out.write_bytes(data)
    print(f'Wrote {out} ({len(data)} bytes unchanged size); patched {total} occurrence(s).')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_scan = sub.add_parser('scan', help='export candidate UTF-8/ASCII strings')
    p_scan.add_argument('input', type=Path)
    p_scan.add_argument('-o', '--output', type=Path)
    p_patch = sub.add_parser('patch', help='apply equal-byte-length UTF-8 replacements')
    p_patch.add_argument('input', type=Path)
    p_patch.add_argument('map', type=Path)
    p_patch.add_argument('-o', '--output', type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == 'scan': scan(args.input, args.output)
    else: patch(args.input, args.map, args.output)

if __name__ == '__main__':
    main()
