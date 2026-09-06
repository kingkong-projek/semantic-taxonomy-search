import fs from 'node:fs';
import crypto from 'node:crypto';
import { describe, it, expect } from 'vitest';
import { TaxonomySearchEngine } from './src/components/job-selector/logic/search.engine';
import { HybridSearchEngine } from './packages/kompetensvaljaren/src/components/kompetensvaljaren/logic/search.engine';
import type { KvBaseData, KvContextShard } from './packages/kompetensvaljaren/src/components/kompetensvaljaren/logic/types';

const YV_URL = 'https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json';
const YV_SHA = '1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49';
const KV_URL = 'https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t31.json';
const KV_SHA = 'da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524';
const SKILL_CATEGORIES = ['regulated_skills','essential_skills','optional_skills','calculated_skills','related_skills'];

type RawDoc = { data?: Record<string, any>; metadata?: Record<string, any> };
type Journey = {
  id: string;
  product: string;
  first_query: string;
  recognition_budget: number;
  followup_budget: number;
  ground_truth_mode: string;
  success_condition: string;
};

function sha256(bytes: Buffer): string { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function toIds(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) return value.filter((x): x is string => typeof x === 'string');
  if (typeof value === 'object') return Object.values(value as Record<string, unknown>).filter((x): x is string => typeof x === 'string');
  return [];
}
function appendUnique(target: string[], seen: Set<string>, ids: string[]) {
  for (const id of ids) if (!seen.has(id)) { seen.add(id); target.push(id); }
}
function collectSkillLabels(raw: Record<string, any>): Record<string,string> {
  const skills: Record<string,string> = {};
  for (const node of Object.values(raw)) {
    if (!node || typeof node !== 'object') continue;
    for (const cat of SKILL_CATEGORIES) {
      const value = node[cat]; if (!value || typeof value !== 'object') continue;
      for (const [label,id] of Object.entries(value)) if (typeof label === 'string' && typeof id === 'string') skills[id]=label;
    }
    if (node.type === undefined && !node.preferred_label) {
      for (const [label,id] of Object.entries(node)) if (typeof label === 'string' && typeof id === 'string') skills[id]=label;
    }
  }
  return skills;
}
function expandWeighted(raw: Record<string,any>, ids: string[], transferable: string[], skills: Record<string,string>): string[] {
  const out: string[]=[]; const seen=new Set<string>();
  for (const id of ids) {
    if (id === 'transferable_skills') { appendUnique(out,seen,transferable); continue; }
    const node=raw[id];
    if (node?.type === 'ssyk-level-4') { appendUnique(out,seen,toIds(node.related_skills)); continue; }
    if (skills[id]) appendUnique(out,seen,[id]);
  }
  return out;
}
function buildKv(doc: RawDoc): { base: KvBaseData; shards: Map<string,KvContextShard> } {
  const raw=doc.data ?? {}; const skills=collectSkillLabels(raw);
  const transferable=toIds(raw.transferable_skills); const globalWeighted: string[]=[]; const seen=new Set<string>();
  appendUnique(globalWeighted,seen,transferable);
  for (const sourceId of toIds(doc.metadata?.most_common_ssyk_level_4)) {
    if (sourceId === 'transferable_skills') continue;
    appendUnique(globalWeighted,seen,expandWeighted(raw,toIds(raw[sourceId]?.weighted_priority),transferable,skills));
  }
  const occupationToSsyk4: Record<string,string>={}, ssyk4ToSsyk3: Record<string,string>={}, shardRefs: Record<string,string>={};
  for (const [id,node] of Object.entries(raw)) {
    if (!node || typeof node !== 'object') continue;
    if (node.type==='occupation-name' && typeof node['ssyk-level-4-id']==='string') occupationToSsyk4[id]=node['ssyk-level-4-id'];
    if (node.type==='ssyk-level-4' && typeof node.ssyk_code_2012==='string') {
      const ssyk3=String(node.ssyk_code_2012).slice(0,3); ssyk4ToSsyk3[id]=ssyk3; shardRefs[ssyk3]=`memory:${ssyk3}`;
    }
  }
  const base: KvBaseData = {
    format:'kv-base.v1', taxonomyVersion:String(doc.metadata?.labour_market_taxonomy_version ?? doc.metadata?.version ?? '31'), dataCreated:String(doc.metadata?.data_created ?? ''),
    skills, mostCommonSkills:toIds(doc.metadata?.most_common_skills), mostCommonSsykLevel4:toIds(doc.metadata?.most_common_ssyk_level_4),
    globalWeightedSkills:globalWeighted, transferableSkills:transferable, occupationToSsyk4, ssyk4ToSsyk3, shards:shardRefs,
  };
  const shards=new Map<string,KvContextShard>();
  const getShard=(ssyk3:string):KvContextShard=>{
    let shard=shards.get(ssyk3); if (!shard) { shard={format:'kv-context.v1',ssyk3,ssyk4:{},occupations:{}}; shards.set(ssyk3,shard); } return shard;
  };
  for (const [id,node] of Object.entries(raw)) {
    if (!node || typeof node !== 'object') continue;
    if (node.type==='ssyk-level-4') {
      const ssyk3=ssyk4ToSsyk3[id]; if (!ssyk3) continue;
      getShard(ssyk3).ssyk4[id]={ssykCode2012:String(node.ssyk_code_2012??''),relatedSkills:toIds(node.related_skills),weightedSkills:expandWeighted(raw,toIds(node.weighted_priority),transferable,skills)};
    } else if (node.type==='occupation-name') {
      const ssyk4=occupationToSsyk4[id], ssyk3=ssyk4ToSsyk3[ssyk4]; if (!ssyk3) continue;
      getShard(ssyk3).occupations[id]={preferredLabel:String(node.preferred_label??''),ssykLevel4Id:ssyk4,regulatedSkills:toIds(node.regulated_skills),essentialSkills:toIds(node.essential_skills),optionalSkills:toIds(node.optional_skills),calculatedSkills:toIds(node.calculated_skills)};
    }
  }
  return {base,shards};
}
async function fetchPinned(url:string, expected:string):Promise<RawDoc> {
  const r=await fetch(url); expect(r.ok).toBe(true); const bytes=Buffer.from(await r.arrayBuffer()); expect(sha256(bytes)).toBe(expected); return JSON.parse(bytes.toString('utf8'));
}
function displayYv(x:any):string { return x.type==='job-title' && x.related ? `${x.preferred_label} (${x.related.preferred_label})` : x.preferred_label; }
function occupationId(x:any):string|null { return x.type==='occupation-name' ? x.id : (x.type==='job-title' ? x.related?.id ?? null : null); }

const journeysPath=process.env.JOURNEYS_FILE;
const outputPath=process.env.OUT_FILE;
if (!journeysPath || !outputPath) throw new Error('JOURNEYS_FILE and OUT_FILE are required');

describe('Track 1 persona replay against exact current product engines', () => {
  it('replays only non-description journeys and writes machine-readable output', async () => {
    const journeys:Journey[]=fs.readFileSync(journeysPath,'utf8').split(/\n/).filter(Boolean).map(JSON.parse);
    const included=journeys.filter(j=>!j.product.includes('DESCRIPTION'));
    const skipped=journeys.filter(j=>j.product.includes('DESCRIPTION')).map(j=>j.id);
    expect(included.length).toBeGreaterThan(0);
    expect(skipped.length).toBeGreaterThan(0);

    const [yvDoc,kvDoc]=await Promise.all([fetchPinned(YV_URL,YV_SHA),fetchPinned(KV_URL,KV_SHA)]);
    const yvItems=(yvDoc as any).data; expect(Array.isArray(yvItems)).toBe(true);
    const yv=new TaxonomySearchEngine(yvItems);
    const {base,shards}=buildKv(kvDoc);
    const kv=new HybridSearchEngine(base,async ssyk3=>shards.get(ssyk3)??null);

    const results:any[]=[];
    for (const j of included) {
      if (j.first_query.startsWith('__AUTO_')) {
        results.push({id:j.id,product:j.product,status:'deferred-deterministic-substitution',query:j.first_query});
        continue;
      }
      if (j.product==='YV') {
        const all=yv.search(j.first_query,50);
        results.push({id:j.id,product:j.product,query:j.first_query,recognition_budget:j.recognition_budget,result_count:all.length,visible:all.slice(0,j.recognition_budget).map((x:any)=>({display:displayYv(x),type:x.type,id:x.id,occupation_id:occupationId(x)})),all:all.map((x:any)=>({display:displayYv(x),type:x.type,id:x.id,occupation_id:occupationId(x)}))});
        continue;
      }
      if (j.product==='KV') {
        const rows=kv.search(j.first_query,'',[],50);
        results.push({id:j.id,product:j.product,query:j.first_query,recognition_budget:j.recognition_budget,result_count:rows.length,visible:rows.slice(0,j.recognition_budget),all:rows});
        continue;
      }
      if (j.product==='YV_TO_KV') {
        const yvRows=yv.search(j.first_query,10);
        const paths:any[]=[];
        for (const selection of yvRows.slice(0,5) as any[]) {
          const occ=occupationId(selection);
          if (!occ) { paths.push({yv:{display:displayYv(selection),type:selection.type,id:selection.id},occupation_id:null,kv_context_valid:false,kv_top5:[]}); continue; }
          await kv.prepareContext(occ,[]);
          const kvTop=kv.getPrioritizedList(occ,[],5);
          paths.push({yv:{display:displayYv(selection),type:selection.type,id:selection.id,occupation_id:occ},occupation_id:occ,kv_context_valid:kv.hasContext(occ),kv_top5:kvTop});
        }
        results.push({id:j.id,product:j.product,query:j.first_query,yv_visible:yvRows.slice(0,5).map((x:any)=>({display:displayYv(x),type:x.type,id:x.id,occupation_id:occupationId(x)})),paths});
      }
    }

    const out={schema_version:1,track:'1-current-yv-kv-findability',yv_commit:process.env.YV_COMMIT,description_journeys_skipped:skipped,included_journeys:included.length,results};
    fs.mkdirSync(outputPath.substring(0,outputPath.lastIndexOf('/')),{recursive:true});
    fs.writeFileSync(outputPath,JSON.stringify(out,null,2)+'\n');
    console.log(JSON.stringify({included_journeys:included.length,description_journeys_skipped:skipped,journey_summaries:results.map(r=>({id:r.id,product:r.product,query:r.query,result_count:r.result_count??r.yv_visible?.length??null,visible:r.visible??r.yv_visible??null}))},null,2));
  },120_000);
});
