#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
t = p.read_text(encoding='utf-8')

old_boundary = (
    "Therefore **plain G1+T3 is the current simple research boundary and no higher model class is justified now**. "
    "Stop retrieval micro-optimization until new independent human/user evidence or a measured product failure identifies a material residual. "
    "The next evidence priority is the bounded product hypothesis itself: whether users who fail ordinary lexical lookup can describe tasks/tools/methods/responsibilities well enough to recognise and select the intended canonical candidate from a small fallback result set."
)
new_boundary = (
    "Therefore **plain G1+T3 remains the current promoted simple runtime boundary**. The live demo failures and the later 88-input dual-stream stress replay now provide a measured product residual sufficient to authorize bounded architecture diagnostics above that boundary: domain-vocabulary and keyword-like input can work well, while colloquial paraphrase, indirect narrative language and abstention remain materially weak. This does **not** promote a heavier runtime model. Stop micro-tuning the already-opened retrieval cases; instead run the compile-time semantic tournament below, and require new independent stream-separated evidence before any runtime promotion."
)
count = t.count(old_boundary)
if count != 1:
    raise RuntimeError(f'expected exactly one old complexity-boundary paragraph, got {count}')
t = t.replace(old_boundary, new_boundary, 1)

anchor = "**Description-ranking metric contract (2026-09-07): Hit@5 is secondary historical recall, not the product-quality headline.**"
if t.count(anchor) != 1:
    raise RuntimeError(f'expected exactly one description-ranking metric anchor, got {t.count(anchor)}')

section = r'''**Compile-time semantic tournament (ACTIVE next architecture phase; 2026-09-07).** The target universe is small and mostly static, so the next architecture question is not `which neural model can the browser tolerate?` but **how much semantic intelligence can be paid once at build time and compiled into a tiny deterministic runtime artifact**. Large/expensive teachers may therefore be used freely offline to generate, score, contrast, distil and prune evidence. The browser must not inherit their parameter count or runtime dependency.

The tournament keeps the current exact router + BM25 candidates as the cheap runtime baseline. The frozen dense diagnostics based on `intfloat/multilingual-e5-small` are a **teacher/semantic ceiling and candidate-generation probe, not a browser candidate**. The opened 88-input stress replay already shows why a pure BM25-top-N reranker is insufficient for YV: plausible targets can sit far outside a practical rerank window, while a dense lane can recover complementary candidates. The same opened replay also shows that dense retrieval over thin canonical YV text is not enough by itself; employer-language and Relevanta-kompetenser representations are materially complementary. These results are architecture evidence only, not promotion evidence.

Tournament entrants, at minimum:

1. **A — teacher/doc2query-expanded sparse BM25.** Use large teachers offline to generate diverse Swedish user-language descriptions for each canonical concept (task language, colloquial paraphrases, tools/methods, misspellings/noise, indirect narrative forms and hard negatives), then prune/compile the useful language into provenance-separated sparse documents. Runtime remains tokenization + sparse scoring; no model ships to the client.
2. **B — teacher-distilled sparse feature→concept index.** Distil teacher relevance directly into weighted lexical features such as words, character n-grams and short phrases mapped to canonical concept IDs, including hard-negative evidence. Runtime is dictionary lookup + deterministic score accumulation.
3. **C — quantized low-rank domain student.** Train only the closed task `Swedish work/skill description -> fixed taxonomy identities`, using teacher-labelled positives, alternatives, ambiguity and hard negatives. Prefer hashed word/character features with a very small latent space or equivalent non-transformer machinery; runtime should be table lookup + small vector arithmetic, not general language-model inference.
4. **Static-embedding/Model2Vec-style distillation may enter as a reference challenger** if it obeys the same client budget; it is not privileged merely because it is called a model.

Teacher diversity is allowed and desirable at compile time: dense retrievers, Swedish sentence models, cross-encoders and capable LLMs may all contribute labels, generated language, pairwise preferences and hard negatives. Their disagreement must be retained as evidence rather than silently collapsed into false ground truth. Source-attested taxonomy/AF evidence remains provenance-distinct from generated teacher language.

**Hard client/runtime constraint:** judge actual incremental transfer size and runtime cost, not parameter-count marketing. The preferred frontend target is **<=3 MB compressed incremental semantic artifact**; **>5 MB compressed is a frontend-track failure** unless later real product evidence explicitly changes this constraint. No transformer or general LLM inference is allowed in the browser candidate set under the current constraint. Measure compressed bytes, parse/init memory and warm-query latency on a representative mid-range Android device before promotion.

**Tournament evaluation order:**

- freeze each entrant definition, teacher/model revision, generated corpus hashes, pruning/distillation parameters and size before comparison;
- use the opened 88-input stress suite only for architecture diagnosis and regression replay, never to tune thresholds/fusion or claim accuracy;
- cross-check against the existing source-attested opened YV/KV description evidence and all exact/canonical regression guards;
- report rank-sensitive quality (Top1, first acceptable rank/MRR, nDCG@5 where applicable, unacceptable-prefix burden, list precision and abstention), plus candidate recall before final ranking;
- separately measure transfer bytes, initialization/memory and runtime latency;
- no entrant can be promoted from synthetic/opened evidence alone: final promotion still requires fresh independent stream-separated human/user evidence under the existing study contract.

**Win/stop rule:** a compile-time entrant earns continued frontend consideration only if it preserves exact/canonical behavior, materially improves the paraphrase/indirect residual over BM25, handles weak/out-of-scope input more conservatively, and on fresh independent evidence retains most of the useful dense semantic lift while remaining within the client budget. If no <=5 MB compiled candidate clears that bar, **stop trying to ship semantic intelligence in the browser**: keep ordinary lexical/BM25 behavior local and use a server/API semantic fallback only for the residual description path. API is the explicit escape hatch, not a research failure.

'''
t = t.replace(anchor, section + anchor, 1)

p.write_text(t, encoding='utf-8')
