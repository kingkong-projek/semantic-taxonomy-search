# A593 training-language diversity — 2026-09-09

## Decision

**Do not scale the current synthetic Gemma language-diversity policy to A593/A2105 yet. Keep architecture A as the surviving simple family, keep A2105 paused, and move the next decision-bearing step to fresh independent human/user description evidence.**

The bounded experiment produced a strong prefrozen synthetic transfer gain, but that gain did not reproduce on the already-opened full-universe user-like residual. The opened replay is diagnostic only and must not be tuned from.

## What was held fixed

The experiment changed training-language distribution only:

- same A-family flattened token BM25 ranker;
- same canonical source representation;
- no runtime model or second semantic stage;
- frozen A593 teacher corpus retained;
- 466 accepted, separately generated source-bound phrases appended to 133 A593 concepts;
- training and holdout language generated in separate calls from canonical/source evidence;
- old A593 phrases were not sent to the generator;
- generated language containing occupation-title surfaces or contiguous source fourgrams was rejected; holdout language was additionally separated from new training phrases;
- opened 17/88 was not loaded during generation or candidate selection.

## Prefrozen synthetic transfer gate

On 446 valid separately generated held-out cases:

| Metric | A control | A + diversified language | Delta |
|---|---:|---:|---:|
| Top1 | 286/446 = 64.13% | 323/446 = 72.42% | **+37 / +8.30 pp** |
| Hit@5 | 380/446 = 85.20% | 406/446 = 91.03% | **+26 / +5.83 pp** |
| MRR | 0.734509 | 0.806519 | **+0.072010** |

Paired Top1 changes were 42 gains versus 5 losses. The strongest synthetic style was `shift_story`: Top1 improved from 40/122 (32.79%) to 59/122 (48.36%), **+15.57 pp**. The preregistered materiality gate passed.

On the separately frozen 66-case hard-confusion replay, Top1 improved by 4 cases and Hit@5 was unchanged, so the additional language did not show a local confusion regression there.

Evidence:

- `research/evaluation/v31/a593-language-diversity-generation-v0.json`
- `research/training/v31/a593-language-diversity-training-v0.jsonl`
- `research/evaluation/v31/a593-language-diversity-holdout-v0.jsonl`
- `research/evaluation/v31/a593-language-diversity-result-v0.json`

## Correct full-universe opened replay

The first opened replay file, `research/evaluation/v31/a593-language-diversity-opened-replay.json`, is **superseded and must not be used for architecture/product interpretation**. It mistakenly ranked only the 593 teacher-expanded identities. That is not the A-family product shape, which ranks all 2,105 active occupations and merely appends teacher language to a subset.

The corrected replay hard-asserts parity with the already-frozen A593 full-universe checkpoint before comparing the challenger:

- strict17 control = **5 Top1 / 10 Hit@5 / MRR 0.424510**;
- targetable40 control = **15 Top1 / 26 Hit@5**.

Those parity checks pass exactly.

Corrected opened result:

| Metric | A control | A + diversified language | Delta |
|---|---:|---:|---:|
| targetable40 Top1 | 15/40 | 16/40 | **+1** |
| targetable40 Hit@5 | 26/40 | 24/40 | **-2** |
| strict17 Top1 | 5/17 | 5/17 | 0 |
| strict17 Hit@5 | 10/17 | 10/17 | 0 |
| strict17 MRR | 0.424510 | 0.418237 | **-0.006273** |

The two targetable Hit@5 losses occur in the residual we most wanted to improve:

- colloquial `yv14` (`Jag kryper runt i hus och får lampor och vägguttag att funka`), family rank **3 -> 8**;
- indirect `yv37` (`Jag får trasiga människor att kunna gå ordentligt igen efter operationer`), family rank **5 -> 6**.

A visible Top1 gain occurs in noisy `yv29` (`städar skurar moppar toa kontor varje dag`), family rank **2 -> 1**.

Therefore the large synthetic `shift_story` gain does not reproduce as improvement on the opened colloquial/indirect residual. The full-universe replay is mixed rather than directionally convincing for the target failure mechanism.

Correct evidence:

- `research/evaluation/v31/a593-language-diversity-opened-replay-full-universe.json`

## Interpretation

This result does **not** falsify the general idea that better training language can help sparse retrieval. The prefrozen synthetic transfer result is too large and internally consistent to dismiss, and it establishes that representation A can exploit useful new language without additional runtime architecture.

It does falsify the stronger operational claim that **this current synthetic Gemma diversification policy is sufficiently validated to justify scaling it broadly now**. Same-model/source-generated holdout performance materially overestimated transfer to the already-opened colloquial/indirect residual.

Do not respond by:

- generating the same policy for all 593/2,105 identities;
- tuning prompts or phrases from the opened rows;
- reviving B/C/E or composing them into a hybrid;
- activating D merely because this data experiment did not transfer cleanly.

## Next gate

The next decision-bearing evidence should be fresh, independent human/user descriptions collected under the existing frozen human-study contract. Its purpose is to answer two separate questions:

1. how good is the current simple A-family description fallback on real human wording;
2. does source-bound diversified training language provide repeatable incremental value on that wording without worsening first-acceptable-rank/list precision.

Until that evidence exists:

- **A remains the simplest surviving architecture family;**
- **A2105 remains paused;**
- **synthetic language scaling remains paused;**
- the preferred production shape remains exact/canonical lexical route + one semantic description ranker/index;
- the server/API semantic fallback remains the explicit escape hatch if the client-side simple family ultimately cannot clear independent evidence gates.
