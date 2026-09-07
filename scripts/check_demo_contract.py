#!/usr/bin/env python3
"""Cheap static contract for the zero-backend semantic fallback demo."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path('demo')
html = (ROOT / 'index.html').read_text(encoding='utf-8')
css = (ROOT / 'styles.css').read_text(encoding='utf-8')
app = (ROOT / 'app.js').read_text(encoding='utf-8')
engine = (ROOT / 'search-engine.js').read_text(encoding='utf-8')
all_text = '\n'.join((html, css, app, engine))

required_html = (
    'id="description"', 'id="search-form"', 'id="results-panel"', 'id="export-button"',
    'id="history"', 'id="main"', 'aria-live="polite"', 'role="radiogroup"',
    'Prototyp för utvärdering', 'Allt stannar i din webbläsare',
)
for token in required_html:
    if token not in html:
        raise RuntimeError(f'missing demo HTML contract: {token}')

for token in (
    'localStorage', 'new Blob', 'URL.createObjectURL',
    "const MODEL_URL = './assets/kv-g1-t3.json'",
    "form.addEventListener('submit'", 'const loaded = await ensureEngine();',
):
    if token not in app:
        raise RuntimeError(f'missing local demo behavior: {token}')

if app.count('fetch(') != 1 or 'fetch(MODEL_URL' not in app:
    raise RuntimeError('demo must make exactly one kind of network request: lazy model fetch')

for token in (
    '@media (max-width: 900px)', '@media (max-width: 640px)', ':focus-visible',
    'prefers-reduced-motion', 'grid-template-columns: minmax(0, 1.72fr)',
):
    if token not in css:
        raise RuntimeError(f'missing responsive/accessibility CSS contract: {token}')

if 'KV-G1+T3-plain-v1' not in engine or 'Float64Array' not in engine:
    raise RuntimeError('browser search engine contract drift')

# No CDN, tracker, feedback endpoint or remote font/script asset. The model itself is relative.
external = re.findall(r'(?:src|href)=["\'](https?://[^"\']+)', html, flags=re.I)
if external:
    raise RuntimeError(f'external page assets are forbidden: {external}')
if re.search(r'fetch\(["\']https?://', app, flags=re.I):
    raise RuntimeError('demo app must not call external HTTP endpoints')
for banned in ('google-analytics', 'gtag(', 'segment.', 'sentry.io', 'hotjar', 'mixpanel'):
    if banned.lower() in all_text.lower():
        raise RuntimeError(f'tracker/telemetry token forbidden: {banned}')

print('demo static contract: ok')
