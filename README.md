# LOVEPICAL-POPPY! Switch translation toolkit (Switch script.arc + PC reference)

All scripts sit in this one folder.<br>
Extra packages are required only for two optional tools: `pip install pillow numpy fonttools`.

> All the scripts in this repository were written and debugged by AI (ChatGPT, Claude). The Switch version has some lines that are not in the PC version—these were translated by AI. If you are not comfortable using AI-generated work, please skip this repository.

> This repository contains Python tools and build instructions only. It does **not** include the game, the original `script.arc`, or the final translated script files. Use it with script files extracted from a legal copy of the game.

# Game version
TitleID: `010008e02632e000` <br>
Version: 1.0.0

# Other games known to utilize the same engine
#### Ren'ai 恋愛0キロメートル / Ren'ai 0 Kilometer Switch version <br>
Tested: unpacking `script.arc`

---

# Getting EN script.arc
Requirements: Python 3.10+; no third-party packages are required for the build.

1. Obtain the original Switch `romfs/script/script.arc`. 
2. Run the builder directly on that archive:

   ```sh
   python build_v6_7_11.py path/to/original/script.arc script_v6_7_11.arc
   ```

   The builder calls `custom_arc.py extract`, which automatically creates `_index.txt` from the original archive entry order. Existing ZIP bundles are also accepted if they contain `script_sw/` with the extracted `.txt` scripts and the matching `_index.txt`.

3. The builder restores the frozen review checkpoint from `build_v6_7_11.py`, runs alignment application and post-processing, applies scene/choice translations and the final correction patch, removes the unsupported italic markup, then packs and verifies the archive.

4. The build succeeds only if the final archive SHA-256 matches the canonical v6.7.11 output:

   `1531be04232fdd3fc088d5943c19f3e2922dde1122fde966d1185ec5f5eca7ea`

   Expected size: 5,209,588 bytes; 98 archive entries. If the hash differs, the script stops with a mismatch instead of claiming reproducibility.

`--keep-work` retains intermediate files beside the output as `<output>.build_work` for inspection. The embedded review checkpoint is a frozen historical input, not a rerun of the original heuristic matching process.

### What this verifies — and what it does not

- The builder validates the embedded review checkpoint hash and checks the final archive against the canonical SHA-256.
- `custom_arc.py verify` checks that the resulting archive can be extracted and repacked byte-for-byte.
- These checks establish reproducibility and archive integrity, not translation accuracy, compatibility with every game version, or in-game rendering/progression. Those still require in-game testing.
- The final correction patch captures the small set of manual edits that were not represented by the frozen Pass 5 review checkpoint alone.

### Workflow tools

- `custom_arc.py` — List, extract, pack, and verify Switch `script.arc` archives.
- `align_apply.py` — Apply non-empty English drafts from a review TSV to matching Japanese strings.
- `script_postprocess.py` — Speaker-name mapping, default player name, quote/comma compatibility, and text sizing.
- `tag_texts.py` — Scene labels and embedded menu labels.
- `apply_choice_translations.py` — Apply reviewed PC-derived choice labels.
- `strip_italic_tags.py` — Remove unsupported italic markup while preserving enclosed text.

---

# Manual step-by-step workflow
Folder names used below: `script_jp` (untouched Japanese) -> `script_en` (translated) -> `script_ready` (post-processed) -> `script_final` (ready to pack). Never edit `script_jp`.

## A. Prepare (once)
1. **Extract the Switch archive** (and check that it is read correctly):

       python3 custom_arc.py verify  script.arc          # must say OK
       python3 custom_arc.py extract script.arc script_jp

2. **PC reference strings** (the English text to be borrowed):

       python3 bgi_arc.py extract-all "<PC data folder>" pc_extracted     # extracts every data*.arc
       python3 pc_prepare.py pc_extracted pc_strings                       # outputs to *_strings.txt
   If two PC scripts share a basename, outputs are prefixed with their parent folder (e.g., `data01600.en__001_prologue_01_strings.txt`) so they are never overwritten. <br>
   Matching PC files to Switch files is a manual process: compare the first lines. For example, PC `001_prologue_01` corresponds to Switch `001_prologue_01.txt`.
3. **Speaker-name map** (all 192 names):

       python3 build_name_map.py --switch-dir script_jp --pc-dir pc_strings --out name_map.tsv

   Open `name_map.tsv` and fix rows marked `CHECK` (most used first; the tool prints the list). Custom rows are preserved on re-runs. Never add `主人公（名）` / `主人公（姓）` (see Notes: Player name).

## B. Translate (repeat per chapter / file)
4. **Align** one Switch file against its PC strings:

       python3 align_extract.py --switch script_jp/001_prologue_01.txt --pc pc_strings/001_prologue_01_strings.txt --out-review review.tsv

   To diagnose every `NO-MATCH` row against ALL extracted PC strings (not only the chapter's selected PC file):

       python3 diagnose_nomatch.py review.tsv --pc-dir pc_strings --out no_match_diagnostics.tsv --top 10

   The report writes up to 10 candidate English strings per missing row, complete with source dump, line number, and a heuristic score. It boosts candidates found between neighboring matched English lines in the same PC dump. This serves as a triage aid rather than a semantic translation; candidates must be manually verified against the PC game. Re-run `pc_prepare.py` after updating the toolkit so colliding basenames are preserved separately.

   **Extraction note:** `bgi_strings.py` treats Unicode whitespace (including the Shift-JIS full-width space sometimes attached to an English line) as valid whitespace. Without this, it can silently discard a real line if that character is not separated by a null byte.

5. **Review `review.tsv`** (tab-separated format; edit using any text editor or spreadsheet, and save as UTF-8 tab-separated). 
   Edit only the `english_draft` column. Keep the original row order. Leaving it empty means the line stays Japanese. `CHECK`/`NO-MATCH` rows require manual inspection, and an `OK` row is not definitive proof (very short lines can occasionally be paired one off). `OK (VOICE ID)` means the Switch voice ID and a nearby PC voice/message ID match; this serves as a stronger alignment anchor, but the English should still be reviewed. 

   The final columns retain the Switch voice ID/speaker and PC voice ID/source/line for debugging. Both `「…」` and `『…』` are classified as speech. Bare PC labels such as `Map App` and `Waitress A` are excluded from the dialogue pool; unquoted PC strings must end like a sentence. Voice-ID matches with extreme text-shape conflicts and explicit ID conflicts are flagged as `CHECK` because voice IDs can be reused. Keep English lines under ~170 bytes.

6. **Apply the changes.** The first time, read from `script_jp`. For subsequent files, read and write to `script_en` so progress accumulates:

       python3 align_apply.py review.tsv --src-dir script_jp --out-dir script_en       # first file
       python3 align_apply.py review.tsv --src-dir script_en --out-dir script_en       # subsequent files

   *(Optional: `--quote-style ascii|curly|corner` adds quotes around speech; defaults to none. See Notes: Quotes.)*

## C. Finish (after the last file is prepared for shipping)
7. **Post-process** (handles speaker names, default player name, punctuation, and text size). Always start from `script_en`:

       python3 script_postprocess.py --src-dir script_en --out-dir script_ready

   Defaults: names are pulled from `name_map.tsv`; default player name is set to `Yaotome,Tetsuya`. ASCII double quotes in translated `<text>` lines are converted to single quotes (the tested Switch runtime mishandles double quotes); commas use the configured replacement; font size is set to 27 with long lines stepped down automatically. Use `--quotes keep` to disable quote conversion. Read the output logs: it lists any English lines that remain too long. Fix those in `review.tsv` (steps 5-6) and rerun step 7. **Do not run step 7 directly on `script_ready`**, or font sizes will shrink twice.

8. **Scene names and choice menus** (processes text inside tags, not standalone `<text>` lines):

       python3 tag_texts.py extract script_jp tag_texts.tsv --name-map name_map.tsv
       # (Optional: edit the 'en' column in the generated TSV)
       python3 tag_texts.py apply   tag_texts.tsv --src-dir script_ready --out-dir script_final

9. **Pack, verify, and deploy**:

       python3 custom_arc.py pack   script_final script_new.arc
       python3 custom_arc.py verify script_new.arc

   Rename `script_new.arc` to exactly `script.arc`, place it at `atmosphere/contents/<TitleID>/romfs/script/script.arc` (matching the original path structure), and fully restart the emulator/console. Test using a **NEW** game save.

## D. Optional extras (independent steps; deploy results next to script.arc in romfs)
- **System text / menus** (`system_mes.mul`, `sysgra_mes.mul`; forces existing English across all regions):

      python3 mul_tool.py extract sysgra_mes.mul sysgra_mes.tsv          # edit the en column (rows with status EN=JP)
      python3 mul_tool.py build   sysgra_mes.tsv sysgra_mes.mul --like original_sysgra_mes.mul --force-english

- **Images** (`*.ext.gz`):

      python3 ext_tool.py unpack sys_title_01.ext.gz        # extracts to .png and .ext.hdr (keep the .hdr beside the png)
      python3 ext_tool.py pack   sys_title_01.png           # packs back to sys_title_01.ext.gz
      python3 ext_tool.py verify sys_title_01.ext.gz

- **Font patch** (makes `，` look like a normal comma; use with `--comma fullwidth` in step 7):

      python3 font_tool.py narrow-comma font_00.ttf.gz font_00_patched.ttf.gz     # replace original file using the same name

- **Text Locator** (search a full romfs dump, including inside `.gz` files):

      python3 find_text.py romfs_dump プロローグ

- **Engine comma/quote test** (injects 8 labeled variants into the prologue):

      python3 make_text_test.py --src-dir script_jp --out-dir script_texttest
      python3 custom_arc.py pack script_texttest script_text_test.arc

---

# ADDITIONAL NOTES (Reference)

## Tools Overview

| File Name | Role |
| :--- | :--- |
| `custom_arc.py` | Switch `script.arc`: list / extract / pack / verify (rebuilds real archives byte-for-byte) |
| `bgi_arc.py`, `dsc_codec.py`, `bgi_strings.py`, `pc_prepare.py` | PC tools: handles archives, DSC decompression, string dumping, and batch utilities |
| `build_name_map.py` | Generates `name_map.tsv` for speakers (flags low-confidence rows with `CHECK`) |
| `align_extract.py` / `align_apply.py` | Aligns Switch JP lines with PC EN strings and writes reviewed English back |
| `script_postprocess.py` | Handles speaker names, default player name, commas, text size, and long-line warnings |
| `tag_texts.py` | Processes scene names (`<autosaverange>`) and choice menus (`<select>`) |
| `mul_tool.py`, `ext_tool.py`, `font_tool.py` | Modifies system text tables, images, and applies font patches |
| `make_text_test.py`, `find_text.py` | Runs in-game comma/quote tests and acts as a global text finder |

## Player name
`00_init.txt` contains `<setsubstitutionname 0,主人公（姓）,主人公（名）>`. The engine swaps these two specific tokens for the name entered at the New Game screen. Writing literal text like "Protag(First)" freezes the name permanently, so the tools leave these tokens untouched (the post-processor prints a before/after count to verify). 

The default name (`<setdefaultname 0,八乙女,哲也>`) is plain text: step 7 writes `Yaotome,Tetsuya` (family name, given name, matching the PC build; customize via `--default-name`). The name-entry window interface itself is rendered via graphics.

## Commas and quotes
- The Switch engine silently drops ASCII commas inside `<text ...>` lines (no original Japanese line utilized them). Step 7 rewrites them using specified behaviors:
  `--comma halfwidth` (default; `､` is 0.50 em wide, looking like a small `、`), `fullwidth` (`，` is 1.00 em wide and leaves a noticeable gap unless the font is patched), `fullwidth-tight` (full-width but drops the trailing space), `backslash`, `quote`, or `keep`.
  Width measurements in the game's font (Noto Sans JP Medium) are: ASCII comma = 0.30 em, `､` = 0.50 em, `，` = 1.00 em. Visual comparisons can be viewed in `comma_compare.png`.
- `font_tool.py narrow-comma` remaps `，` to a standard comma glyph, making `--comma fullwidth` render identically to the PC version. 
- Quotes: The PC localization uses standard `"..."` for dialogue, while the Switch engine uses native Japanese `「」`. English text is written without quotes by default. `align_apply.py --quote-style` can add them automatically; run `make_text_test.py` first to see which style renders best on screen.
- Inside `<select>` tags, a comma splits menu choices. Consequently, choice labels cannot contain raw commas (`tag_texts.py` strips or converts them automatically).

## Text size
- Only ~3% of dialogue lines (888 out of 28,611) contain explicit `<font size:N>` tags; 97% inherit the engine default, which is not defined in the scripts.
- Original developer usage patterns: 45/40/38 for short exclamation shouts, 33/35 for general shouting, and 28-30 to squeeze long lines into bounds. The default base size is roughly 32.
- Step 7 assigns every translated line an explicit `<font size:27>` tag. Long lines step down progressively (>90 chars decreases by 3, >130 chars decreases by 5, >170 chars decreases by 8) and scales existing explicit sizes down by 3. Available options include: `--base N` (0 keeps default values), `--no-fit`, `--fit-steps`, and `--shrink N`.

## Crash on the emulator
There are known reports of crashes (invalid memory access). This is unresolved, but current findings indicate:
- The game font contains every character used in the English translation, ruling out missing glyph assets as the root cause.
- The longest original Japanese `<text>` line spans 178 bytes. A few English lines exceed this limit (e.g., 200/191/185 bytes in the prologue chapter). Step 7 logs every line exceeding 178 bytes; shortening these is recommended as a fixed-size log buffer allocation is the leading theory.
- Utilizing half-width commas/patched font resolved the crash in one instance, though this may be coincidental. Test backlog stability across the entire prologue to verify.
- Double quotes also caused a crash on one line.

## Scene names (save/load screen)
Scene names are stored in `<autosaverange 【...】>` tags inside `root_Common.txt` and `root_*.txt` before the respective scene is loaded. The current toolkit build translates all **59 scene-name entries** (e.g., `【プロローグ０１】` → `【Prologue 01】`). This mapping applies directly to the final release scripts, covering 59 unique scene labels across 63 structural tag occurrences.

## Format notes
*   **Switch script.arc structure:** `uint32 data_start (=8+count*72) | uint32 count`, followed by count x `[name 64 bytes (NUL, 0xFE fill) | uint32 size | uint32 absolute offset]`. File data begins at `data_start`. Each file ends with a `NUL` byte and pads out to an 8-byte alignment boundary. The last file terminates at the exact end of the archive. Text encoding uses `cp932`.
*   **`.mul` structure:** 48-byte header block `[(groups<<8)|4, record_count, group sizes...]`, records structured as `(offset, length)`. Text format is UTF-8, containing 4 language tracks per message entry (JP, EN, zh-Hans, zh-Hant). `#n` denotes a line break.
*   **`.ext.gz` structure:** Gzip archive containing a 256-byte header (`EXT0`, float offsets, width, height, inner size, -9999, -9999, 32 bpp, etc.) alongside raw BGRA pixels utilizing premultiplied alpha channels.

## Lessons learned
- Character names, scene headers, and selection menus reside strictly inside tags. Scoping searches to standalone `<text>` lines will miss them.
- ASCII commas vanish completely in `<text>` blocks, while raw commas inside `<select>` blocks break menu logic.
- Explicit size tags affect only 3% of lines; reducing values globally is required to impact general layout layout constraints.
- Legacy iterations of `custom_arc.py` misaligned file naming pairs with adjacent offset sizes; ensure this current version is used.

### Translation status and known limits

- The consolidated review pipeline contains 28,619 entries with zero empty English draft placeholders. Select entries have been translated from scratch rather than pulled from the PC localization; tracking statuses inside the TSV preserve this history.
- Corrected entries handle localized metrics for follower milestones, childcare/caregiver references, special-privilege story consequences, and curiosity dialogue tracks. The existing PC localization adaptations like `W H A T  T H E  C L U C K ! ?` and `Y'all grannies or somethin'!?` have been preserved deliberately.
- This toolkit provides personal-use translation candidates. It does not imply that every text line has been manually proofread or verified throughout a full 30–50 hour playthrough. Backlog text behavior and unexpected text clipping still require targeted in-game evaluation.

## Known limitations
- String alignment relies on a heuristic approach; status labels and matching voice IDs do not constitute absolute semantic proof.
- The compiled PC string asset pool strips out certain control-flow execution contexts, making choice menus, duplicate lines, and generalized reactions difficult to align with absolute certainty.
- No guarantees are made regarding individual translation accuracy or total stability throughout a full playthrough.
