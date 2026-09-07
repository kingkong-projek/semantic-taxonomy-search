#!/usr/bin/env node
import fs from 'node:fs';
import { createSearchEngine } from '../demo/search-engine.js';

// yv-c2.json is retained as the stable Pages asset URL; engine metadata is authoritative.
const modelPath = process.argv[2] || 'demo/assets/yv-c2.json';
const parityPath = process.argv[3] || 'artifacts/yv-demo-parity-v1.json';
const model = JSON.parse(fs.readFileSync(modelPath, 'utf8'));
const parity = JSON.parse(fs.readFileSync(parityPath, 'utf8'));
const engine = createSearchEngine(model);
let failures = 0;

for (const row of parity.cases) {
  const actual = engine.search(row.query).results.map((result) => result.id);
  if (JSON.stringify(actual) !== JSON.stringify(row.expected_top5)) {
    failures += 1;
    if (failures <= 10) console.error('YV parity failure', row.id, row.query, actual, row.expected_top5);
  }
}

if (failures) throw new Error(`${failures}/${parity.cases.length} YV browser runtime parity failures`);
if (model.metadata?.target_count !== 2105) throw new Error('YV full-universe target_count drift');
if (model.engine !== 'YV-description-full-v0-canonical-router') throw new Error('YV frozen engine drift');
if (!model.metadata?.job_title_route_surface_count) throw new Error('YV job-title routes missing');
if (!String(model.metadata?.retrieval_contract || '').includes('diagnostic lanes excluded')) {
  throw new Error('YV runtime must exclude unpromoted diagnostic lanes');
}
console.log(JSON.stringify({
  engine: model.engine,
  parity_cases: parity.cases.length,
  parity_failures: 0,
  target_count: model.metadata.target_count,
  job_title_route_surfaces: model.metadata.job_title_route_surface_count,
  runtime_dependencies: model.metadata.runtime_dependencies,
}, null, 2));
