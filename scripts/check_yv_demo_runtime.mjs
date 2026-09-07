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

const canonicalIds = new Set(model.document_ids);
const routeEntries = Object.entries(model.job_title_routes || {});
if (routeEntries.length !== model.metadata.job_title_route_surface_count) {
  throw new Error('YV route population metadata drift');
}
if (parity.full_route_structure_checked !== true || parity.route_population_count !== routeEntries.length) {
  throw new Error('YV parity packet must attest the exhaustive route-table structure check');
}
if (!Number.isInteger(parity.route_rank_parity_sample_count) || parity.route_rank_parity_sample_count < 100) {
  throw new Error('YV route ranking parity sample unexpectedly small');
}
for (const [surface, parentIds] of routeEntries) {
  if (!surface || !Array.isArray(parentIds) || parentIds.length === 0) {
    throw new Error(`YV invalid route row: ${surface}`);
  }
  if (new Set(parentIds).size !== parentIds.length) {
    throw new Error(`YV duplicate parent in route: ${surface}`);
  }
  for (const id of parentIds) {
    if (!canonicalIds.has(id)) throw new Error(`YV route parent outside canonical universe: ${surface} -> ${id}`);
  }
}

console.log(JSON.stringify({
  engine: model.engine,
  parity_cases: parity.cases.length,
  parity_failures: 0,
  target_count: model.metadata.target_count,
  job_title_route_surfaces: routeEntries.length,
  route_rank_parity_sample: parity.route_rank_parity_sample_count,
  route_structure_failures: 0,
  runtime_dependencies: model.metadata.runtime_dependencies,
}, null, 2));
