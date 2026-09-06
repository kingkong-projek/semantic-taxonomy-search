#!/usr/bin/env python3
from pathlib import Path

path = Path("scripts/evaluate_pareto_c1.py")
text = path.read_text(encoding="utf-8")
old = '''def rank_c1(
    ranker: BM25,
    query: str,
    exact_surfaces: dict[str, set[str]],
    surface_tokens: dict[str, set[str]],
) -> list[tuple[str, float, str]]:
    qtokens = tokens(query)
    short_query = len(qtokens) <= 3
    boosts = {4: 1_000_000.0, 3: 10_000.0, 2: 5_000.0, 1: 2_500.0, 0: 0.0}
    scored: list[tuple[str, float, str]] = []
    for cid in ranker.documents:
        signal, signal_name = surface_signal(query, exact_surfaces[cid], surface_tokens[cid])
        lexical = ranker.score(qtokens, cid)
        if short_query and signal == 0:
            continue
        if not short_query and signal == 0 and lexical <= 0.0:
            continue
        score = lexical + boosts[signal]
        if score > 0.0:
            scored.append((cid, score, signal_name))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored
'''
new = '''def rank_c1(
    ranker: BM25,
    query: str,
    exact_surfaces: dict[str, set[str]],
    surface_tokens: dict[str, set[str]],
) -> list[tuple[str, float, str]]:
    qtokens = tokens(query)
    short_query = len(qtokens) <= 3
    boosts = {4: 1_000_000.0, 3: 10_000.0, 2: 5_000.0, 1: 2_500.0, 0: 0.0}
    scored: list[tuple[str, float, str]] = []
    nq = norm(query)
    for cid in ranker.documents:
        lexical = ranker.score(qtokens, cid)

        if short_query:
            # Short picker-style queries are where lexical surface evidence is useful
            # and where definition-only overlap caused false confident geography hits.
            signal, signal_name = surface_signal(query, exact_surfaces[cid], surface_tokens[cid])
            if signal == 0:
                continue
            score = lexical + boosts[signal]
        else:
            # Description-style queries keep C0 semantics. Token/component/fuzzy
            # surface boosts on long text caused incidental words to overpower the
            # concept's own definition in the frozen source-truth regression.
            signal_name = "exact_surface" if nq and nq in exact_surfaces[cid] else "definition_bm25"
            score = lexical + (1_000_000.0 if signal_name == "exact_surface" else 0.0)
            if score <= 0.0:
                continue

        scored.append((cid, score, signal_name))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected exactly one rank_c1 block, got {text.count(old)}")
text = text.replace(old, new, 1)
text = text.replace(
    '"ranking": "deterministic BM25 plus deterministic label-surface dominance: exact surface > exact label token > component > bounded fuzzy > definition-only",',
    '"ranking": "short queries: deterministic label-surface dominance (exact > token > component > bounded fuzzy); long descriptions: unchanged C0 BM25 with exact-full-surface dominance only",',
    1,
)
text = text.replace(
    '"abstention": "queries of <=3 tokens require label/alternative-label surface evidence; longer description queries may use definition-only lexical evidence",',
    '"abstention": "queries of <=3 tokens require label/alternative-label surface evidence; longer descriptions retain C0 definition-BM25 behavior",',
    1,
)
path.write_text(text, encoding="utf-8")
print("patched C1 so surface/component/fuzzy boosts apply only to short queries")
