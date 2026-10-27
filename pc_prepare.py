#!/usr/bin/env python3
"""Batch-extract readable strings from BGI/Ethornell compiled scripts.

Usage: python pc_prepare.py <extracted_dir> <out_dir>
Only reads full file contents for files with the DSC/script magic header.
Shows scan progress, so large folders containing images/audio don't look frozen.
"""
import os
import sys
from dsc_codec import decompress, MAGIC
from bgi_strings import extract_strings

SCRIPT_MAGIC = b"BurikoCompiledScriptVer"

def main():
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    src, out = sys.argv[1], sys.argv[2]
    if not os.path.isdir(src):
        print(f"ERROR: input directory does not exist: {src}", file=sys.stderr)
        raise SystemExit(2)
    os.makedirs(out, exist_ok=True)

    candidates = []
    scanned = 0
    print(f"Scanning: {os.path.abspath(src)}", flush=True)
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for name in sorted(files):
            scanned += 1
            path = os.path.join(root, name)
            try:
                with open(path, 'rb') as f:
                    header = f.read(16)
            except OSError as e:
                print(f"SKIP unreadable {path}: {e}", flush=True)
                continue
            if header == MAGIC or header.startswith(SCRIPT_MAGIC):
                candidates.append((path, name))
            if scanned % 250 == 0:
                print(f"Scanned {scanned} files; found {len(candidates)} possible scripts...", flush=True)
    print(f"Scan complete: {scanned} files, {len(candidates)} possible scripts. Extracting...", flush=True)

    by_name = {}
    for path, name in candidates:
        by_name.setdefault(name, []).append(path)

    done = 0
    for i, (path, name) in enumerate(candidates, 1):
        try:
            with open(path, 'rb') as f:
                data = f.read()
            if data[:16] == MAGIC:
                data = decompress(data)
            if not data.startswith(SCRIPT_MAGIC):
                print(f"SKIP {path}: decompressed data lacks script header", flush=True)
                continue
            if len(by_name[name]) == 1:
                out_name = name + "_strings.txt"
            else:
                rel_parent = os.path.relpath(os.path.dirname(path), src)
                prefix = rel_parent.replace(os.sep, "__")
                out_name = prefix + "__" + name + "_strings.txt"
            strings = extract_strings(data)
            target = os.path.join(out, out_name)
            with open(target, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(strings) + ('\n' if strings else ''))
            print(f"[{i}/{len(candidates)}] {path}: {len(strings)} strings -> {target}", flush=True)
            done += 1
        except Exception as e:
            print(f"ERROR {path}: {type(e).__name__}: {e}", flush=True)
    print(f"Done: processed {done} script file(s); scanned {scanned} total files.", flush=True)

if __name__ == '__main__':
    main()
