#!/usr/bin/env python3
from pathlib import Path
p=Path('scripts/replay_track1_personas.mjs')
s=p.read_text(encoding='utf-8')
replacements={
    '(root?.12:0)':'(root ? .12 : 0)',
    "const ranked=[...[occ.regulatedSkills,9],...[occ.essentialSkills,8],...[occ.optionalSkills,7],...[occ.calculatedSkills,6],...[related,4]];":"const ranked=[[occ.regulatedSkills,9],[occ.essentialSkills,8],[occ.optionalSkills,7],[occ.calculatedSkills,6],[related,4]];",
}
for old,new in replacements.items():
    if old in s:
        s=s.replace(old,new,1)
    elif new not in s:
        raise RuntimeError(f'persona replay patch anchor missing: {old}')
p.write_text(s,encoding='utf-8')
print('track1 persona replay harness fixed')
