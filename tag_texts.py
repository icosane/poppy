#!/usr/bin/env python3
"""
tag_texts.py - translate text that lives inside TAGS rather than <text> lines:
    <autosaverange 【プロローグ０１】>      the scene name shown on the save/load screen (59 values)
    <select 0,0,0:label,1:label,outline:>   choice menus and their prompt (9 menus with labels)

extract writes tag_texts.tsv:   kind <TAB> jp <TAB> en <TAB> uses <TAB> source
    kind = scene | choice.  The English column is pre-filled with drafts:
      scene  - built by rule (Prologue / Chapter / Branch A / name + number; names from name_map.tsv)
      choice - from the PC build's own English where it has one (source "PC"), otherwise my draft ("draft")
    Edit the en column, keep everything else.
apply rewrites the scripts from a (possibly edited) tag_texts.tsv.

Notes
  * Inside <select ...> a comma separates the options, so English labels must not contain ASCII commas.
    apply replaces any comma by a full-width one and tells you.
  * Scene names keep the 【 】 brackets; digits become ASCII ("01").

Usage:
    python3 tag_texts.py extract script_jp tag_texts.tsv [--name-map name_map.tsv]
    python3 tag_texts.py apply   tag_texts.tsv --src-dir script_en --out-dir script_en2
"""
import os
import re
import shutil
import sys
import unicodedata

ENC = "cp932"
SELECT = re.compile(r"<select\s+([^>]*)>")
SCENE = re.compile(r"<autosaverange\s+([^>]*)>")

# English for choice labels: "PC" = taken from the PC build's string pool, "draft" = mine (check them)
CHOICES = {
    "やる！": ("Take the offer!", "PC"),
    "このまま話を聞く": ("Keep listening", "draft"),
    "虚勢を張る": ("Put on a bold front", "draft"),
    "去勢をする": ("Neuter myself", "draft"),
    "たくさん食べる人がいい": ("I like girls with big appetites.", "PC"),
    "衣川みたいなのがいい": ("I like girls like Kinugawa.", "PC"),
    "むしろ男がいい": ("Actually I like men.", "PC"),
    "希未を誘う": ("Invite Nozomi.", "PC"),
    "涼花を誘う": ("Invite Suzuka.", "PC"),
    "綾子を誘う": ("Invite Ayako.", "PC"),
    "美卯を誘う": ("Invite Miu.", "PC"),
    "珠祈を誘う": ("Invite Tamaki.", "PC"),
    "たんぽぽを誘う": ("Invite Tampopo.", "PC"),
    "頭を下げたまま話をする": ("Keep talking with my head down.", "PC"),
    "頭を上げて話をする": ("Raise my head and speak.", "PC"),
    "プロローグからはじめる": ("Start at the prologue", "PC"),
    "共通パートから始める": ("Start at the common route", "PC"),
    "プロローグをスキップしますか？": ("Do you want to skip the prologue?", "PC"),
}
WORDS = {"プロローグ": "Prologue", "チャプター": "Chapter", "分岐Ａ": "Branch A", "分岐Ｂ": "Branch B", "ＥＰ": "EP"}


def read_name_map(path):
    m = {}
    if path and os.path.exists(path):
        for l in open(path, encoding="utf-8-sig"):
            c = l.rstrip("\r\n").split("\t")
            if len(c) >= 2 and c[0] and not c[0].startswith("#") and c[1]:
                m[c[0]] = c[1]
    return m


def scene_draft(jp, names):
    inner = jp.strip()
    if inner.startswith("【") and inner.endswith("】"):
        inner = inner[1:-1]
    num = ""
    mnum = re.search(r"([０-９]+)$", inner)
    if mnum:
        num = unicodedata.normalize("NFKC", mnum.group(1))
        inner = inner[:mnum.start()]
    word = inner.replace("\u3000", "").strip()
    if word.endswith("ＥＰ"):
        word, num = word[:-2], "EP"
    word = WORDS.get(word, names.get(word, word))
    return "【" + (word + " " + num).strip() + "】"


def iter_script_files(d):
    for root, _, files in os.walk(d):
        for fn in sorted(files):
            if fn.lower().endswith(".txt"):
                yield os.path.join(root, fn)


def split_args(arg):
    return arg.split(",")


def labels_of(arg):
    out = []
    for part in split_args(arg):
        m = re.match(r"^(\d+|outline):(.*)$", part)
        if m and m.group(2):
            out.append(m.group(2))
    return out


def cmd_extract(src, tsv, name_map):
    names = read_name_map(name_map)
    scenes, choices = {}, {}
    for path in iter_script_files(src):
        t = open(path, "rb").read().decode(ENC, errors="replace")
        for m in SCENE.finditer(t):
            scenes[m.group(1)] = scenes.get(m.group(1), 0) + 1
        for m in SELECT.finditer(t):
            for lab in labels_of(m.group(1)):
                choices[lab] = choices.get(lab, 0) + 1
    with open(tsv, "w", encoding="utf-8", newline="") as f:
        f.write("kind\tjp\ten\tuses\tsource\n")
        for jp, n in scenes.items():
            f.write(f"scene\t{jp}\t{scene_draft(jp, names)}\t{n}\trule\n")
        for jp, n in choices.items():
            en, src_ = CHOICES.get(jp, ("", "NONE"))
            f.write(f"choice\t{jp}\t{en}\t{n}\t{src_}\n")
    print(f"{len(scenes)} scene names, {len(choices)} choice labels -> {tsv}")
    missing = [j for j in choices if j not in CHOICES]
    if missing:
        print("choice labels with no draft (fill them in):", missing)


def cmd_apply(tsv, src, out):
    scene_map, choice_map = {}, {}
    for l in open(tsv, encoding="utf-8-sig").read().replace("\r\n", "\n").split("\n")[1:]:
        c = l.split("\t")
        if len(c) >= 3 and c[2].strip():
            (scene_map if c[0] == "scene" else choice_map)[c[1]] = c[2].strip()
    if os.path.abspath(src) != os.path.abspath(out):
        if os.path.exists(out):
            shutil.rmtree(out)
        shutil.copytree(src, out)
    n_scene = n_choice = 0

    def scene_sub(m):
        nonlocal n_scene
        en = scene_map.get(m.group(1))
        if en is None:
            return m.group(0)
        n_scene += 1
        return "<autosaverange " + en + ">"

    def select_sub(m):
        nonlocal n_choice
        parts = split_args(m.group(1))
        for i, part in enumerate(parts):
            mm = re.match(r"^(\d+|outline):(.*)$", part)
            if mm and mm.group(2) in choice_map:
                en = choice_map[mm.group(2)]
                if "," in en:
                    print(f"  note: comma in choice '{en}' replaced by a full-width comma (commas separate options)")
                    en = en.replace(",", "，")
                parts[i] = mm.group(1) + ":" + en
                n_choice += 1
        return "<select " + ",".join(parts) + ">"

    for path in iter_script_files(out):
        raw = open(path, "rb").read()
        t = raw.decode(ENC, errors="surrogateescape")
        new = SELECT.sub(select_sub, SCENE.sub(scene_sub, t))
        if new != t:
            open(path, "wb").write(new.encode(ENC, errors="surrogateescape"))
    print(f"scene names replaced: {n_scene}, choice labels replaced: {n_choice} -> {out}")


def main():
    a = sys.argv[1:]
    nm = None
    if "--name-map" in a:
        i = a.index("--name-map"); nm = a[i + 1]; del a[i:i + 2]
    if a and a[0] == "extract" and len(a) >= 3:
        cmd_extract(a[1], a[2], nm)
    elif a and a[0] == "apply" and "--src-dir" in a and "--out-dir" in a:
        cmd_apply(a[1], a[a.index("--src-dir") + 1], a[a.index("--out-dir") + 1])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
