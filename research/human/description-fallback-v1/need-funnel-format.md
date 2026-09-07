# Need/prevalence funnel format

This aggregate file answers a different question from the staged human case files: **how often is a description fallback actually needed/used after ordinary lexical lookup?**

It intentionally contains no raw query or description text.

Example shape:

```json
{
  "schema_version": 1,
  "measurement_window": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
  "lexical_failure_definition": "prefrozen operational definition",
  "cohorts": [
    {
      "stream": "occupation",
      "eligible_lexical_failure_exposures": 0,
      "fallback_offers": 0,
      "fallback_opens": 0,
      "fallback_submissions": 0,
      "fallback_selections": 0,
      "none_selections": 0
    }
  ]
}
```

Required ordering invariants per cohort:

```text
eligible lexical-failure exposures
>= fallback offers
>= fallback opens
>= fallback submissions
>= fallback selections
```

`none_selections <= fallback_submissions` and `fallback_selections + none_selections <= fallback_submissions`.

`lexical_failure_definition` must be frozen before reading fallback outcomes. Examples of possible product events may include repeated lexical reformulation, zero-result states or explicit “hittar inte” actions, but the study must choose the operational definition before measurement rather than selecting the definition that produces the most favorable uptake rate.

A prompted/recruited capability study does not supply this denominator and therefore cannot estimate production prevalence.
