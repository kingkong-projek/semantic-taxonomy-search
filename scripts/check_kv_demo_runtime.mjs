#!/usr/bin/env node
import fs from 'node:fs';
import { createSearchEngine } from '../demo/search-engine.js';

const modelPath = process.argv[2] || 'demo/assets/kv-g1-t3.json';
const parityPath = process.argv[3] || 'artifacts/kv-demo-parity-v1.json';
const model = JSON.parse(fs.readFileSync(modelPath, 'utf8'));
const parity = JSON.parse(fs.readFileSync(parityPath, 'utf8'));
const engine = createSearchEngine(model);
let failures = 0;

for (const row of parity.cases) {
  const actual = engine.search(row.query).results.map((result) => result.id);
  if (JSON.stringify(actual) !== JSON.stringify(row.expected_top5)) {
    failures += 1;
    if (failures <= 10) console.error('parity failure', row.id, actual, row.expected_top5);
  }
}

if (failures) throw new Error(`${failures}/${parity.cases.length} browser runtime parity failures`);
if (model.metadata?.target_count !== 316) throw new Error('target_count drift');
if (model.engine !== 'KV-G1+T3-plain-v1') throw new Error('engine drift');
console.log(JSON.stringify({
  engine: model.engine,
  parity_cases: parity.cases.length,
  parity_failures: 0,
  target_count: model.metadata.target_count,
  runtime_dependencies: model.metadata.runtime_dependencies,
}, null, 2));
