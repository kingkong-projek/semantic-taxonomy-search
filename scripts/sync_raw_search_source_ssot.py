#!/usr/bin/env python3
import json
from pathlib import Path

PLAN = Path("docs/research-plan.md")
ADAPTERS = Path("research/coverage/source-adapters.json")

text = PLAN.read_text(encoding="utf-8")

replacements = [
    (
        "### 5.5 Observed YV query language\n\nThe generator-bound Platsbanken query snapshot contains:",
        "### 5.5 Observed YV query language — generator-bound cumulative snapshot\n\nThe generator-bound cumulative Platsbanken query snapshot contains:",
    ),
    (
        "Evidence: `docs/findings/yv-observed-query-language-v31.md` and `research/coverage/v31/yv-query-language-aggregate.json`.\n\n### 5.6 Published Kompetensväljaren v31",
        """Evidence: `docs/findings/yv-observed-query-language-v31.md` and `research/coverage/v31/yv-query-language-aggregate.json`.

### 5.5.1 Raw public JobSearch Trends

The complete Yrkesväljaren source and its upstream `job-ads/search-trends` generator are now audited end-to-end.

The committed `data/sokningar-platsbanken.json.zip` is **not the raw public search source**. `update_search_terms.py` reads only `q_approved` from public daily JobSearch Trends files, retains terms with at least 10 searches on a day, sums over time, performs small whitespace/hyphen normalization and then removes cumulative terms below 100.

The public source is materially richer:

- **1,256 dated ZIP files** were present in the current listing, from **2022-05-04 through 2026-09-04**;
- that interval contains 1,585 calendar days, so **329 dates currently have no published ZIP**; absence is `UNKNOWN`, not zero;
- the first sampled daily file contains **15,425** distinct `q_approved` values;
- the 2026-09-04 sample contains **100,342** distinct `q_approved` values;
- public files also contain independent daily counters for several structured JobSearch parameters such as occupation group/field/name and geography.

Upstream source semantics are decisive: JobSearch Trends summarizes `/search` request logs by parameter and explicitly does **not** publish complete parameter combinations. `q_approved` is free text that passed a whitelist/stemming privacy filter intended to remove PII. It does **not** mean semantically approved, taxonomy-mapped or selected by a user.

Therefore:

```text
raw daily JobSearch Trends
  = behavioral language + time/frequency + independent parameter marginals
  != query -> selected canonical identity ground truth
```

The current public field whitelist does not expose structured `skill` counts. Same-day free text and taxonomy-ID counters may never be paired as if they came from the same request.

Raw JobSearch Trends is now a first-class Gate-2 source for recency, trend, long-tail and benchmark sampling. The cumulative generator snapshot remains the reproducible evidence source for current YV weighting/admission analysis.

Evidence: `docs/findings/yrkesvaljaren-jobsearch-trends-source-audit-2026-09-06.md` and `research/coverage/jobsearch-trends-source-probe-2026-09-06.json`.

### 5.6 Published Kompetensväljaren v31""",
    ),
    (
        "Generic public JobSearch Trends beyond the exact generator-bound snapshot remain **not a Gate-1 blocker**. Their lineage can be sampled later if the measured YV snapshot is insufficient.",
        "Raw public JobSearch Trends lineage is now audited end-to-end. It does not reopen Gate 1 because it does not change the canonical target universe or provide query→selection ground truth, but it is a first-class Gate-2 behavioral source and must be sampled with date/source provenance.",
    ),
    (
        "- unbound observed query-language samples with **manual judgments**, not auto-labels;\n- task/skill description→occupation;",
        "- unbound observed query-language samples with **manual judgments**, not auto-labels;\n- raw daily JobSearch Trends recency/long-tail samples, with `q_approved` treated only as privacy-filtered behavioral wording;\n- task/skill description→occupation;",
    ),
    (
        "- observed query frequency is not query→selection ground truth;\n- model-derived ad enrichment is not human ground truth;",
        "- observed query frequency is not query→selection ground truth;\n- JobSearch Trends `q_approved` means privacy-filtered public free text, not semantic approval or a selected target;\n- public JobSearch Trends fields are independent daily aggregate marginals and must never be interpreted as same-request co-occurrence;\n- model-derived ad enrichment is not human ground truth;",
    ),
    (
        "→ real query/search language with explicit join semantics",
        "→ raw + cumulative real query/search language with date/source provenance and explicit non-join semantics",
    ),
    (
        "### Now — Gate 2\n\n- [x] benchmark schema and semantic validator contract\n- [ ] high-confidence judged seed cases",
        "### Now — Gate 2\n\n- [x] benchmark schema and semantic validator contract\n- [ ] bounded raw JobSearch Trends date-range adapter + exact dated-file manifest + recency/long-tail strata\n- [ ] targeted source-gap inventory against measured weak strata: AF catalog first, ESCO through existing typed mappings, Sveriges dataportal as discovery index; admit a source only with explicit join/provenance semantics\n- [ ] high-confidence judged seed cases",
    ),
    (
        "9. Observed YV search corpus direct selected-ID labels? **No; query + frequency only**.",
        "9. Observed search data direct selected-ID labels? **No. The YV cumulative snapshot is query + frequency; raw daily JobSearch Trends adds time and independent structured-parameter counts, but explicitly omits complete request combinations and therefore still has no query→selected-ID join.**",
    ),
    (
        "30. What does observed `quality-level` mean on non-occupation types, and does it affect retrieval enough to justify a Gate-1 adapter?",
        "30. What does observed `quality-level` mean on non-occupation types, and does it affect retrieval enough to justify a Gate-1 adapter?\n31. How much vocabulary and recency signal is lost by the YV `>=10/day` and `>=100 cumulative` filters, and which raw-date windows are most useful for Gate-2 sampling?\n32. How much incremental Swedish semantic text do mapped ESCO v1.2.1 concepts add specifically to the 244 weak YV occupations and 1,410 critical-sparse KV skills?\n33. How much of the critical-sparse KV population is covered by AF's manually mapped labour-market-training learning outcomes and other explicitly curated domain sources?",
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one SSOT match, got {count}: {old[:100]!r}")
    text = text.replace(old, new)

PLAN.write_text(text, encoding="utf-8")

registry = json.loads(ADAPTERS.read_text(encoding="utf-8"))
registry["last_updated"] = "2026-09-06"
adapters = registry["adapters"]
by_id = {a["id"]: a for a in adapters}

existing = by_id["yv-observed-query-language"]
existing["notes"] = (
    "Generator-bound cumulative derivative of public daily JobSearch Trends: 115,553 retained terms and 3.136B retained searches "
    "for 2022-05-04 through 2026-08-16 after the YV updater keeps >=10/day, aggregates, normalizes lightly and keeps >=100 cumulative. "
    "11.153% of retained volume exactly matches generator-excluded job-title vocabulary and 67.377% is not exactly bound to admitted/excluded YV labels. "
    "This is behavioral query-frequency evidence, not query→selected canonical ID ground truth."
)

raw = {
    "id": "jobsearch-trends-raw-daily",
    "status": "partially_measured",
    "provenance_class": "behavioral",
    "target_types": ["query-language", "occupation-name", "ssyk-level-4"],
    "join_key": "none from q_approved to a canonical target; structured fields contain IDs only within independent daily parameter marginals",
    "dimensions": ["daily q_approved frequency", "date", "structured occupation/filter frequencies", "dated source-file manifest", "recency/trend"],
    "source": "https://data.arbetsformedlingen.se/annonser/search-trends",
    "evidence": [
        "docs/findings/yrkesvaljaren-jobsearch-trends-source-audit-2026-09-06.md",
        "research/coverage/jobsearch-trends-source-probe-2026-09-06.json"
    ],
    "notes": (
        "Upstream source commit 7f3d919a876550678341ff43fecb98f42b98896b summarizes JobSearch /search request logs into public daily parameter-wise counts. "
        "q_approved is privacy-filtered/whitelist-approved free text, not semantic approval. Complete request combinations are explicitly not public, so same-day q and taxonomy-ID counters cannot be joined. "
        "Current probe found 1,256 dated ZIPs from 2022-05-04 through 2026-09-04. Public fields expose occupation-oriented counters but currently omit the structured skill field. "
        "Use for Gate-2 recency/long-tail/trend sampling, never as destination ground truth without independent evidence or judgment."
    )
}

if raw["id"] in by_id:
    idx = next(i for i,a in enumerate(adapters) if a["id"] == raw["id"])
    adapters[idx] = raw
else:
    idx = next(i for i,a in enumerate(adapters) if a["id"] == "yv-observed-query-language") + 1
    adapters.insert(idx, raw)

ADAPTERS.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("SSOT and source adapter registry updated")
