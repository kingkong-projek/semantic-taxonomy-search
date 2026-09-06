#!/usr/bin/env node
/**
 * Replay the no-context, non-empty-query path of the pinned KV HybridSearchEngine.
 *
 * Pinned implementation:
 * kingkong-projek/yrkesvaljaren@0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b
 * search.engine.ts git blob: bd255b894d39b9e8d628998cf8b749c71d529a3f
 * search.engine.helpers.ts git blob: 7f410397895714279c5968343d459842a5c03852
 * build-kompetens-sharded-package.mjs git blob: 618b93aae6c691e6f90cda402722a4c3f01d3341
 * package-lock Fuse.js: 7.5.0
 *
 * This evaluator intentionally uses no occupation/SSYK context: description fallback
 * must be measured on its own. The replay is limited to exactly the code path exercised
 * by search(query, '', [], 5); context/shard behavior is not reimplemented here.
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import Fuse from 'fuse.js';

const PINNED_COMMIT = '0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b';
const KV_URL = 'https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t31.json';
const KV_SHA256 = 'da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524';
const SKILL_CATEGORIES = ['regulated_skills','essential_skills','optional_skills','calculated_skills','related_skills'];
const DEFAULT_BUCKET_WEIGHTS = [10,9,8,7,6,5,4,3,2,1];
const WEIGHT_BUCKET_SIZE = 50;
const MAX_WEIGHTED_SKILL_DEPTH = DEFAULT_BUCKET_WEIGHTS.length * WEIGHT_BUCKET_SIZE;

function args() {
  const out = { benchmark: 'research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl', output: 'artifacts/pinned-kv-selector-description-baseline-v31.json' };
  for (let i=2;i<process.argv.length;i+=1) {
    if (process.argv[i]==='--benchmark') out.benchmark=process.argv[++i];
    else if (process.argv[i]==='--output') out.output=process.argv[++i];
    else throw new Error(`unknown arg ${process.argv[i]}`);
  }
  return out;
}
function pct(n,d){ return d ? Number((100*n/d).toFixed(3)) : 0; }
function normalizeText(value){ return String(value ?? '').normalize('NFC').toLowerCase().trim(); }
function uniqueStrings(values){ const seen=new Set(); const out=[]; for(const v of values){if(!v||seen.has(v))continue;seen.add(v);out.push(v);} return out; }
function splitSearchTokens(value){ return normalizeText(value).split(/[\s\-_/(),.;:]+/).filter(Boolean); }
function toArrayOfIds(value){ if(!value)return[]; if(Array.isArray(value))return value.filter(x=>typeof x==='string'); return Object.values(value).filter(x=>typeof x==='string'); }
function appendUnique(target,seen,ids){ for(const id of ids){if(!seen.has(id)){seen.add(id);target.push(id);}} }
function collectSkillLabels(rawData){
  const skills={};
  for(const node of Object.values(rawData||{})){
    if(!node||typeof node!=='object')continue;
    for(const category of SKILL_CATEGORIES){
      const value=node[category]; if(!value||typeof value!=='object')continue;
      for(const [label,id] of Object.entries(value)){ if(typeof label==='string'&&typeof id==='string') skills[id]=label; }
    }
    if(node.type===undefined&&!node.preferred_label){
      for(const [label,id] of Object.entries(node)){ if(typeof label==='string'&&typeof id==='string') skills[id]=label; }
    }
  }
  return skills;
}
function expandWeightedPrioritySources(rawData,sourceIds,transferableSkills,skillLabels){
  const ordered=[]; const seen=new Set();
  for(const sourceId of sourceIds){
    if(sourceId==='transferable_skills'){appendUnique(ordered,seen,transferableSkills);continue;}
    const sourceNode=rawData[sourceId];
    if(sourceNode?.type==='ssyk-level-4'){appendUnique(ordered,seen,toArrayOfIds(sourceNode.related_skills));continue;}
    if(skillLabels[sourceId]) appendUnique(ordered,seen,[sourceId]);
  }
  return ordered;
}
function buildBaseData(json){
  const rawData=json.data||{}; const skills=collectSkillLabels(rawData); const ordered=[]; const seen=new Set();
  const transferableSkills=toArrayOfIds(rawData.transferable_skills); appendUnique(ordered,seen,transferableSkills);
  for(const sourceId of toArrayOfIds(json.metadata?.most_common_ssyk_level_4)){
    if(sourceId==='transferable_skills')continue;
    appendUnique(ordered,seen,expandWeightedPrioritySources(rawData,toArrayOfIds(rawData[sourceId]?.weighted_priority),transferableSkills,skills));
  }
  return {skills,transferableSkills,globalWeightedSkills:ordered};
}
function buildWeightMapFromOrderedSkills(skillIds){
  const map=new Map(); const maxDepth=DEFAULT_BUCKET_WEIGHTS.length*WEIGHT_BUCKET_SIZE;
  skillIds.forEach((id,index)=>{if(map.has(id)||index>=maxDepth)return; const bucket=Math.floor(index/WEIGHT_BUCKET_SIZE); const weight=DEFAULT_BUCKET_WEIGHTS[bucket]??0; if(weight>0)map.set(id,weight);}); return map;
}
function buildSortWeightMapFromOrderedSkills(skillIds){
  const ids=uniqueStrings(skillIds); const map=new Map(); ids.slice(0,MAX_WEIGHTED_SKILL_DEPTH).forEach((id,index)=>map.set(id,MAX_WEIGHTED_SKILL_DEPTH-index)); return map;
}
function getDirectTextMatch(label,query){
  if(!label.includes(query))return null;
  if(label===query)return {kind:'exact'};
  if(label.startsWith(query))return {kind:'prefix'};
  const escaped=query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'); const m=new RegExp(`(?:^|[\\s\\-_/(),.;:])${escaped}`).exec(label);
  if(m)return {kind:'wordBoundary',index:m.index};
  return {kind:'contains',index:label.indexOf(query)};
}
function textScore(m){switch(m.kind){case'exact':return 10000;case'prefix':return 8000;case'wordBoundary':return 7000-Math.min(m.index,80)*8;case'contains':return 5600-Math.min(m.index,120)*4;case'fuzzy':return 3200+m.score*80;}}
function textTier(m){return {exact:0,prefix:1,wordBoundary:2,contains:3,fuzzy:4}[m.kind];}
function textOrder(m){if(m.kind==='exact'||m.kind==='prefix')return 0;if(m.kind==='fuzzy')return -m.score;return m.index;}
function exactTextAnchor(m){return m.kind==='exact'?0:1;}
function firstNonZero(values){return values.find(x=>x!==0)??0;}

class PinnedNoContextKvSearch {
  constructor(base){
    this.base=base;
    this.catalog=Object.entries(base.skills).map(([id,label])=>({id,preferred_label:label,normalizedLabel:normalizeText(label)}));
    const tokenCatalog=Object.entries(base.skills).flatMap(([skillId,label])=>splitSearchTokens(label).map(token=>({skillId,token})));
    this.tokenFuse=new Fuse(tokenCatalog,{includeScore:true,shouldSort:true,ignoreLocation:false,ignoreFieldNorm:true,ignoreDiacritics:false,threshold:0.25,distance:80,minMatchCharLength:3,keys:['token']});
  }
  search(query,maxResults=5){
    if(!String(query).trim())return [];
    const q=normalizeText(query); if(!q)return [];
    const direct=new Map();
    for(const entry of this.catalog){const m=getDirectTextMatch(entry.normalizedLabel,q);if(m)direct.set(entry.id,m);}
    const fuzzy=new Map();
    if(q.length>=3){
      for(const result of this.tokenFuse.search(q,{limit:150})){
        const confidence=1-(result.score??1);if(confidence<=0)continue;
        const existing=fuzzy.get(result.item.skillId);const existingScore=existing?.kind==='fuzzy'?existing.score:0;
        fuzzy.set(result.item.skillId,{kind:'fuzzy',score:Math.max(existingScore,confidence*8)});
      }
    }
    const matches=direct.size===0?fuzzy:new Map(fuzzy);
    if(direct.size>0)for(const [id,m] of direct)matches.set(id,m);
    const weighted=[...this.base.transferableSkills,...this.base.globalWeightedSkills];
    const weightMap=buildWeightMapFromOrderedSkills(weighted); const sortWeightMap=buildSortWeightMapFromOrderedSkills(weighted);
    const candidates=this.catalog.filter(e=>matches.has(e.id)).map(e=>({id:e.id,label:e.preferred_label,match:matches.get(e.id),weightedRank:weightMap.get(e.id)??0,weightedSortWeight:sortWeightMap.get(e.id)??0}));
    candidates.sort((a,b)=>firstNonZero([
      exactTextAnchor(a.match)-exactTextAnchor(b.match),
      textScore(b.match)-textScore(a.match),
      textTier(a.match)-textTier(b.match),
      textOrder(a.match)-textOrder(b.match),
      b.weightedRank-a.weightedRank,
      b.weightedSortWeight-a.weightedSortWeight,
      a.label.localeCompare(b.label,'sv'),
    ]));
    return candidates.slice(0,maxResults);
  }
}

async function main(){
  const a=args();
  const response=await fetch(KV_URL); if(!response.ok)throw new Error(`KV source HTTP ${response.status}`); const bytes=Buffer.from(await response.arrayBuffer());
  const sha=crypto.createHash('sha256').update(bytes).digest('hex'); if(sha!==KV_SHA256)throw new Error(`KV source drift ${sha}`);
  const kv=JSON.parse(bytes.toString('utf8')); const base=buildBaseData(kv); const engine=new PinnedNoContextKvSearch(base);
  const cases=fs.readFileSync(a.benchmark,'utf8').split(/\n/).filter(Boolean).map(JSON.parse); if(cases.length!==35)throw new Error(`expected 35 cases, got ${cases.length}`);
  let hit1=0,hit5=0,weightedHit1=0,weightedHit5=0,totalWeight=0,noResults=0; const detail=[];
  for(const c of cases){
    const target=String(c.target.concept_id); const w=Number(c.target.occurrence_proxy); const results=engine.search(c.query,5); const ids=results.map(r=>r.id);
    const h1=ids[0]===target,h5=ids.includes(target); hit1+=Number(h1);hit5+=Number(h5);weightedHit1+=w*Number(h1);weightedHit5+=w*Number(h5);totalWeight+=w;noResults+=Number(ids.length===0);
    detail.push({id:c.id,target_id:target,target_label:c.target.label,top1_success:h1,discovery_hit_at_5:h5,no_results:ids.length===0,top5:results.map(r=>({id:r.id,label:r.label,match:r.match.kind}))});
  }
  const result={schema_version:1,taxonomy_version:31,role:'pinned current-KV no-context description baseline replay',pinned_selector:{repository:'kingkong-projek/yrkesvaljaren',commit:PINNED_COMMIT,search_engine_blob:'bd255b894d39b9e8d628998cf8b749c71d529a3f',helpers_blob:'7f410397895714279c5968343d459842a5c03852',data_builder_blob:'618b93aae6c691e6f90cda402722a4c3f01d3341',fuse_js_version:'7.5.0',path_replayed:"HybridSearchEngine.search(query, '', [], 5)",context:'none'},source:{url:KV_URL,sha256:sha},skill_catalog_count:Object.keys(base.skills).length,cases:cases.length,occurrence_proxy_weight:totalWeight,top1_pct:pct(hit1,cases.length),weighted_top1_pct:pct(weightedHit1,totalWeight),discovery_hit_at_5_pct:pct(hit5,cases.length),weighted_discovery_hit_at_5_pct:pct(weightedHit5,totalWeight),no_result_cases:noResults,no_result_pct:pct(noResults,cases.length),cases_detail:detail};
  fs.mkdirSync(new URL('../artifacts/',import.meta.url),{recursive:true}); fs.writeFileSync(a.output,JSON.stringify(result,null,2)+'\n'); console.log(JSON.stringify({...result,cases_detail:undefined},null,2));
}
await main();
