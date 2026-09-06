#!/usr/bin/env python3
from pathlib import Path

p=Path('scripts/build_findability_should_find_cases.py')
s=p.read_text(encoding='utf-8')
old='''    query_items = [(q, count, set(word_tokens(q))) for q, count in query_counts.items()]\n    context_cases: list[dict[str, Any]] = []\n    for rows in multi:\n        title = str(rows[0].get("preferred_label") or "")\n        title_tokens = set(word_tokens(title))\n        if not title_tokens:\n            continue\n        parent_tokens = {\n            str(r.get("occupation_name_id") or ""): set(word_tokens(r.get("occupation_name_preferred_label")))\n            for r in rows if r.get("occupation_name_id")\n        }\n        for q, count, qtokens in query_items:\n            if count <= 0 or norm(q) == norm(title) or not title_tokens.issubset(qtokens):\n                continue\n            extra = qtokens - title_tokens\n'''
new='''    query_items = [(q, count, set(word_tokens(q))) for q, count in query_counts.items()]\n    token_postings: dict[str, set[int]] = collections.defaultdict(set)\n    for index, (_q, count, tokens) in enumerate(query_items):\n        if count <= 0:\n            continue\n        for token in tokens:\n            token_postings[token].add(index)\n\n    context_cases: list[dict[str, Any]] = []\n    for rows in multi:\n        title = str(rows[0].get("preferred_label") or "")\n        title_tokens = set(word_tokens(title))\n        if not title_tokens:\n            continue\n        candidate_indices: set[int] | None = None\n        for token in title_tokens:\n            postings = token_postings.get(token, set())\n            candidate_indices = set(postings) if candidate_indices is None else candidate_indices & postings\n            if not candidate_indices:\n                break\n        if not candidate_indices:\n            continue\n        parent_tokens = {\n            str(r.get("occupation_name_id") or ""): set(word_tokens(r.get("occupation_name_preferred_label")))\n            for r in rows if r.get("occupation_name_id")\n        }\n        for index in sorted(candidate_indices):\n            q, count, qtokens = query_items[index]\n            if norm(q) == norm(title):\n                continue\n            extra = qtokens - title_tokens\n'''
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise RuntimeError('builder optimization anchor drift')
p.write_text(s,encoding='utf-8')
print('optimized findability context-query candidate lookup')
