#!/usr/bin/env python3
from pathlib import Path
p=Path('scripts/replay_track1_personas.mjs')
s=p.read_text(encoding='utf-8')
old="const ranked=[[occ.regulatedSkills,9],[occ.essentialSkills,8],[occ.optionalSkills,7],[occ.calculatedSkills,6],[related,4]];const out=[],seen=new Set();for(const [id,rank] of ranked){if(seen.has(id)||!this.base.skills[id])continue;seen.add(id);out.push({id,preferred_label:this.base.skills[id],rank});if(out.length>=max)break;}return out.length?"
new="const groups=[[occ.regulatedSkills,9],[occ.essentialSkills,8],[occ.optionalSkills,7],[occ.calculatedSkills,6],[related,4]];const out=[],seen=new Set();outer:for(const [skillIds,rank] of groups){for(const id of skillIds){if(seen.has(id)||!this.base.skills[id])continue;seen.add(id);out.push({id,preferred_label:this.base.skills[id],rank});if(out.length>=max)break outer;}}return out.length?"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise RuntimeError('KV prioritized replay anchor drift')
p.write_text(s,encoding='utf-8')
print('corrected KV prioritized-list replay')
