# P80 lexical A/B/C ablation — taxonomy v31

**Status:** measured and frozen  
**Measured:** 2026-09-06

## Result

| configuration | YV top-1 | YV Recall@10 | KV top-1 | KV Recall@10 |
|---|---:|---:|---:|---:|
| A — preferred labels only | 90.1% | 94.0% | 90.1% | 95.1% |
| B — + real canonical definitions | 99.7% | 100.0% | 95.5% | 96.3% |
| C — + canonical alternative labels | **100.0%** | **100.0%** | **100.0%** | **100.0%** |

C has **zero top-1 misses** on all 950 frozen source-truth cases. It is deterministic BM25 over the P80 target documents, with exact canonical preferred/alternative labels treated as exact indexed lexical surfaces.

The first C run exposed punctuation/tokenisation failures for `C`, `C++`, `SQL` and `Windows`. The correction was not a fuzzy special case: exact canonical alternative labels receive the same deterministic exact-surface dominance as preferred labels.

## Boundary

This is an ingestion/retrieval test over source-attested text, **not proof of natural paraphrase performance**. Definitions and alternative labels come from the same accepted taxonomy source used to build the representations.

The result therefore supports one simple decision:

> Do not add embeddings, ESCO enrichment, ad-language ETL or a semantic service merely to consume semantics already present in the P80 taxonomy core.

The next decision-bearing experiment is a small manually judged high-volume real-query sample plus compact safety cases. Additional complexity is deferred until those external-language cases expose a material residual.

## Reproducibility

- benchmark: `research/benchmark/v31/p80-source-truth/`
- evaluator: `scripts/evaluate_p80_lexical_ablation.py`
- result: `research/evaluation/v31/p80-lexical-ablation.json`
- result SHA-256: `f7bc8659cbac6ba7b2e4b7f93b3e206f2042d9678078d4f22bee1255ef27228c`
- taxonomy v31 SHA-256: `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`
