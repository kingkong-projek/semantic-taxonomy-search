#!/usr/bin/env python3
"""Cheap static contract for the zero-backend dual YV/KV fallback demo."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path('demo')
html = (ROOT / 'index.html').read_text(encoding='utf-8')
css = '\n'.join((
    (ROOT / 'styles.css').read_text(encoding='utf-8'),
    (ROOT / 'stream.css').read_text(encoding='utf-8'),
))
app = (ROOT / 'app.js').read_text(encoding='utf-8')
engine = (ROOT / 'search-engine.js').read_text(encoding='utf-8')
all_text = '\n'.join((html, css, app, engine))

required_html = (
    'id="description"', 'id="search-form"', 'id="results-panel"', 'id="export-button"',
    'id="history"', 'id="main"', 'aria-live="polite"', 'role="radiogroup"',
    'id="stream-occupation"', 'value="occupation"', 'id="stream-skill"', 'value="skill"',
    'Prototyp för utvärdering', 'Allt stannar i din webbläsare',
    'Beskriv ditt arbete', 'Mitt yrke', 'En kompetens',
)
for token in required_html:
    if token not in html:
        raise RuntimeError(f'missing demo HTML contract: {token}')

for token in (
    'localStorage', 'new Blob', 'URL.createObjectURL',
    # Stable Pages URL retained even though its engine is no longer the old C2 candidate.
    "occupation: './assets/yv-c2.json?v=a593-cachefix-1'", "skill: './assets/kv-g1-t3.json?v=a593-cachefix-1'",
    "form.addEventListener('submit'", 'const loaded = await ensureEngine(stream);',
    "stream: 'mixed'", "schema_version: 2",
):
    if token not in app:
        raise RuntimeError(f'missing local dual-stream demo behavior: {token}')

if app.count('fetch(') != 1 or 'fetch(MODEL_URLS[stream]' not in app:
    raise RuntimeError('demo must make only the selected relative model fetch lazily')
if "cache: 'no-cache'" not in app or "cache: 'force-cache'" in app:
    raise RuntimeError('demo model loads must revalidate so runtime/model deploys cannot mix')

for token in (
    '@media (max-width: 900px)', '@media (max-width: 640px)', ':focus-visible',
    'prefers-reduced-motion', 'grid-template-columns: minmax(0, 1.72fr)',
    '.stream-options', '.stream-input:checked + .stream-option',
):
    if token not in css:
        raise RuntimeError(f'missing responsive/accessibility CSS contract: {token}')

for token in ('KV-G1+T3-plain-v1', 'YV-description-full-v0-canonical-router', 'Float64Array', 'boundedLevenshtein'):
    if token not in engine:
        raise RuntimeError(f'browser search engine contract drift: {token}')

# No CDN, tracker, feedback endpoint or remote font/script asset. Model assets are relative.
external = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)', html, flags=re.I)
if external:
    raise RuntimeError(f'external page assets are forbidden: {external}')
if re.search(r'fetch\(["\']https?://', app, flags=re.I):
    raise RuntimeError('demo app must not call external HTTP endpoints')
for banned in ('google-analytics', 'gtag(', 'segment.', 'sentry.io', 'hotjar', 'mixpanel'):
    if banned.lower() in all_text.lower():
        raise RuntimeError(f'tracker/telemetry token forbidden: {banned}')

print('demo dual-stream static contract: ok')
