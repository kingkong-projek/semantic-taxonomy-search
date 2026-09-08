# Real-user YV/KV findability feedback — 2026-09-07

**Status:** decision-bearing field evidence; root causes partly unresolved  
**Source:** one downstream service that embeds YV/KV  
**Raw source:** workbook received 2026-09-07; not committed here  
**Derived corpus:** `research/evaluation/v31/field-feedback-findability-2026-09-07.json`

## Evidence boundary

The workbook states that the survey had **88 free-text responses**. The supplied sheet contains **52 selected comments** plus a pre-existing category summary. The 52 rows are therefore a curated subset, not a representative frequency sample of all 88 responses.

The comments concern a downstream service that uses YV/KV, but they also describe that service's own profile model, migration, education fields, CV handling, location choices and other UX. A complaint in this source is **not automatically a YV or KV defect**.

This analysis therefore treats each comment as a symptom and assigns only a provisional failure layer until it can be reproduced against the exact YV/KV product behaviour.

The raw comments are not copied into the repository. The structured corpus keeps source-row provenance and only the minimum non-identifying wording needed to reproduce a YV/KV question.

## Main findings

### 1. The existing label `Bristfällig taxonomi` is not a root-cause category

The workbook's summary groups many different mechanisms together. At minimum the field evidence contains:

- occupation-title findability / vocabulary failures;
- skill findability / vocabulary failures;
- plausible-but-wrong occupation mappings;
- irrelevant occupation-context skill suggestions;
- stale or non-current terminology;
- multi-role expression problems;
- downstream-service UX/data-model problems unrelated to YV/KV;
- genuinely unknown cases where the taxonomy concept may be missing.

No broad taxonomy change should be justified from the aggregate category alone.

### 2. Nine comments explicitly report highly implausible KV context suggestions

The selected rows include explicit examples such as:

- `IT Operations Manager` → doctor-related competence;
- `Badvakt` → `Truckvana`;
- `Grafisk designer` → truck-related competence;
- `Project Manager` → doctor/nurse degree;
- `Head of Brand` / `Content Producer` / `Head of Communication` → doctor/truck/nurse suggestions;
- `Lönespecialist` → truck licence while salary/personnel competence is absent;
- `Leveranspersonal` → doctor degree;
- `VD-assistent` / `administratör` → truck/doctor suggestions;
- `Kock storkök` → doctor degree.

The repetition of a small set of absurd suggestions across unrelated occupations is evidence for a **shared failure path**, not nine independent semantic mistakes. Plausible mechanisms include wrong context identity, fallback behaviour, stale/mismatched data or a downstream integration error.

A specific hypothesis is that a selected YV `job-title` identity may have been supplied where KV expects an `occupation-name`/SSYK context. That hypothesis is **not proven by this feedback**. A colleague has already contacted the downstream users/owners, so consumer investigation is outside the current repo work.

The current YV/KV product contract in `kingkong-projek/yrkesvaljaren` is nevertheless relevant as a regression boundary: a selected `job-title` carries its occupation context separately, and the stepped integration test verifies that KV receives the related `occupation-name` ID rather than the `job-title` ID.

### 3. Real users supply valuable YV findability cases

Examples include:

- `CRM Manager` where the offered `Systemansvarig` interpretation was explicitly rejected as too technical;
- `Revenue Manager`;
- `Advanced Manufacturing Engineer`;
- `Global Manufacturing Engineer`;
- `Black Belt`;
- `Research Director`;
- `Project Manager` / `Projektledare`;
- `Instruktör/Handledare i offentlig sektor`;
- `Processrevisor` / `Processberedare`;
- patent/IP administration where `Paralegal` was considered too broad/wrong;
- communication/IT-role coverage;
- employer-specific or international titles.

These must be split into four materially different outcomes:

```text
A. intended concept exists and current YV finds it
B. intended concept exists but wording/alias/ranking prevents discovery
C. wording maps to several valid occupations and needs context/disambiguation
D. no adequate canonical concept exists
```

Only D is evidence for a taxonomy-content gap. B is a selector/retrieval problem. C is an ambiguity/product-flow problem. A points away from YV and toward the downstream integration or user journey.

### 4. Real users also supply KV lexical/semantic cases

High-signal examples include:

- `systemadministration`;
- `research design` for a research role;
- salary/personnel competence for `Lönespecialist`;
- IT certificates / IT competences;
- `Krita`, `Aseprite`, `Blender`, `GameMaker`;
- international/equivalent competence wording;
- a stale `Windows Azure` vs `Microsoft Azure` naming complaint;
- profession-specific certification that could not be represented as a competence.

Again, the first question is not "should semantic search learn this phrase?". The first question is whether the canonical skill exists, whether an alternative/hidden label already covers it, whether current KV can retrieve it, and only then whether description fallback adds value.

### 5. Requests for free text do not imply that free text should become the stored identity

Several users ask to type their own occupation, competence or work description. That is strong evidence that the current **discovery language** can be insufficient. It is not by itself evidence that downstream systems should abandon canonical taxonomy IDs.

The preferred architecture remains:

```text
user's own wording / work description
        ↓
find or propose one or more canonical occupation/skill candidates
        ↓
user confirms
        ↓
canonical taxonomy IDs propagate downstream
```

This is consistent with the semantic-description hypothesis: free text is an input to mapping, not a fabricated taxonomy identity.

### 6. Combined roles are not automatically a taxonomy representation failure

Comments such as `ekonomi + lön + administration`, `Produktägare + Gruppchef`, or `KAM + webb/marknad` may be representable as multiple canonical occupation selections rather than one free-text super-role.

This becomes a concrete product test:

1. can the user discover each intended occupation;
2. can YV preserve several selections/context identities;
3. can KV use several occupation contexts coherently;
4. can the consuming service persist the resulting canonical IDs.

The downstream persistence question is out of scope here. In our own products, multi-selection and multi-context behaviour are testable: YV exposes multiple selection, while KV exposes one priority `af-occupation-id` plus additional `af-input-ids` context IDs.

## Decision update

The earlier plan parked broad ordinary YV/KV expansion and stopped semantic retrieval micro-optimisation until new independent human/user evidence or a measured product failure appeared.

This feedback satisfies that trigger. Ordinary YV/KV is reopened only as a bounded field-feedback replay, while semantic-description work remains separate.

The bounded replay must not turn into a general YV/KV rewrite. Its purpose is to classify real failures and choose the cheapest responsible layer.

## Action order

1. **Freeze the derived field corpus.** Keep row provenance, stream, observed symptom and expected product property. Do not turn the user's proposed solution (`fritext`, `CV`) into ground truth.
2. **Replay occupation-title cases against exact current YV.** For each title classify A/B/C/D above.
3. **Replay competence terms against exact current KV globally and with valid occupation context where known.** Distinguish missing canonical skill from selector-recall/ranking failure.
4. **Test multi-role mechanics in the owning product.** Verify YV multiple selections and KV multi-context weighting with deterministic browser tests.
5. **Keep the absurd-suggestion cluster as an external/context hypothesis until it reproduces inside the owning product.** Do not encode `doctor degree must never appear for X` as a product regression unless the same failure can be produced using valid YV/KV inputs.
6. **Promote only reproduced product-native failures to `kingkong-projek/yrkesvaljaren`.** Product fixes and regression tests belong there.
7. **Use residual description-language failures to evaluate semantic description search.** A case becomes semantic-search evidence only after ordinary canonical lookup/alias/context handling is shown insufficient.
8. **Preserve canonical-gap cases for later taxonomy improvement work.** They are not YV/KV bugs, but they are valuable evidence for improving the taxonomy itself.

## Success criteria for this field-feedback slice

For every YV/KV-relevant case we should eventually have one of:

- `CURRENT_PRODUCT_OK` — current YV/KV already satisfies the need;
- `PRODUCT_NATIVE_BUG` — reproducible defect with regression test/fix in `yrkesvaljaren`;
- `LEXICAL_OR_ALIAS_GAP` — existing concept but current ordinary lookup fails;
- `AMBIGUOUS_NEEDS_CONTEXT` — several canonical mappings are defensible;
- `CANONICAL_CONCEPT_GAP` — no adequate active taxonomy identity found; preserve for later taxonomy improvement;
- `SEMANTIC_DESCRIPTION_RESIDUAL` — ordinary structured discovery is insufficient but a canonical target exists;
- `DOWNSTREAM_ONLY` — belongs to the consuming service and is not pursued in these repos;
- `UNKNOWN` — evidence is insufficient.

Do not collapse these states back into `bristfällig taxonomi`.