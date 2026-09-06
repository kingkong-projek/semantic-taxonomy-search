# P80 source-truth decision benchmark — taxonomy v31

**Status:** frozen and validator-clean  
**Frozen:** 2026-09-06

## Result

The first deterministic Gate-2 benchmark now covers the full **475-target P80 semantic priority core** without synthetic wording or inferred labels.

| product | P80 targets | benchmark cases | preferred-label cases | canonical-definition cases | alternative-label cases |
|---|---:|---:|---:|---:|---:|
| YV | 159 occupation-name | **333** | 159 | 137 | 37 |
| KV | 316 skill | **617** | 316 | 193 | 108 |
| total | **475** | **950** | 475 | 330 | 145 |

Every P80 target is represented. One KV surface is source-truth ambiguous: `Marknadsföring` is an alternative label for both `Marknadsföring/PR` and `Marknadsföring/Marknadskommunikation`; the benchmark correctly retains both identities rather than forcing a single answer.

## What this benchmark proves

This suite is deliberately conservative:

- preferred labels, real canonical definitions and canonical alternative labels are taken from the accepted taxonomy v31 snapshot;
- YV positive identities are additionally checked against published Yrkesväljaren product admission;
- Historical API occurrence counts only selected the P80 population and never become destination truth;
- no observed free-text query, ad-derived phrase, model output or synthetic phrase is auto-labelled as truth.

It is therefore a strong regression/source-ingestion benchmark and a valid first ablation surface for simple lexical evidence layers.

## What it does not prove

The definition and alternative-label cases are source-attested text. They do **not** by themselves establish performance on natural user paraphrases. A small manually judged high-volume observed-query slice remains necessary before conclusions about embeddings or real semantic UX are made.

## Frozen files

- `research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl` — 431,816 bytes — SHA-256 `7bd44757b2eb663e56e2928438caa4789cb0eef064ad01fd3051c9f020de17f9`
- `research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl` — 579,141 bytes — SHA-256 `e5785a648c6cb9e8e618eacd937c4860127cdb97c1aec130335035459d3cf02a`
- `research/benchmark/v31/p80-source-truth/manifest.json` — SHA-256 `b61d8080a8b0a4dbe8078db6dd34ffc98498d5535a01db82d8c29bc35c9726ed`

Builder: `scripts/build_p80_decision_benchmark.py`  
Validator: `scripts/validate_benchmark.py`
