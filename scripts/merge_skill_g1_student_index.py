#!/usr/bin/env python3
"""Merge separately compiled C0/G1 postings into one dual-score static index."""
import gzip, hashlib, json
from pathlib import Path

def compact(x): return (json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n').encode()

def merge(c0, g1, lane_name):
    if c0['document_ids']!=g1['document_ids'] or c0['exact_surfaces']!=g1['exact_surfaces']: raise RuntimeError('lane identity/surface drift')
    terms=sorted(set(c0['postings'])|set(g1['postings'])); merged={}
    for term in terms:
        rows={}
        for o,s in c0['postings'].get(term,[]): rows[int(o)]=[float(s),0.0]
        for o,s in g1['postings'].get(term,[]): rows.setdefault(int(o),[0.0,0.0])[1]=float(s)
        merged[term]=[[o,v[0],v[1]] for o,v in sorted(rows.items())]
    return {'schema_version':1,'engine':'dual-precomputed-bm25-postings','lanes':['KV-C0',lane_name],'document_ids':c0['document_ids'],'postings':merged,'exact_surfaces':c0['exact_surfaces'],'runtime':'single unique-token pass; each posting carries precomputed C0 and G1 contribution; exact boost both; fuse C0 rank1 + four G1 candidates','runtime_dependencies':[]}

def write(d, filename, asset):
    b=compact(asset); (d/f'{filename}.json').write_bytes(b); stats={'raw_bytes':len(b),'gzip9_bytes':len(gzip.compress(b,9,mtime=0)),'terms':len(asset['postings']),'postings':sum(len(x) for x in asset['postings'].values()),'sha256':hashlib.sha256(b).hexdigest()}; (d/f'{filename}-size.json').write_text(json.dumps(stats,indent=2,sort_keys=True)+'\n'); return stats

def main():
    d=Path('artifacts/skill-g1-student-runtime-v31'); c0=json.loads((d/'c0.json').read_text()); g1=json.loads((d/'g1.json').read_text()); prod=json.loads((d/'g1-production-shape.json').read_text())
    validation_stats=write(d,'dual',merge(c0,g1,'KV-G1-single-desc'))
    production_stats=write(d,'dual-production-shape',merge(c0,prod,'KV-G1-single-desc-production-shape'))
    result={'validation_shape':validation_stats,'production_shape':production_stats,'separate_lane_validation_gzip9_bytes':len(gzip.compress(compact(c0),9,mtime=0))+len(gzip.compress(compact(g1),9,mtime=0)),'separate_lane_production_gzip9_bytes':len(gzip.compress(compact(c0),9,mtime=0))+len(gzip.compress(compact(prod),9,mtime=0))}
    (d/'dual-comparison.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print(json.dumps(result,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
