#!/usr/bin/env node
// Browser-shaped, dependency-free runtime for the compiled C0 student index.
// This intentionally does only tokenization, postings lookup, addition and sorting.

import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';

const args = process.argv.slice(2);
function arg(name, fallback) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
}

const indexDir = arg('--index-dir', 'artifacts/frontend-student-index-v31');
const vectorsPath = arg('--vectors', path.join(indexDir, 'runtime-vectors.json'));
const outputPath = arg('--output', path.join(indexDir, 'js-runtime-benchmark.json'));
const rounds = Number(arg('--rounds', '25'));
if (!Number.isInteger(rounds) || rounds < 1) throw new Error(`invalid rounds ${rounds}`);

const TOKEN_RE = /[0-9A-Za-zÅÄÖåäöÉéÜü]+/g;
function norm(value) {
  return String(value ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
}
function tokens(value) {
  const matches = String(value ?? '').match(TOKEN_RE);
  return matches ? matches.map(x => x.toLowerCase()) : [];
}

function loadJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

const assets = {
  YV: loadJson(path.join(indexDir, 'yv-p80-c0-index.json')),
  KV: loadJson(path.join(indexDir, 'kv-p80-c0-index.json')),
};
const vectors = loadJson(vectorsPath).cases;

function rank(asset, query) {
  const scores = new Map();
  const unique = [...new Set(tokens(query))].sort();
  let postingsVisited = 0;
  let matchedTerms = 0;
  for (const term of unique) {
    const rows = asset.postings[term];
    if (!rows) continue;
    matchedTerms += 1;
    for (const [ordinal, contribution] of rows) {
      scores.set(ordinal, (scores.get(ordinal) ?? 0) + contribution);
      postingsVisited += 1;
    }
  }
  const nq = norm(query);
  const exactRows = nq ? (asset.exact_surfaces[nq] ?? []) : [];
  for (const ordinal of exactRows) {
    scores.set(ordinal, (scores.get(ordinal) ?? 0) + 1_000_000);
  }
  const ranked = [...scores.entries()]
    .filter(([, score]) => score > 0)
    .map(([ordinal, score]) => [score, asset.document_ids[ordinal]])
    .sort((a, b) => (b[0] - a[0]) || a[1].localeCompare(b[1]))
    .map(([, id]) => id);
  return {
    ranked,
    ops: {
      query_tokens_unique: unique.length,
      matched_terms: matchedTerms,
      postings_visited: postingsVisited,
      candidate_docs_scored: scores.size,
      exact_surface_docs: exactRows.length,
    },
  };
}

// Contract/parity pass before timing.
let parityCases = 0;
for (const vector of vectors) {
  const result = rank(assets[vector.product], vector.query);
  const got = result.ranked.slice(0, 10);
  if (JSON.stringify(got) !== JSON.stringify(vector.expected_top10)) {
    throw new Error(`runtime parity failure ${vector.id}: ${JSON.stringify(got)} != ${JSON.stringify(vector.expected_top10)}`);
  }
  for (const [key, expected] of Object.entries(vector.ops)) {
    if (result.ops[key] !== expected) throw new Error(`operation parity failure ${vector.id} ${key}: ${result.ops[key]} != ${expected}`);
  }
  parityCases += 1;
}

// Warmup outside timing.
for (let warm = 0; warm < 3; warm++) {
  for (const vector of vectors) rank(assets[vector.product], vector.query);
}

const roundMs = [];
let checksum = 0;
for (let round = 0; round < rounds; round++) {
  const start = performance.now();
  for (const vector of vectors) {
    const result = rank(assets[vector.product], vector.query);
    checksum += result.ranked.length;
  }
  roundMs.push(performance.now() - start);
}
roundMs.sort((a, b) => a - b);
const queryRuns = rounds * vectors.length;
const elapsedMs = roundMs.reduce((a, b) => a + b, 0);
const percentile = p => roundMs[Math.min(roundMs.length - 1, Math.floor((roundMs.length - 1) * p))];
const result = {
  schema_version: 1,
  engine: 'compiled-c0-bm25-student-js',
  parity_cases: parityCases,
  parity_failures: 0,
  runtime_dependencies: [],
  benchmark: {
    host_role: 'self-hosted garderob diagnostic only; not a low-end-mobile SLA',
    rounds,
    vectors_per_round: vectors.length,
    query_runs: queryRuns,
    total_measured_ms: Number(elapsedMs.toFixed(3)),
    mean_microseconds_per_query: Number((elapsedMs * 1000 / queryRuns).toFixed(3)),
    median_round_ms: Number(percentile(0.5).toFixed(3)),
    p95_round_ms: Number(percentile(0.95).toFixed(3)),
    checksum,
  },
};
fs.writeFileSync(outputPath, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));
