#!/usr/bin/env python3
"""Guard repository-bound human study files against stage/order drift."""
from __future__ import annotations

import json
from pathlib import Path

import validate_human_description_study as base
import verify_human_description_study as verifier

ROOT = Path('research/human/description-fallback-v1')
PREREG = ROOT / 'preregistration.json'
ELICITATION = ROOT / 'elicitation.jsonl'
ADJUDICATION = ROOT / 'adjudication.jsonl'
MANIFEST = ROOT / 'manifest.json'
OUTCOMES = ROOT / 'outcomes.jsonl'
FUNNEL = ROOT / 'need-funnel.json'


def main() -> int:
    staged = [ELICITATION, ADJUDICATION, MANIFEST, OUTCOMES, FUNNEL]
    existing = [path for path in staged if path.exists()]

    if not PREREG.exists() and not existing:
        print('human-description repo state: no real study data collected')
        return 0

    if not PREREG.exists():
        raise RuntimeError(f'real study files exist without frozen preregistration.json: {[str(p) for p in existing]}')

    preregistration = verifier.validate_preregistration(PREREG)

    if ADJUDICATION.exists() and not ELICITATION.exists():
        raise RuntimeError('adjudication exists without elicitation')
    if MANIFEST.exists() and (not ELICITATION.exists() or not ADJUDICATION.exists()):
        raise RuntimeError('manifest requires both elicitation and adjudication')
    if OUTCOMES.exists() and not MANIFEST.exists():
        raise RuntimeError('outcomes exist before freeze manifest')

    elicitation = None
    adjudication = None
    if ELICITATION.exists():
        elicitation = base.validate_elicitation(base.load_jsonl(ELICITATION))
    if ADJUDICATION.exists():
        if elicitation is None:
            raise RuntimeError('internal stage error: adjudication without elicitation')
        adjudication = base.validate_adjudication(base.load_jsonl(ADJUDICATION), elicitation)

    if MANIFEST.exists():
        if elicitation is None or adjudication is None:
            raise RuntimeError('internal stage error: manifest without prior stages')
        verifier.verify_bound_manifest(
            MANIFEST,
            PREREG,
            preregistration,
            ELICITATION,
            ADJUDICATION,
            len(elicitation),
            len(adjudication),
        )

    if OUTCOMES.exists():
        if elicitation is None or adjudication is None:
            raise RuntimeError('internal stage error: outcomes without prior stages')
        base.validate_outcomes(base.load_jsonl(OUTCOMES), elicitation, adjudication)

    if FUNNEL.exists():
        base.validate_funnel(FUNNEL)

    print(
        json.dumps(
            {
                'study_id': preregistration['study_id'],
                'preregistration_frozen': True,
                'elicitation_present': ELICITATION.exists(),
                'adjudication_present': ADJUDICATION.exists(),
                'manifest_present': MANIFEST.exists(),
                'outcomes_present': OUTCOMES.exists(),
                'production_funnel_present': FUNNEL.exists(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
