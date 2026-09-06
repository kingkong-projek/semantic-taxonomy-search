#!/usr/bin/env node
/**
 * Replay the pinned Yrkesväljaren search over the actual published YV v31 row model.
 *
 * Important: YV has two selectable entity types: occupation-name and job-title.
 * A multi-parent job-title is intentionally emitted as 2-3 contextual rows with the
 * same job-title ID and different occupation_name_id. Evaluation therefore treats
 * a job-title row as discovery evidence for its exact parent occupation while also
 * preserving the row identity (job-title ID + occupation parent ID).
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import Fuse from 'fuse.js';

const PINNED_COMMIT = '0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b';
const SEARCH_UTILS_BLOB = '711769d019d01539b958776467e42dbafa46d9c1';
const CONSTANTS_BLOB = 'e9a412778d77de1aef82da94e36559619f5d607c';
const FUSE_VERSION = '7.5.0';
const YV_URL = 'https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json';
const YV_SHA256 = '1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49';
const MAX_WEAK_FUZZY_RESULTS = 3;
const MIN_FUZZY_SCORE = 0.4;
const MAX_FUZZY_SCORE = 0.84;

function normalizeForComparison(text){ return String(text ?? '').toLowerCase().trim(); }
function formatDisplayLabel(item){ return item.occupation_name_preferred_label ? `${item.preferred_label || ''} (${item.occupation_name_preferred_label})` : (item.preferred_label || ''); }
function getDirectScore(label, query, tokens){
  if(label === query) return 1.0;
  if(tokens.length > 1) return tokens.every(t => label.includes(t)) ? 0.98 : null;
  if(label.startsWith(query)) return 0.99;
  if(label.includes(query)) return 0.95;
  return null;
}
function editDistance(a,b){
  const m=a.length,n=b.length; let prev=Array.from({length:n+1},(_,i)=>i);
  for(let i=1;i<=m;i+=1){ const cur=[i,...new Array(n).fill(0)]; for(let j=1;j<=n;j+=1){cur[j]=Math.min(cur[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));} prev=cur; }
  return prev[n];
}
function findBestFuzzySubstring(text,q){
  const lower=text.toLowerCase(), targetLen=q.length; let best=99;
  const minLen=Math.max(3,targetLen-2), maxLen=Math.min(lower.length,targetLen+2);
  for(let start=0;start<=lower.length-minLen;start+=1){
    for(let len=minLen;len<=maxLen && start+len<=lower.length;len+=1){best=Math.min(best,editDistance(q,lower.slice(start,start+len)));}
  }
  const allowed=Math.max(2,Math.floor(targetLen*0.25)); return best<=allowed?best:null;
}
function isSingleWordOrCompoundRoot(query,label){
  const q=query.toLowerCase().trim(), l=label.toLowerCase().trim();
  if(l.includes(' ')){ const d=editDistance(q,l); return d<=Math.max(2,Math.floor(q.length*0.25)) && Math.abs(q.length-l.length)<=2; }
  return findBestFuzzySubstring(l,q)!==null;
}
function sortStrict(results){
  return results.sort((a,b)=>{
    if(a.score!==b.score) return b.score-a.score;
    const aw=a.weight??0,bw=b.weight??0; if(aw!==bw) return bw-aw;
    return a.displayLabel.localeCompare(b.displayLabel,'sv');
  });
}
class PinnedYvSearch {
  constructor(items){
    this.items=items;
    this.fuse=new Fuse(items,{keys:['preferred_label'],includeScore:true,ignoreDiacritics:true,ignoreFieldNorm:true,threshold:0.6,minMatchCharLength:1,ignoreLocation:true,distance:100});
  }
  search(query,maxResults=10){
    if(!query || query.length<1) return [];
    const q=normalizeForComparison(query), tokens=q.split(' ').filter(Boolean), direct=[], seen=new Set();
    for(const item of this.items){
      const score=getDirectScore(normalizeForComparison(item.preferred_label),q,tokens);
      if(score!==null){direct.push({...item,score,displayLabel:formatDisplayLabel(item)});seen.add(`${item.id}|${item.occupation_name_id??''}`);}
    }
    if(direct.length>0) return sortStrict(direct).slice(0,maxResults);
    const raw=this.fuse.search(q); if(raw.length===0)return [];
    const bestRaw=raw[0].score??1, candidates=[]; let strong=false;
    for(const fr of raw){
      const rowKey=`${fr.item.id}|${fr.item.occupation_name_id??''}`; if(seen.has(rowKey))continue;
      const rawScore=fr.score??1, base=1-rawScore; if(base<MIN_FUZZY_SCORE)continue;
      if(rawScore>bestRaw+0.12)continue;
      const label=normalizeForComparison(fr.item.preferred_label), weight=fr.item.weight??0;
      const root=isSingleWordOrCompoundRoot(q,label); if(root&&rawScore<=0.25)strong=true;
      let score=base*0.70+weight*0.10+(root?0.12:0); score=Math.min(MAX_FUZZY_SCORE,Math.max(MIN_FUZZY_SCORE,score));
      candidates.push({...fr.item,score,displayLabel:formatDisplayLabel(fr.item)});seen.add(rowKey);
    }
    const sorted=sortStrict(candidates); if(sorted.length===0)return [];
    return sorted.slice(0,strong?Math.min(5,maxResults):Math.min(MAX_WEAK_FUZZY_RESULTS,maxResults));
  }
}
function readJsonl(path){ return fs.readFileSync(path,'utf8').split(/\n/).filter(Boolean).map(JSON.parse); }
function observedCount(c){ const m=String(c.notes??'').match(/(?:Observed count(?: in frozen source review pool)?|Observed count in source review pool):\s*(\d+)/i); return m?Number(m[1]):1; }
function rowKey(r){ return `${r.id}|${r.occupation_name_id??''}`; }
function discoveryOccupationId(r){ return r.type==='occupation-name'?r.id:(r.type==='job-title'?r.occupation_name_id:null); }
function pct(n,d){ return d?Number((100*n/d).toFixed(3)):0; }

function evaluateJudged(engine,path,name){
  const cases=readJsonl(path); let positive=0,posHit5=0,posHit10=0,noMatch=0,safe=0,weightedNumerator5=0,weightedDenom=0,weightedAllNumerator=0,weightedAllDenom=0;
  const detail=[];
  for(const c of cases){
    const results=engine.search(c.query,10), top5=results.slice(0,5), w=observedCount(c);
    const positives=new Set([...(c.must??[]),...(c.acceptable??[])].filter(x=>x.kind==='occupation-name').map(x=>x.concept_id));
    let success5=false,success10=false;
    if(c.expected_intent==='NO_MATCH'){
      noMatch+=1; success5=results.length===0; success10=success5; safe+=Number(success5);
    } else {
      positive+=1; success5=top5.some(r=>positives.has(discoveryOccupationId(r))); success10=results.some(r=>positives.has(discoveryOccupationId(r))); posHit5+=Number(success5);posHit10+=Number(success10);weightedNumerator5+=w*Number(success5);weightedDenom+=w;
    }
    weightedAllNumerator+=w*Number(success5);weightedAllDenom+=w;
    detail.push({id:c.id,query:c.query,intent:c.expected_intent,observed_count:w,success_at_5:success5,success_at_10:success10,result_count:results.length,top5:top5.map(r=>({type:r.type,id:r.id,label:r.preferred_label,parent_id:r.occupation_name_id??null,parent_label:r.occupation_name_preferred_label??null,score:r.score}))});
  }
  return {name,cases:cases.length,positive_cases:positive,no_match_cases:noMatch,positive_discovery_at_5_pct:pct(posHit5,positive),positive_discovery_at_10_pct:pct(posHit10,positive),positive_weighted_discovery_at_5_pct:pct(weightedNumerator5,weightedDenom),no_match_abstention_pct:pct(safe,noMatch),all_case_weighted_decision_at_5_pct:pct(weightedAllNumerator,weightedAllDenom),detail};
}
function evaluateExcluded(engine){
  const cases=readJsonl('research/benchmark/v31/yv-profile-safety/excluded-routing-review.jsonl');
  let any5=0,any10=0,wAny5=0,wAny10=0,wTotal=0,parentHit5=0,parentTotal=0,parentHit10=0;
  const detail=[];
  for(const c of cases){
    const target=new Set(c.candidate_occupation_identities.map(x=>x.concept_id)),results=engine.search(c.query,10),top5=results.slice(0,5);
    const occ5=new Set(top5.map(discoveryOccupationId).filter(Boolean)),occ10=new Set(results.map(discoveryOccupationId).filter(Boolean));
    const hits5=[...target].filter(x=>occ5.has(x)).length,hits10=[...target].filter(x=>occ10.has(x)).length;
    const a5=hits5>0,a10=hits10>0,w=Number(c.observed_count); any5+=Number(a5);any10+=Number(a10);wAny5+=w*Number(a5);wAny10+=w*Number(a10);wTotal+=w;parentHit5+=hits5;parentHit10+=hits10;parentTotal+=target.size;
    detail.push({id:c.id,query:c.query,reason:c.yv_exclusion_reason,observed_count:w,target_parent_count:target.size,any_parent_at_5:a5,any_parent_at_10:a10,parent_recall_at_5_pct:pct(hits5,target.size),parent_recall_at_10_pct:pct(hits10,target.size),top5:top5.map(r=>({type:r.type,id:r.id,label:r.preferred_label,parent_id:r.occupation_name_id??null,parent_label:r.occupation_name_preferred_label??null}))});
  }
  return {cases:cases.length,observed_volume:wTotal,any_parent_at_5_pct:pct(any5,cases.length),any_parent_at_10_pct:pct(any10,cases.length),weighted_any_parent_at_5_pct:pct(wAny5,wTotal),weighted_any_parent_at_10_pct:pct(wAny10,wTotal),micro_parent_recall_at_5_pct:pct(parentHit5,parentTotal),micro_parent_recall_at_10_pct:pct(parentHit10,parentTotal),detail};
}

async function main(){
  const response=await fetch(YV_URL); if(!response.ok)throw new Error(`YV source HTTP ${response.status}`); const bytes=Buffer.from(await response.arrayBuffer()); const sha=crypto.createHash('sha256').update(bytes).digest('hex'); if(sha!==YV_SHA256)throw new Error(`YV source drift: ${sha}`);
  const doc=JSON.parse(bytes.toString('utf8')),items=doc.data; if(!Array.isArray(items))throw new Error('YV data missing'); const engine=new PinnedYvSearch(items);
  const jt=items.filter(x=>x.type==='job-title'),occ=items.filter(x=>x.type==='occupation-name'),byJt=new Map();
  for(const r of jt){if(!byJt.has(r.id))byJt.set(r.id,[]);byJt.get(r.id).push(r);}
  let jtAll5=0,jtAll10=0,multi=0,multiAll5=0,multiAll10=0,occHit5=0;
  for(const rows of byJt.values()){
    const results=engine.search(rows[0].preferred_label,10),keys5=new Set(results.slice(0,5).map(rowKey)),keys10=new Set(results.map(rowKey)),expected=rows.map(rowKey);
    const a5=expected.every(k=>keys5.has(k)),a10=expected.every(k=>keys10.has(k));jtAll5+=Number(a5);jtAll10+=Number(a10);
    if(rows.length>1){multi+=1;multiAll5+=Number(a5);multiAll10+=Number(a10);}
  }
  for(const r of occ){const results=engine.search(r.preferred_label,10);occHit5+=Number(results.slice(0,5).some(x=>x.type==='occupation-name'&&x.id===r.id));}
  const judged=[
    ['pareto-development','research/benchmark/v31/pareto-model-adjudicated/benchmark.jsonl'],
    ['pareto-holdout','research/benchmark/v31/pareto-model-holdout/benchmark.jsonl'],
    ['fresh-natural-holdout','research/benchmark/v31/fresh-natural-holdout/benchmark.jsonl'],
  ].map(([name,path])=>evaluateJudged(engine,path,name));
  const result={schema_version:1,taxonomy_version:31,role:'current YV product-search failure-mode audit',pinned_selector:{repository:'kingkong-projek/yrkesvaljaren',commit:PINNED_COMMIT,search_utils_blob:SEARCH_UTILS_BLOB,constants_blob:CONSTANTS_BLOB,fuse_js_version:FUSE_VERSION},source:{url:YV_URL,sha256:sha,rows:items.length},published_identity_recall:{occupation_name_ids:occ.length,occupation_exact_label_self_hit_at_5_pct:pct(occHit5,occ.length),job_title_unique_ids:byJt.size,job_title_context_rows:jt.length,job_title_all_context_rows_at_5_pct:pct(jtAll5,byJt.size),job_title_all_context_rows_at_10_pct:pct(jtAll10,byJt.size),multi_parent_job_title_ids:multi,multi_parent_all_context_rows_at_5_pct:pct(multiAll5,multi),multi_parent_all_context_rows_at_10_pct:pct(multiAll10,multi)},excluded_title_routing:evaluateExcluded(engine),judged_observed_query_suites:judged};
  fs.mkdirSync('artifacts',{recursive:true});fs.writeFileSync('artifacts/pinned-yv-selector-product-audit-v31.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({...result,excluded_title_routing:{...result.excluded_title_routing,detail:undefined},judged_observed_query_suites:judged.map(x=>({...x,detail:undefined}))},null,2));
}
await main();
