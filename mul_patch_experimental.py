#!/usr/bin/env python3
"""Experimental fixed-size Japanese->English patcher for sysgra_mes.mul.

This intentionally does NOT change file size or offsets. Each replacement is
written at the same byte width as the Japanese source and padded on the right
with ASCII spaces. This is a reversible TEST patch, not a proven format-aware
repacker. Always keep the original file.

Usage:
  python mul_patch_experimental.py patch sysgra_mes.mul ui_map.tsv -o sysgra_mes_test.mul
  python mul_patch_experimental.py verify sysgra_mes.mul sysgra_mes_test.mul ui_map.tsv
Map format: source<TAB>replacement, UTF-8, # comments allowed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys


def load_map(path: Path):
    rows=[]
    for n,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts=line.split('\t')
        if len(parts)!=2 or not parts[0]:
            raise ValueError(f'{path}:{n}: expected source<TAB>replacement')
        old,new=parts
        ob,nb=old.encode('utf-8'),new.encode('utf-8')
        if len(nb)>len(ob):
            raise ValueError(f'{path}:{n}: replacement longer than source in UTF-8 ({len(nb)} > {len(ob)}): {old!r} -> {new!r}')
        rows.append((old,new,ob,nb))
    return sorted(rows, key=lambda row: len(row[2]), reverse=True)


def patch(src: Path, mapping_path: Path, out: Path):
    original=src.read_bytes()
    data=bytearray(original)
    total=0
    for old,new,ob,nb in load_map(mapping_path):
        count=data.count(ob)
        if not count:
            print(f'NOT FOUND: {old!r}', file=sys.stderr)
            continue
        # Equal-width replacement; padding is confined to the source byte span.
        replacement=nb+b' '*(len(ob)-len(nb))
        data=data.replace(ob,replacement)
        total+=count
        print(f'{old} -> {new}: {count} occurrence(s), {len(ob)} bytes preserved')
    if len(data)!=len(original):
        raise RuntimeError('Internal error: output size changed')
    out.write_bytes(data)
    print(f'Wrote {out}; size {len(data)} bytes (original {len(original)}); {total} replacements.')


def verify(original_path: Path, patched_path: Path, mapping_path: Path):
    a=original_path.read_bytes(); b=patched_path.read_bytes()
    if len(a)!=len(b):
        raise SystemExit(f'FAIL: size differs: {len(a)} vs {len(b)}')
    mapping=load_map(mapping_path)
    failed=[]
    for old,new,ob,nb in mapping:
        expected=nb+b' '*(len(ob)-len(nb))
        if expected not in b:
            # It may have been replaced more than once or be absent in source.
            if ob in a:
                failed.append((old,new))
    if failed:
        for old,new in failed: print(f'CHECK: expected padded replacement not found: {old!r} -> {new!r}')
        raise SystemExit('Verify completed with checks; inspect the file in-game.')
    print(f'PASS: same file size ({len(a)} bytes); map replacements look present.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('patch'); p.add_argument('input',type=Path); p.add_argument('map',type=Path); p.add_argument('-o','--output',type=Path,required=True)
    v=sub.add_parser('verify'); v.add_argument('original',type=Path); v.add_argument('patched',type=Path); v.add_argument('map',type=Path)
    args=ap.parse_args()
    if args.cmd=='patch': patch(args.input,args.map,args.output)
    else: verify(args.original,args.patched,args.map)
if __name__=='__main__': main()
