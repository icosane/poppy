#!/usr/bin/env python3
"""Apply PC-English equivalents to embedded Switch <select ...> menu labels.

This is deliberately separate from align_apply.py because menu labels are embedded
inside <select> tags, not ordinary <text> nodes. It changes only explicitly mapped
labels and preserves numeric choice indices and all other tag fields.
"""
from pathlib import Path
import argparse, csv, re

# Exact PC script choice strings, mapped by Switch script and menu order.
MAPS = {
 '001_prologue_01.txt': [
   ['Take the offer!', 'Take the offer!', 'Take the offer!'],
   ['Let them continue talking.', 'Lose your shit.', 'Get castrated.'],
 ],
 '003_com01.txt': [['I like girls with big appetites.', 'I like girls like Kinugawa.', 'Actually, I like men.']],
 '011_branch_a2.txt': [['Invite Nozomi.', 'Invite Suzuka.', 'Invite Ayako.']],
 '013_branch_b2.txt': [['Invite Miu.', 'Invite Tamaki.', 'Invite Tanpopo.']],
 '407_NOZOMI_07.txt': [['Keep talking with my head down.', 'Raise my head and speak.']],
 'op_skip.txt': [['Start at the prologue', 'Start at the common route', 'Do you want to skip the prologue?']],
}
ENC='cp932'
TAG_RE = re.compile(rb'<select ([^>]+)>', re.I)

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--src-dir',default='script_final'); ap.add_argument('--jp-dir',default='script_jp'); ap.add_argument('--out-dir',default='script_v6_7'); ap.add_argument('--review',default='choice_review.tsv'); a=ap.parse_args()
 src=Path(a.src_dir); jpdir=Path(a.jp_dir); out=Path(a.out_dir)
 if out.exists():
  import shutil; shutil.rmtree(out)
 import shutil; shutil.copytree(src,out)
 rows=[]; applied=0
 for filename, menus in MAPS.items():
  p=out/filename
  if not p.exists():
   # Allow source bundles whose extracted file casing differs.
   matches=[x for x in out.iterdir() if x.name.lower()==filename.lower()]
   if not matches: raise FileNotFoundError(f'Missing {filename} in {out}')
   p=matches[0]
  data=p.read_bytes(); jp_path=next((x for x in jpdir.iterdir() if x.name.lower()==filename.lower()), None)
  if jp_path is None: raise FileNotFoundError(f'Missing Japanese source {filename} in {jpdir}')
  jp_data=jp_path.read_bytes(); jp_tags=list(TAG_RE.finditer(jp_data)); jp_menu_i=0; menu_i=0
  def repl(m):
   nonlocal menu_i, applied, jp_menu_i
   raw=m.group(1)
   if not re.search(rb'\d+:',raw): return m.group(0)
   if menu_i >= len(menus): return m.group(0)
   menu=menus[menu_i]; menu_i+=1
   jp_match=None
   for jm in jp_tags[jp_menu_i:]:
    if re.search(rb'\d+:',jm.group(1)):
     jp_match=jm; jp_menu_i=jp_tags.index(jm)+1; break
   jp_options=[]
   if jp_match:
    jp_options=[x.decode(ENC) for x in re.findall(rb'\d+:([^,]*)(?=,|$)',jp_match.group(1))]
   # Option text is encoded after N: and before the next comma; outline is optional.
   s=raw
   opt_i=0
   def opt_repl(om):
    nonlocal opt_i, applied
    idx=om.group(1).decode('ascii'); old=om.group(2).decode(ENC)
    if opt_i >= len(menu): return om.group(0)
    new=menu[opt_i]; jp_old=jp_options[opt_i] if opt_i < len(jp_options) else old; opt_i+=1; applied+=1
    rows.append({'switch_file':filename,'menu_index':menu_i-1,'option_index':idx,'japanese':jp_old,'english_pc':new,'status':'APPLIED (PC string evidence)'})
    return idx.encode()+b':'+new.encode(ENC)
   s=re.sub(rb'(?<![A-Za-z0-9])(\d+):([^,]*)(?=,|$)',opt_repl,s)
   # outline: is displayed text in op_skip; map it only for the known PC menu.
   if filename.lower()=='op_skip.txt' and b'outline:' in s:
    old=s.split(b'outline:',1)[1].decode(ENC)
    jp_outline=''
    if jp_match and b'outline:' in jp_match.group(1): jp_outline=jp_match.group(1).split(b'outline:',1)[1].decode(ENC)
    new='Do you want to skip the prologue?' 
    s=s.split(b'outline:',1)[0]+b'outline:'+new.encode(ENC)
    rows.append({'switch_file':filename,'menu_index':menu_i-1,'option_index':'outline','japanese':jp_outline or old,'english_pc':new,'status':'APPLIED (PC string evidence)'})
    applied+=1
   return b'<select '+s+b'>'
  data=TAG_RE.sub(repl,data)
  if menu_i != len(menus): raise RuntimeError(f'{filename}: expected {len(menus)} mapped menus, found {menu_i}')
  p.write_bytes(data)
 with open(a.review,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['switch_file','menu_index','option_index','japanese','english_pc','status'],delimiter='\t'); w.writeheader(); w.writerows(rows)
 print(f'Applied {applied} menu labels across {len(MAPS)} files. Review: {a.review}')
if __name__=='__main__': main()
