# Semantic display hard-confusion v1 — 2026-09-10

## Question

Does richer positive candidate-specific task evidence improve semantic rejection of independently defined adjacent-role hard negatives without sacrificing the true structured target?

The protocol was frozen before outcomes in `research/evaluation/v31/semantic-display-hard-confusion-v1-preregistration.json`. Opened 17/88 rows were not loaded for design, execution or selection.

## Evidence

- fixed pre-existing hard-confusion panel: 11 pairs / 22 concepts;
- independent historical Platsbanken task text from 2022;
- 79 accepted cases across the preregistered pair population;
- control evidence: frozen v0 compact candidate evidence;
- challenger evidence: same canonical identity/definition evidence plus all six pre-existing canonical-derived positive task atoms;
- same conservative `keep | uncertain | drop` oracle contract;
- structured target, rank and SSYK hidden from the oracle.

## Result

| metric | control | richer positive evidence |
|---|---:|---:|
| target non-drop | 78/79 = 98.73% | **79/79 = 100%** |
| target drops | 1 | **0** |
| hard-negative drops | **16/79 = 20.25%** | 13/79 = 16.46% |

Hard-negative drop improvement was **-3.80 percentage points**.

The sample and target-safety gates passed. The preregistered absolute hard-negative gate (>=70%) and materiality gate (>=+10 pp versus control) both failed. Therefore the overall decision gate failed.

## Decision

**Reject richer positive task evidence as the next display-precision mechanism.** It increased target safety slightly but did not discriminate adjacent roles; hard-negative rejection was slightly worse than the compact control.

Do not replay opened 17/88 and do not distill this evidence contract. Do not tune from the known nursing/electrician stress examples.

The next bounded question is different: can **explicit source-grounded contrastive evidence** identify what distinguishes two plausible neighboring roles, rather than merely adding more positive descriptions of each role? That mechanism must be frozen before evaluation on a new independent time slice.

Human/domain-expert relevance judgments remain the decisive promotion evidence when available.
