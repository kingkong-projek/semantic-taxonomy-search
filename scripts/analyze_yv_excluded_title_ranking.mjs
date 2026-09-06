#!/usr/bin/env node
/**
 * Measure ranking/reachability for the frozen generator-excluded YV title population.
 *
 * This is a Track-1 diagnostic, not a product change. It compares the pinned current
 * direct-search ordering with one deliberately narrow counterfactual:
 *   exact excluded-title wording -> already generator-mapped occupation parents first.
 *
 * The counterfactual uses only parent identities already frozen in
 * research/benchmark/v31/yv-profile-safety/excluded-routing-review.jsonl.
 */
import fs from 'node:fs';
import crypto from 'node:crypto';

const YV_URL = 'https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json';
const YV_SHA256 = '1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49';
const CASES_PATH = 'research/benchmark/v31/yv-profile-safety/excluded-routing-review.jsonl';
const EXPECTED_CASES = 205;

function norm(v){ return String(v ?? '').toLowerCase().trim().replace(/\s+/g,' '); }
function readJsonl(path){ return fs.readFileSync(path,'utf8').split(/\n/).filter(Boolean).map(JSON.parse); }
function pct(n,d){ return d ? Number((100*n/d).toFixed(3)) : 0; }
function display(item){ return item.occupation_name_preferred_label ? `${item.preferred_label} (${item.occupation_name_preferred_label})` : item.preferred_label; }
function discoveryOccupationId(r){ return r.type === 'occupation-name' ? r.id : (r.type === 'job-title' ? r.occupation_name_id : null); }
function directScore(label, query){
  const l=norm(label), q=norm(query), tokens=q.split(' ').filter(Boolean);
  if(l===q) return 1.0;
  if(tokens.length>1) return tokens.every(t=>l.includes(t)) ? 0.98 : null;
  if(l.startsWith(q)) return 0.99;
  if(l.includes(q)) return 0.95;
  return null;
}
function sortStrict(rows){
  return rows.sort((a,b)=>{
    if(a.score!==b.score) return b.score-a.score;
    const aw=a.weight??0,bw=b.weight??0;
    if(aw!==bw) return bw-aw;
    return a.display.localeCompare(b.display,'sv');
  });
}
function directResults(items,query){
  const out=[];
  for(const item of items){
    const score=directScore(item.preferred_label,query);
    if(score!==null) out.push({...item,score,display:display(item)});
  }
  return sortStrict(out);
}
function routedResults(current,targetIds,occupationById){
  const parents=[...targetIds]
    .map(id=>occupationById.get(id))
    .filter(Boolean)
    .map(item=>({...item,score:1.0,display:display(item),route:'excluded-title-parent'}))
    .sort((a,b)=>{
      const aw=a.weight??0,bw=b.weight??0;
      if(aw!==bw) return bw-aw;
      return a.display.localeCompare(b.display,'sv');
    });
  const parentIds=new Set(parents.map(x=>x.id));
  const rest=current.filter(r=>!(r.type==='occupation-name' && parentIds.has(r.id)));
  return [...parents,...rest];
}
function summarize(rows){
  const total=rows.length;
  const volume=rows.reduce((s,r)=>s+r.observed_count,0);
  const at=(k)=>rows.reduce((s,r)=>s+Number(r.current.first_target_rank!==null && r.current.first_target_rank<=k),0);
  const wat=(k)=>rows.reduce((s,r)=>s+r.observed_count*Number(r.current.first_target_rank!==null && r.current.first_target_rank<=k),0);
  const rat=(k)=>rows.reduce((s,r)=>s+Number(r.routed.first_target_rank!==null && r.routed.first_target_rank<=k),0);
  const rwat=(k)=>rows.reduce((s,r)=>s+r.observed_count*Number(r.routed.first_target_rank!==null && r.routed.first_target_rank<=k),0);
  const targetTotal=rows.reduce((s,r)=>s+r.target_parent_count,0);
  const recall=(which,k)=>rows.reduce((s,r)=>s+r[which][`target_hits_at_${k}`],0);
  return {
    cases:total,
    observed_volume:volume,
    current:{
      any_parent_at_1_pct:pct(at(1),total), any_parent_at_3_pct:pct(at(3),total), any_parent_at_5_pct:pct(at(5),total), any_parent_at_10_pct:pct(at(10),total),
      weighted_any_parent_at_1_pct:pct(wat(1),volume), weighted_any_parent_at_3_pct:pct(wat(3),volume), weighted_any_parent_at_5_pct:pct(wat(5),volume), weighted_any_parent_at_10_pct:pct(wat(10),volume),
      micro_parent_recall_at_5_pct:pct(recall('current',5),targetTotal), micro_parent_recall_at_10_pct:pct(recall('current',10),targetTotal),
      no_parent_in_direct_results:rows.filter(r=>r.current.first_target_rank===null).length,
      higher_score_prefix_shadow_cases:rows.filter(r=>r.mechanism.higher_score_prefix_shadow).length,
      weighted_higher_score_prefix_shadow_pct:pct(rows.reduce((s,r)=>s+r.observed_count*Number(r.mechanism.higher_score_prefix_shadow),0),volume)
    },
    exact_excluded_title_parent_route_counterfactual:{
      any_parent_at_1_pct:pct(rat(1),total), any_parent_at_3_pct:pct(rat(3),total), any_parent_at_5_pct:pct(rat(5),total), any_parent_at_10_pct:pct(rat(10),total),
      weighted_any_parent_at_1_pct:pct(rwat(1),volume), weighted_any_parent_at_3_pct:pct(rwat(3),volume), weighted_any_parent_at_5_pct:pct(rwat(5),volume), weighted_any_parent_at_10_pct:pct(rwat(10),volume),
      micro_parent_recall_at_5_pct:pct(recall('routed',5),targetTotal), micro_parent_recall_at_10_pct:pct(recall('routed',10),targetTotal)
    }
  };
}

async function main(){
  const cases=readJsonl(CASES_PATH);
  if(cases.length!==EXPECTED_CASES) throw new Error(`expected ${EXPECTED_CASES} frozen excluded-title cases, got ${cases.length}`);
  const response=await fetch(YV_URL);
  if(!response.ok) throw new Error(`YV source HTTP ${response.status}`);
  const bytes=Buffer.from(await response.arrayBuffer());
  const sha=crypto.createHash('sha256').update(bytes).digest('hex');
  if(sha!==YV_SHA256) throw new Error(`YV source drift: ${sha}`);
  const doc=JSON.parse(bytes.toString('utf8'));
  const items=doc.data;
  if(!Array.isArray(items)) throw new Error('YV data missing');
  const occupationById=new Map(items.filter(x=>x.type==='occupation-name').map(x=>[x.id,x]));

  const detail=[];
  for(const c of cases){
    const targetIds=new Set(c.candidate_occupation_identities.map(x=>x.concept_id));
    const current=directResults(items,c.query);
    const routed=routedResults(current,targetIds,occupationById);
    const measure=(results)=>{
      const ranks=[];
      results.forEach((r,i)=>{ if(targetIds.has(discoveryOccupationId(r))) ranks.push(i+1); });
      return {
        result_count:results.length,
        first_target_rank:ranks.length?ranks[0]:null,
        target_hits_at_5:ranks.filter(x=>x<=5).length,
        target_hits_at_10:ranks.filter(x=>x<=10).length,
        top10:results.slice(0,10).map(r=>({rank:results.indexOf(r)+1,type:r.type,id:r.id,label:r.preferred_label,parent_id:r.occupation_name_id??null,score:r.score,weight:r.weight??0,target:targetIds.has(discoveryOccupationId(r)),route:r.route??'current'}))
      };
    };
    const cm=measure(current), rm=measure(routed);
    const firstTarget = cm.first_target_rank===null ? null : current[cm.first_target_rank-1];
    const preceding = cm.first_target_rank===null ? current : current.slice(0,cm.first_target_rank-1);
    const higherScorePrefixShadow = Boolean(firstTarget && preceding.some(r=>r.type==='job-title' && r.score>firstTarget.score && norm(r.preferred_label).startsWith(norm(c.query))));
    detail.push({
      id:c.id, query:c.query, reason:c.yv_exclusion_reason, observed_count:Number(c.observed_count), target_parent_count:targetIds.size,
      current:cm, routed:rm,
      mechanism:{
        higher_score_prefix_shadow:higherScorePrefixShadow,
        rows_before_first_target:cm.first_target_rank===null?current.length:cm.first_target_rank-1,
        non_target_prefix_job_titles_before_first_target:preceding.filter(r=>r.type==='job-title' && norm(r.preferred_label).startsWith(norm(c.query))).length
      }
    });
  }

  const byReason={};
  for(const reason of [...new Set(detail.map(x=>x.reason))].sort()) byReason[reason]=summarize(detail.filter(x=>x.reason===reason));
  const worst=[...detail]
    .filter(x=>x.current.first_target_rank===null || x.current.first_target_rank>1)
    .sort((a,b)=>b.observed_count-a.observed_count)
    .slice(0,30)
    .map(x=>({id:x.id,query:x.query,reason:x.reason,observed_count:x.observed_count,target_parent_count:x.target_parent_count,current_first_target_rank:x.current.first_target_rank,routed_first_target_rank:x.routed.first_target_rank,higher_score_prefix_shadow:x.mechanism.higher_score_prefix_shadow,current_top5:x.current.top10.slice(0,5)}));

  const result={
    schema_version:1,
    taxonomy_version:31,
    role:'Track-1 diagnostic of generator-excluded exact-title ranking',
    source:{yv_url:YV_URL,yv_sha256:sha,cases_path:CASES_PATH,cases:cases.length},
    interpretation_guardrails:[
      'candidate occupation parents are routing/context evidence from the frozen generator mapping, not adjudicated proof that every parent is equally user-intended',
      'the route counterfactual is exact excluded-title only; it is not a proposal to globally prefer occupation-name over job-title results',
      'observed_count weights are exact query counts from the frozen source corpus and do not prove selection or satisfaction'
    ],
    summary:summarize(detail),
    by_reason:byReason,
    highest_volume_current_rank_failures:worst,
    detail
  };
  fs.mkdirSync('artifacts',{recursive:true});
  fs.writeFileSync('artifacts/yv-excluded-title-ranking-v31.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({summary:result.summary,by_reason:result.by_reason,highest_volume_current_rank_failures:worst.slice(0,12)},null,2));
}
await main();
