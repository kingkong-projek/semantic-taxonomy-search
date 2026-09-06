#!/usr/bin/env python3
"""Merge separately compiled C0/G1 postings into one dual-score static index."""
import gzip, hashlib, json
from pathlib import Path

def compact(x): return (json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n').encode()

def main():
    d=Path('artifacts/skill-g1-student-runtime-v31'); c0=json.loads((d/'c0.json').read_text()); g1=json.loads((d/'g1.json').read_text())
    if c0['document_ids']!=g1['document_ids'] or c0['exact_surfaces']!=g1['exact_surfaces']: raise RuntimeError('lane identity/surface drift')
    terms=sorted(set(c0['postings'])|set(g1['postings'])); merged={}
    for term in terms:
        rows={}
        for o,s in c0['postings'].get(term,[]): rows[int(o)]=[float(s),0.0]
        for o,s in g1['postings'].get(term,[]): rows.setdefault(int(o),[0.0,0.0])[1]=float(s)
        merged[term]=[[o,v[0],v[1]] for o,v in sorted(rows.items())]
    asset={'schema_version':1,'engine':'dual-precomputed-bm25-postings','lanes':['KV-C0','KV-G1-single-desc'],'document_ids':c0['document_ids'],'postings':merged,'exact_surfaces':c0['exact_surfaces'],'runtime':'single unique-token pass; each posting carries precomputed C0 and G1 contribution; exact boost both; fuse C0 rank1 + four G1 candidates','runtime_dependencies':[]}
    b=compact(asset); (d/'dual.json').write_bytes(b); stats={'raw_bytes':len(b),'gzip9_bytes':len(gzip.compress(b,9,mtime=0)),'terms':len(merged),'postings':sum(len(x) for x in merged.values()),'sha256':hashlib.sha256(b).hexdigest()}
    (d/'dual-size.json').write_text(json.dumps(stats,indent=2,sort_keys=True)+'\n'); print(json.dumps(stats,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
