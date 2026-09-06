#!/usr/bin/env node
/**
 * Replay current YV/KV selector behavior on source-attested "should find" probes.
 *
 * This evaluator is deliberately product-first. It does not test semantic C0/C2.
 * It asks whether words already owned by the taxonomy/migration graph, or narrowly
 * inferred observed title+context phrases, surface the authoritative target in the
 * ordinary current selectors.
 *
 * It also isolates a YV interaction between fuzzy fallback and multi-context job
 * titles: current search.utils.ts deduplicates fuzzy candidates by job-title id,
 * while contextual rows share that id. Exact/direct search does not have this issue.
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import Fuse from 'fuse.js';

const YV_URL='https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json';
const YV_SHA='1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49';
const KV_URL='https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t31.json';
const KV_SHA='da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524';
const FUSE_VERSION='7.5.0';
const MAX_WEAK_FUZZY_RESULTS=3, MIN_FUZZY_SCORE=0.4, MAX_FUZZY_SCORE=0.84;
const SKILL_CATEGORIES=['regulated_skills','essential_skills','optional_skills','calculated_skills','related_skills'];
const DEFAULT_BUCKET_WEIGHTS=[10,9,8,7,6,5,4,3,2,1], WEIGHT_BUCKET_SIZE=50;
const MAX_WEIGHTED_SKILL_DEPTH=DEFAULT_BUCKET_WEIGHTS.length*WEIGHT_BUCKET_SIZE;

function parseArgs(){let input='artifacts/findability-should-find-v31/cases.jsonl',output='artifacts/findability-should-find-v31/evaluation.json';for(let i=2;i<process.argv.length;i++){if(process.argv[i]==='--input')input=process.argv[++i];else if(process.argv[i]==='--output')output=process.argv[++i];else throw new Error(`unknown arg ${process.argv[i]}`);}return{input,output};}
function pct(n,d){return d?Number((100*n/d).toFixed(3)):0;}
function norm(v){return String(v??'').normalize('NFC').toLowerCase().trim();}
function sha(b){return crypto.createHash('sha256').update(b).digest('hex');}
function rowKey(r){return `${r.id}|${r.occupation_name_id??''}`;}
function displayLabel(r){return r.occupation_name_preferred_label?`${r.preferred_label??''} (${r.occupation_name_preferred_label})`:(r.preferred_label??'');}

function getDirectScore(label,q,tokens){if(label===q)return 1;if(tokens.length>1)return tokens.every(t=>label.includes(t))?.98:null;if(label.startsWith(q))return .99;if(label.includes(q))return .95;return null;}
function editDistance(a,b){const n=b.length;let prev=Array.from({length:n+1},(_,i)=>i);for(let i=1;i<=a.length;i++){const cur=[i,...new Array(n).fill(0)];for(let j=1;j<=n;j++)cur[j]=Math.min(cur[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));prev=cur;}return prev[n];}
function fuzzySubstring(text,q){const target=q.length,min=Math.max(3,target-2),max=Math.min(text.length,target+2);let best=99;for(let s=0;s<=text.length-min;s++)for(let l=min;l<=max&&s+l<=text.length;l++)best=Math.min(best,editDistance(q,text.slice(s,s+l)));return best<=Math.max(2,Math.floor(target*.25))?best:null;}
function rootMatch(q,label){q=norm(q);label=norm(label);if(label.includes(' ')){const d=editDistance(q,label);return d<=Math.max(2,Math.floor(q.length*.25))&&Math.abs(q.length-label.length)<=2;}return fuzzySubstring(label,q)!==null;}
function strictSort(rows){return rows.sort((a,b)=>b.score-a.score||Number(b.weight??0)-Number(a.weight??0)||a.displayLabel.localeCompare(b.displayLabel,'sv'));}

class CurrentYv {
  constructor(items){this.items=items;this.fuse=new Fuse(items,{keys:['preferred_label'],includeScore:true,ignoreDiacritics:true,ignoreFieldNorm:true,threshold:.6,minMatchCharLength:1,ignoreLocation:true,distance:100});}
  searchDetailed(query,max=10){
    if(!query)return{lane:'none',results:[]};const q=norm(query),tokens=q.split(' ').filter(Boolean),direct=[];
    for(const item of this.items){const s=getDirectScore(norm(item.preferred_label),q,tokens);if(s!==null)direct.push({...item,score:s,displayLabel:displayLabel(item)});}
    if(direct.length)return{lane:'direct',results:strictSort(direct).slice(0,max)};
    const raw=this.fuse.search(q);if(!raw.length)return{lane:'none',results:[]};const best=raw[0].score??1,candidates=[];let strong=false;
    // IMPORTANT: mirror production exactly. Fuzzy dedupe is by item.id, not contextual row key.
    const processedIds=new Set();
    for(const fr of raw){if(processedIds.has(fr.item.id))continue;const rs=fr.score??1,base=1-rs;if(base<MIN_FUZZY_SCORE)continue;if(rs>best+.12)continue;const root=rootMatch(q,norm(fr.item.preferred_label));if(root&&rs<=.25)strong=true;let score=base*.70+Number(fr.item.weight??0)*.10+(root?.12:0);score=Math.min(MAX_FUZZY_SCORE,Math.max(MIN_FUZZY_SCORE,score));candidates.push({...fr.item,score,displayLabel:displayLabel(fr.item)});processedIds.add(fr.item.id);}
    if(!candidates.length)return{lane:'none',results:[]};const sorted=strictSort(candidates),limit=strong?Math.min(5,max):Math.min(MAX_WEAK_FUZZY_RESULTS,max);return{lane:'fuzzy',results:sorted.slice(0,limit)};
  }
}

function uniqueStrings(values){const out=[],seen=new Set();for(const x of values){if(!x||seen.has(x))continue;seen.add(x);out.push(x);}return out;}
function splitTokens(v){return norm(v).split(/[\s\-_/(),.;:]+/).filter(Boolean);}
function toIds(v){if(!v)return[];if(Array.isArray(v))return v.filter(x=>typeof x==='string');return Object.values(v).filter(x=>typeof x==='string');}
function appendUnique(out,seen,ids){for(const id of ids)if(!seen.has(id)){seen.add(id);out.push(id);}}
function collectSkillLabels(raw){const skills={};for(const node of Object.values(raw||{})){if(!node||typeof node!=='object')continue;for(const cat of SKILL_CATEGORIES){const v=node[cat];if(!v||typeof v!=='object')continue;for(const [label,id] of Object.entries(v))if(typeof label==='string'&&typeof id==='string')skills[id]=label;}if(node.type===undefined&&!node.preferred_label)for(const [label,id] of Object.entries(node))if(typeof label==='string'&&typeof id==='string')skills[id]=label;}return skills;}
function expandPriority(raw,ids,transferable,skills){const out=[],seen=new Set();for(const id of ids){if(id==='transferable_skills'){appendUnique(out,seen,transferable);continue;}const n=raw[id];if(n?.type==='ssyk-level-4'){appendUnique(out,seen,toIds(n.related_skills));continue;}if(skills[id])appendUnique(out,seen,[id]);}return out;}
function buildKvBase(doc){const raw=doc.data||{},skills=collectSkillLabels(raw),ordered=[],seen=new Set(),transferable=toIds(raw.transferable_skills);appendUnique(ordered,seen,transferable);for(const source of toIds(doc.metadata?.most_common_ssyk_level_4)){if(source==='transferable_skills')continue;appendUnique(ordered,seen,expandPriority(raw,toIds(raw[source]?.weighted_priority),transferable,skills));}return{skills,transferableSkills:transferable,globalWeightedSkills:ordered};}
function weightMap(ids){const m=new Map();ids.forEach((id,i)=>{if(m.has(id)||i>=MAX_WEIGHTED_SKILL_DEPTH)return;const w=DEFAULT_BUCKET_WEIGHTS[Math.floor(i/WEIGHT_BUCKET_SIZE)]??0;if(w>0)m.set(id,w);});return m;}
function sortWeightMap(ids){const m=new Map();uniqueStrings(ids).slice(0,MAX_WEIGHTED_SKILL_DEPTH).forEach((id,i)=>m.set(id,MAX_WEIGHTED_SKILL_DEPTH-i));return m;}
function directMatch(label,q){if(!label.includes(q))return null;if(label===q)return{kind:'exact'};if(label.startsWith(q))return{kind:'prefix'};const e=q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),m=new RegExp(`(?:^|[\\s\\-_/(),.;:])${e}`).exec(label);if(m)return{kind:'wordBoundary',index:m.index};return{kind:'contains',index:label.indexOf(q)};}
function textScore(m){return m.kind==='exact'?10000:m.kind==='prefix'?8000:m.kind==='wordBoundary'?7000-Math.min(m.index,80)*8:m.kind==='contains'?5600-Math.min(m.index,120)*4:3200+m.score*80;}
function tier(m){return{exact:0,prefix:1,wordBoundary:2,contains:3,fuzzy:4}[m.kind];}
function order(m){if(m.kind==='exact'||m.kind==='prefix')return 0;if(m.kind==='fuzzy')return-m.score;return m.index;}
function anchor(m){return m.kind==='exact'?0:1;}
function firstNonZero(v){return v.find(x=>x!==0)??0;}
class CurrentKv{
  constructor(base){this.base=base;this.catalog=Object.entries(base.skills).map(([id,label])=>({id,preferred_label:label,normalizedLabel:norm(label)}));const tc=Object.entries(base.skills).flatMap(([skillId,label])=>splitTokens(label).map(token=>({skillId,token})));this.tokenFuse=new Fuse(tc,{includeScore:true,shouldSort:true,ignoreLocation:false,ignoreFieldNorm:true,ignoreDiacritics:false,threshold:.25,distance:80,minMatchCharLength:3,keys:['token']});}
  searchDetailed(query,max=5){const q=norm(query);if(!q)return{lane:'none',results:[]};const direct=new Map();for(const e of this.catalog){const m=directMatch(e.normalizedLabel,q);if(m)direct.set(e.id,m);}const fuzzy=new Map();if(q.length>=3)for(const r of this.tokenFuse.search(q,{limit:150})){const conf=1-(r.score??1);if(conf<=0)continue;const old=fuzzy.get(r.item.skillId),oldScore=old?.kind==='fuzzy'?old.score:0;fuzzy.set(r.item.skillId,{kind:'fuzzy',score:Math.max(oldScore,conf*8)});}const matches=direct.size===0?fuzzy:new Map(fuzzy);if(direct.size)for(const [id,m] of direct)matches.set(id,m);const weighted=[...this.base.transferableSkills,...this.base.globalWeightedSkills],wm=weightMap(weighted),sm=sortWeightMap(weighted);const rows=this.catalog.filter(e=>matches.has(e.id)).map(e=>({id:e.id,label:e.preferred_label,match:matches.get(e.id),weightedRank:wm.get(e.id)??0,weightedSortWeight:sm.get(e.id)??0}));rows.sort((a,b)=>firstNonZero([anchor(a.match)-anchor(b.match),textScore(b.match)-textScore(a.match),tier(a.match)-tier(b.match),order(a.match)-order(b.match),b.weightedRank-a.weightedRank,b.weightedSortWeight-a.weightedSortWeight,a.label.localeCompare(b.label,'sv')]));return{lane:direct.size?'direct':(rows.length?'fuzzy':'none'),results:rows.slice(0,max)};}
}

function mutateLabel(label){
  const chars=[...label];
  const letters=[];for(let i=0;i<chars.length;i++)if(/[A-Za-zÅÄÖåäö]/.test(chars[i]))letters.push(i);
  const candidates=[];
  // Prefer an internal single-character deletion: realistic typo, preserves word shape.
  for(let k=Math.floor(letters.length/2);k<letters.length-1;k++){const i=letters[k];if(i>0&&i<chars.length-1)candidates.push(chars.slice(0,i).concat(chars.slice(i+1)).join(''));}
  // Then an adjacent transposition.
  for(let k=1;k<letters.length-1;k++){const i=letters[k],j=letters[k+1];if(j===i+1){const c=[...chars];[c[i],c[j]]=[c[j],c[i]];candidates.push(c.join(''));}}
  return uniqueStrings(candidates).filter(x=>norm(x)!==norm(label));
}

async function fetchPinned(url,expected){const r=await fetch(url);if(!r.ok)throw new Error(`HTTP ${r.status}: ${url}`);const b=Buffer.from(await r.arrayBuffer()),s=sha(b);if(s!==expected)throw new Error(`source drift ${url}: ${s}`);return{bytes:b,doc:JSON.parse(b.toString('utf8'))};}

async function main(){
  const a=parseArgs(),cases=fs.readFileSync(a.input,'utf8').split(/\n/).filter(Boolean).map(JSON.parse);
  const yvSrc=await fetchPinned(YV_URL,YV_SHA),kvSrc=await fetchPinned(KV_URL,KV_SHA),yvItems=yvSrc.doc.data,kvBase=buildKvBase(kvSrc.doc),yv=new CurrentYv(yvItems),kv=new CurrentKv(kvBase);
  const yvPreferred=new Map();for(const r of yvItems){const q=norm(r.preferred_label);if(!yvPreferred.has(q))yvPreferred.set(q,[]);yvPreferred.get(q).push(r);}
  const kvPreferred=new Map();for(const [id,label] of Object.entries(kvBase.skills)){const q=norm(label);if(!kvPreferred.has(q))kvPreferred.set(q,[]);kvPreferred.get(q).push({id,label});}

  const detail=[];
  for(const c of cases){
    const target=c.target,product=c.product,q=c.query;
    if(product==='YV'){
      const run=yv.searchDetailed(q,10),top5=run.results.slice(0,5),preferred=yvPreferred.get(norm(q))??[];
      const collision=preferred.length>0&&!preferred.some(r=>String(r.id)===String(target.concept_id)&&String(r.type)===String(target.kind));
      const exactTarget=r=>String(r.type)===String(target.kind)&&String(r.id)===String(target.concept_id);
      const targetAt5=top5.some(exactTarget),targetAt10=run.results.some(exactTarget);
      let discovery5=targetAt5,discovery10=targetAt10,context5=null,context10=null;
      if(target.kind==='occupation-name'){
        const occ=r=>String(r.type)==='occupation-name'&&String(r.id)===String(target.concept_id)||String(r.type)==='job-title'&&String(r.occupation_name_id)===String(target.concept_id);
        discovery5=top5.some(occ);discovery10=run.results.some(occ);
      }
      if(c.expected_context_row){const ctx=r=>String(r.id)===String(c.expected_context_row.job_title_id)&&String(r.occupation_name_id)===String(c.expected_context_row.occupation_name_id);context5=top5.some(ctx);context10=run.results.some(ctx);}
      detail.push({...c,selector_lane:run.lane,preferred_label_collision:collision,target_exact_at_5:targetAt5,target_exact_at_10:targetAt10,discovery_at_5:discovery5,discovery_at_10:discovery10,context_row_at_5:context5,context_row_at_10:context10,no_results:run.results.length===0,top5:top5.map(r=>({type:r.type,id:r.id,label:r.preferred_label,parent_id:r.occupation_name_id??null,parent_label:r.occupation_name_preferred_label??null}))});
    }else{
      const run=kv.searchDetailed(q,5),preferred=kvPreferred.get(norm(q))??[],collision=preferred.length>0&&!preferred.some(r=>String(r.id)===String(target.concept_id)),hit=run.results.some(r=>String(r.id)===String(target.concept_id));
      detail.push({...c,selector_lane:run.lane,preferred_label_collision:collision,target_exact_at_5:hit,discovery_at_5:hit,no_results:run.results.length===0,top5:run.results.map(r=>({id:r.id,label:r.label,match:r.match.kind}))});
    }
  }

  function summarize(product){const rows=detail.filter(r=>r.product===product),strict=rows.filter(r=>!r.preferred_label_collision),observed=strict.filter(r=>product==='YV'&&Number(r.observed_yv_query_count)>0),fail=strict.filter(r=>!r.discovery_at_5),byProv={};for(const r of strict)for(const p of r.surface_provenance){const b=byProv[p]??={cases:0,hit5:0,observed_volume:0,observed_hit5_volume:0};b.cases++;b.hit5+=Number(r.discovery_at_5);const w=Number(r.observed_yv_query_count??0);b.observed_volume+=w;b.observed_hit5_volume+=w*Number(r.discovery_at_5);byProv[p]=b;}for(const b of Object.values(byProv)){b.discovery_at_5_pct=pct(b.hit5,b.cases);b.observed_volume_discovery_at_5_pct=pct(b.observed_hit5_volume,b.observed_volume);}
    const observedVol=observed.reduce((s,r)=>s+Number(r.observed_yv_query_count),0),observedHit=observed.reduce((s,r)=>s+Number(r.observed_yv_query_count)*Number(r.discovery_at_5),0);
    const proxyDen=strict.reduce((s,r)=>s+Number(r.target_occurrence_proxy??0),0),proxyHit=strict.reduce((s,r)=>s+Number(r.target_occurrence_proxy??0)*Number(r.discovery_at_5),0);
    return{cases:rows.length,strict_noncollision_cases:strict.length,preferred_label_collision_cases:rows.length-strict.length,discovery_at_5_pct:pct(strict.filter(r=>r.discovery_at_5).length,strict.length),no_result_pct:pct(strict.filter(r=>r.no_results).length,strict.length),observed_exact_query_cases:observed.length,observed_exact_query_volume:observedVol,observed_volume_discovery_at_5_pct:pct(observedHit,observedVol),target_occurrence_proxy_weighted_discovery_at_5_pct:pct(proxyHit,proxyDen),by_surface_provenance:byProv,top_failures:fail.sort((a,b)=>Number(b.observed_yv_query_count??b.target_occurrence_proxy??0)-Number(a.observed_yv_query_count??a.target_occurrence_proxy??0)).slice(0,30).map(r=>({query:r.query,target:r.target,provenance:r.surface_provenance,observed_yv_query_count:r.observed_yv_query_count??null,target_occurrence_proxy:r.target_occurrence_proxy??0,lane:r.selector_lane,no_results:r.no_results,top5:r.top5}))};}

  // Synthetic structural stress only: one realistic typo per multi-context title where
  // production actually enters fuzzy and recognizes the intended job-title id.
  const byJob=new Map();for(const r of yvItems.filter(r=>r.type==='job-title')){if(!byJob.has(r.id))byJob.set(r.id,[]);byJob.get(r.id).push(r);}const stress=[];
  for(const [id,rows] of byJob){const parents=new Set(rows.map(r=>r.occupation_name_id).filter(Boolean));if(parents.size<=1)continue;let chosen=null;for(const q of mutateLabel(rows[0].preferred_label)){const run=yv.searchDetailed(q,10);if(run.lane==='fuzzy'&&run.results.some(r=>String(r.id)===String(id))){chosen={q,run};break;}}if(!chosen)continue;const returned=chosen.run.results.filter(r=>String(r.id)===String(id));stress.push({job_title_id:id,label:rows[0].preferred_label,query:chosen.q,expected_context_rows:rows.length,returned_context_rows:returned.length,returned:returned.map(r=>({parent_id:r.occupation_name_id,parent_label:r.occupation_name_preferred_label}))});}
  const fuzzyStress={eligible_multi_context_titles:stress.length,all_contexts_preserved:stress.filter(x=>x.returned_context_rows===x.expected_context_rows).length,all_contexts_preserved_pct:pct(stress.filter(x=>x.returned_context_rows===x.expected_context_rows).length,stress.length),one_context_only:stress.filter(x=>x.returned_context_rows===1).length,examples:stress.slice(0,30)};

  const result={schema_version:1,taxonomy_version:31,role:'current-selector should-find reconstruction',selector_contract:{yv_search_utils_blob:'711769d019d01539b958776467e42dbafa46d9c1',yv_constants_blob:'e9a412778d77de1aef82da94e36559619f5d607c',fuse_js_version:FUSE_VERSION,yv_fuzzy_dedupe_key:'job-title id'},sources:{yv:{url:YV_URL,sha256:sha(yvSrc.bytes)},kv:{url:KV_URL,sha256:sha(kvSrc.bytes)}},YV:summarize('YV'),KV:summarize('KV'),yv_multi_context_fuzzy_structural_stress:fuzzyStress,cases_detail:detail};
  fs.mkdirSync(new URL('../artifacts/',import.meta.url),{recursive:true});fs.mkdirSync(a.output.substring(0,a.output.lastIndexOf('/')),{recursive:true});fs.writeFileSync(a.output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({...result,cases_detail:undefined,YV:{...result.YV,top_failures:result.YV.top_failures.slice(0,10)},KV:{...result.KV,top_failures:result.KV.top_failures.slice(0,10)},yv_multi_context_fuzzy_structural_stress:{...fuzzyStress,examples:fuzzyStress.examples.slice(0,10)}},null,2));
}
await main();
