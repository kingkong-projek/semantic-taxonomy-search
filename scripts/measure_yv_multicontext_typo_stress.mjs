#!/usr/bin/env node
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import Fuse from 'fuse.js';

const YV_URL = 'https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json';
const YV_SHA256 = '1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49';
const FUSE_VERSION = '7.5.0';
const MIN_FUZZY_SCORE = 0.4;
const MAX_FUZZY_SCORE = 0.84;
const MAX_WEAK_FUZZY_RESULTS = 3;

function norm(v) {
  return String(v ?? '').normalize('NFC').toLowerCase().trim();
}

function hash(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function display(row) {
  return row.occupation_name_preferred_label
    ? `${row.preferred_label} (${row.occupation_name_preferred_label})`
    : row.preferred_label;
}

function identity(row) {
  return row.type === 'job-title' ? `${row.id}|${row.occupation_name_id ?? ''}` : row.id;
}

function editDistance(a, b) {
  const n = b.length;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const cur = [i, ...new Array(n).fill(0)];
    for (let j = 1; j <= n; j += 1) {
      cur[j] = Math.min(
        cur[j - 1] + 1,
        prev[j] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    prev = cur;
  }
  return prev[n];
}

function fuzzySubstring(text, query) {
  const target = query.length;
  const min = Math.max(3, target - 2);
  const max = Math.min(text.length, target + 2);
  let best = 99;
  for (let start = 0; start <= text.length - min; start += 1) {
    for (let length = min; length <= max && start + length <= text.length; length += 1) {
      best = Math.min(best, editDistance(query, text.slice(start, start + length)));
    }
  }
  return best <= Math.max(2, Math.floor(target * 0.25)) ? best : null;
}

function rootMatch(query, label) {
  const q = norm(query);
  const l = norm(label);
  if (l.includes(' ')) {
    const distance = editDistance(q, l);
    return distance <= Math.max(2, Math.floor(q.length * 0.25)) && Math.abs(q.length - l.length) <= 2;
  }
  return fuzzySubstring(l, q) !== null;
}

function sortRows(rows) {
  return rows.sort((a, b) =>
    b.score - a.score
    || Number(b.weight ?? 0) - Number(a.weight ?? 0)
    || display(a).localeCompare(display(b), 'sv')
  );
}

class CurrentYv {
  constructor(items) {
    this.items = items;
    this.fuse = new Fuse(items, {
      keys: ['preferred_label'],
      includeScore: true,
      ignoreDiacritics: true,
      ignoreFieldNorm: true,
      threshold: 0.6,
      minMatchCharLength: 1,
      ignoreLocation: true,
      distance: 100,
    });
  }

  search(query, max = 10) {
    const q = norm(query);
    if (!q) return [];

    const direct = [];
    const tokens = q.split(' ').filter(Boolean);
    for (const item of this.items) {
      const label = norm(item.preferred_label);
      let score = null;
      if (label === q) score = 1;
      else if (tokens.length > 1 && tokens.every((token) => label.includes(token))) score = 0.98;
      else if (label.startsWith(q)) score = 0.99;
      else if (label.includes(q)) score = 0.95;
      if (score !== null) direct.push({ ...item, score });
    }
    if (direct.length) return sortRows(direct).slice(0, max);

    const raw = this.fuse.search(q);
    if (!raw.length) return [];
    const best = raw[0].score ?? 1;
    const candidates = [];
    const seen = new Set();
    let strong = false;

    for (const hit of raw) {
      const id = identity(hit.item);
      if (seen.has(id)) continue;
      const rawScore = hit.score ?? 1;
      const baseScore = 1 - rawScore;
      if (baseScore < MIN_FUZZY_SCORE || rawScore > best + 0.12) continue;
      const root = rootMatch(q, hit.item.preferred_label);
      if (root && rawScore <= 0.25) strong = true;
      let score = baseScore * 0.70 + Number(hit.item.weight ?? 0) * 0.10 + (root ? 0.12 : 0);
      score = Math.min(MAX_FUZZY_SCORE, Math.max(MIN_FUZZY_SCORE, score));
      candidates.push({ ...hit.item, score });
      seen.add(id);
    }

    if (!candidates.length) return [];
    const sorted = sortRows(candidates);
    const limit = strong ? Math.min(5, max) : Math.min(MAX_WEAK_FUZZY_RESULTS, max);
    return sorted.slice(0, limit);
  }
}

function longestWordSpan(label) {
  const matches = [...label.matchAll(/[A-Za-zÅÄÖåäöÉéÜü]+/g)];
  return matches
    .filter((m) => m[0].length >= 5)
    .sort((a, b) => b[0].length - a[0].length || a.index - b.index)[0] ?? null;
}

function makeDeletionTypo(label) {
  const span = longestWordSpan(label);
  if (!span) return null;
  const word = span[0];
  const idx = Math.max(1, Math.min(word.length - 2, Math.floor(word.length / 2)));
  const mutated = word.slice(0, idx) + word.slice(idx + 1);
  return label.slice(0, span.index) + mutated + label.slice(span.index + word.length);
}

function makeTransposeTypo(label) {
  const span = longestWordSpan(label);
  if (!span) return null;
  const chars = [...span[0]];
  let idx = Math.max(1, Math.min(chars.length - 2, Math.floor(chars.length / 2) - 1));
  if (chars[idx] === chars[idx + 1] && idx + 2 < chars.length) idx += 1;
  if (chars[idx] === chars[idx + 1]) return null;
  [chars[idx], chars[idx + 1]] = [chars[idx + 1], chars[idx]];
  const mutated = chars.join('');
  return label.slice(0, span.index) + mutated + label.slice(span.index + span[0].length);
}

function summarize(cases) {
  const n = cases.length;
  const sum = (key) => cases.reduce((acc, row) => acc + Number(row[key] ?? 0), 0);
  return {
    cases: n,
    no_result: cases.filter((row) => row.result_count === 0).length,
    top1_is_intended: cases.filter((row) => row.top1_is_intended).length,
    any_intended_context_visible: cases.filter((row) => row.intended_visible > 0).length,
    all_intended_contexts_visible: cases.filter((row) => row.intended_visible === row.expected_contexts).length,
    mean_context_recall: n ? Number((sum('context_recall') / n).toFixed(4)) : null,
    median_context_recall: n ? [...cases].sort((a, b) => a.context_recall - b.context_recall)[Math.floor(n / 2)].context_recall : null,
  };
}

async function main() {
  const outputIndex = process.argv.indexOf('--output');
  const output = outputIndex >= 0 ? process.argv[outputIndex + 1] : 'artifacts/yv-multicontext-typo-stress-v31.json';

  const response = await fetch(YV_URL);
  if (!response.ok) throw new Error(`YV HTTP ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  const actualSha = hash(bytes);
  if (actualSha !== YV_SHA256) throw new Error(`YV source drift: ${actualSha}`);
  const doc = JSON.parse(bytes.toString('utf8'));
  const items = doc.data;
  const byJobTitle = new Map();

  for (const row of items) {
    if (row.type !== 'job-title') continue;
    if (!byJobTitle.has(row.id)) byJobTitle.set(row.id, []);
    byJobTitle.get(row.id).push(row);
  }

  const multi = [...byJobTitle.entries()]
    .filter(([, rows]) => new Set(rows.map((row) => row.occupation_name_id)).size > 1)
    .map(([id, rows]) => ({ id, label: rows[0].preferred_label, rows }));

  const engine = new CurrentYv(items);
  const cases = [];
  for (const group of multi) {
    const expected = new Set(group.rows.map(identity));
    for (const [mutation, mutate] of [['delete-middle', makeDeletionTypo], ['transpose-middle', makeTransposeTypo]]) {
      const query = mutate(group.label);
      if (!query || norm(query) === norm(group.label)) continue;
      const results = engine.search(query, 10);
      const visibleIds = new Set(results.map(identity));
      const intendedVisible = [...expected].filter((id) => visibleIds.has(id)).length;
      cases.push({
        job_title_id: group.id,
        preferred_label: group.label,
        mutation,
        query,
        expected_contexts: expected.size,
        result_count: results.length,
        intended_visible: intendedVisible,
        context_recall: Number((intendedVisible / expected.size).toFixed(4)),
        top1_is_intended: results.length > 0 && expected.has(identity(results[0])),
        visible: results.map((row) => ({ display: display(row), id: identity(row), intended: expected.has(identity(row)), score: row.score })),
      });
    }
  }

  const deletion = cases.filter((row) => row.mutation === 'delete-middle');
  const transpose = cases.filter((row) => row.mutation === 'transpose-middle');
  const worst = [...cases]
    .sort((a, b) => a.context_recall - b.context_recall || a.intended_visible - b.intended_visible || b.expected_contexts - a.expected_contexts || a.preferred_label.localeCompare(b.preferred_label, 'sv'))
    .slice(0, 40);

  const result = {
    schema_version: 1,
    taxonomy_version: 31,
    classification: 'structural stress probe only; deterministic synthetic typos are not observed user traffic',
    source: { yv_url: YV_URL, yv_sha256: YV_SHA256, fuse_js_version: FUSE_VERSION },
    population: { multi_context_job_title_ids: multi.length },
    mutation_policy: {
      target: 'longest alphabetic token of length >=5',
      deletion: 'delete one internal character near token midpoint',
      transposition: 'swap one adjacent internal character pair near token midpoint',
    },
    exact_baseline: { all_contexts_visible_top10: 541, cases: 541, pct: 100.0 },
    summaries: { deletion: summarize(deletion), transposition: summarize(transpose), combined: summarize(cases) },
    worst_cases: worst,
    cases,
  };

  await fs.mkdir(output.split('/').slice(0, -1).join('/') || '.', { recursive: true });
  await fs.writeFile(output, JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ population: result.population, summaries: result.summaries, worst_cases: worst.slice(0, 12) }, null, 2));
}

await main();
