# Statistical confidence and sampling guardrails — taxonomy v31

**Status:** reporting/evaluation guardrail; no retrieval-policy change.

Percentages in this project do not all have the same statistical meaning. From this point forward, every headline result must state its denominator, evidence role and scope. Confidence intervals are required when a genuinely sampled proportion is being generalized; they are not mechanically attached to exhaustive deterministic slices or proxy-weighted summaries.

## KV description fallback: what is actually known

### First natural holdout — development evidence

35 cases. This slice was opened before the final 3-slot/4-slot fusion choice, so it is useful development evidence but not the final confirmatory test.

- C0: 11/35 Hit@5 = 31.429%; 95% Wilson interval **18.55–47.98%**.
- G1-4slot: 31/35 Hit@5 = 88.571%; 95% Wilson interval **74.05–95.46%**.

Do not use this slice for a post-selection p-value claim about the final policy.

### Second blind holdout — independent validation

20 cases. The benchmark was frozen before the declared 3-slot/4-slot candidate outputs were generated, and both natural holdouts were excluded from G1 retrieval evidence.

- C0: 6/20 Hit@5 = 30.0%; 95% Wilson interval **14.55–51.90%**.
- G1-4slot: 17/20 Hit@5 = 85.0%; 95% Wilson interval **63.96–94.76%**.

The paired outcome is stronger than the small-sample precision of the 85% point estimate suggests:

- 11 C0 misses are rescued;
- 0 C0 hits regress;
- 6 cases remain hits;
- 3 cases remain misses.

An exact two-sided McNemar/binomial test on the 11-versus-0 discordant pairs gives **p = 0.0009765625**.

Interpretation: there is strong evidence that the bounded G1 lane improves Hit@5 over C0 **on this frozen benchmark distribution**. There is much less precision about the absolute success rate in a broader population. `85%` must therefore not be quoted as production accuracy.

### Canonical regression

The frozen canonical regression is **617/617 top-1 and 617/617 Hit@5** for the candidate.

This is a fixed deterministic regression set, not a random production sample. Its primary meaning is: no canonical regression was observed on those 617 frozen source-truth cases. A binomial confidence interval is not the main uncertainty and must not be used to imply production-wide 99.x% safety.

## Weighted percentages

The second blind holdout reports 19.639% weighted Hit@5 for C0 and 89.331% for G1-4slot.

Those weights are historical occurrence proxies, not known sampling probabilities for description-search users. The weighted percentages are therefore useful descriptive prioritisation metrics, but ordinary binomial confidence intervals are **not** valid for them without a defensible sampling/variance model.

## Scope limits that dominate the uncertainty

The confirmatory holdout is small (`n=20`) and covers the **316-skill P80 priority envelope**, not all 6,752 active skills. The descriptions are AF labour-market-training text, which is source-attested natural language but can differ substantially from what real users type. Each blind case is also constructed around exactly one P80 target, so ambiguous/multi-intent user descriptions are underrepresented.

After the second holdout was opened and its three misses inspected, subsequent pruning/ESCO/subword/residual experiments are exploratory. None may replace the validated candidate without another independently frozen validation set.

Synthetic cases and personas are instrumentation/stress evidence, not population samples.

## Track-1 metrics have a different uncertainty class

Several YV/KV selector audits are enumerations of a defined slice rather than random samples:

- all 541 multi-context YV job-title IDs were evaluated for exact search;
- 1,076 deterministic one-edit mutations were evaluated across those 541 IDs;
- all 205 active generator-excluded titles were evaluated;
- strict current canonical alias populations were fully enumerated: 357 YV aliases and 1,279 KV aliases.

Sampling confidence intervals are not the useful uncertainty measure for those defined populations. The uncertainty is instead external validity: how representative those slices are of real traffic and real user intent.

## Reporting rule

From now on, a result such as `85%` is incomplete. Report it as, for example:

> **17/20 Hit@5 = 85.0% (95% Wilson CI 64.0–94.8%), independently frozen P80 training-description holdout; not production accuracy.**

Every headline metric must include numerator/denominator or enumerated population size, evidence role, scope and — where statistically meaningful — uncertainty interval. Proxy-weighted metrics must remain explicitly descriptive unless a valid variance model is established.

Frozen machine-readable summary: `research/evaluation/v31/statistical-confidence-summary.json`.
