const TOKEN_RE = /[0-9A-Za-zÅÄÖåäöÉéÜü]+/g;

export function normalizeText(value) {
  return String(value ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
}

export function tokenize(value) {
  return (String(value ?? '').match(TOKEN_RE) || []).map((token) => token.toLowerCase());
}

function compareCodepoint(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

function rankLane(scores, ids) {
  const rows = [];
  for (let index = 0; index < scores.length; index += 1) {
    if (scores[index] > 0) rows.push([scores[index], ids[index]]);
  }
  rows.sort((a, b) => (b[0] - a[0]) || compareCodepoint(a[1], b[1]));
  return rows.map((row) => row[1]);
}

function fuseKv(c0, g1, teacher) {
  const out = c0.length ? [c0[0]] : [];
  const admit = (source, limit) => {
    let added = 0;
    for (const id of source) {
      if (out.includes(id)) continue;
      out.push(id);
      added += 1;
      if (added >= limit) break;
    }
  };

  admit(g1, 1);
  admit(teacher, 3);

  for (const source of [teacher, g1, c0]) {
    for (const id of source) {
      if (!out.includes(id)) out.push(id);
      if (out.length >= 5) break;
    }
    if (out.length >= 5) break;
  }

  return out;
}

function createKvEngine(model) {
  const ids = model.document_ids;
  const labels = model.labels;
  const idToIndex = new Map(ids.map((id, index) => [id, index]));

  return {
    name: model.engine,
    metadata: model.metadata,
    search(query) {
      const started = performance.now();
      const uniqueTokens = [...new Set(tokenize(query))].sort(compareCodepoint);
      const c0 = new Float64Array(ids.length);
      const g1 = new Float64Array(ids.length);
      const teacher = new Float64Array(ids.length);
      let postingsVisited = 0;
      let matchedTerms = 0;

      for (const token of uniqueTokens) {
        const rows = model.postings[token];
        if (!rows) continue;
        matchedTerms += 1;
        for (const row of rows) {
          const index = row[0];
          c0[index] += row[1];
          g1[index] += row[2];
          teacher[index] += row[3];
          postingsVisited += 1;
        }
      }

      const exactRows = model.exact_surfaces[normalizeText(query)] || [];
      for (const index of exactRows) {
        c0[index] += 1_000_000;
        g1[index] += 1_000_000;
        teacher[index] += 1_000_000;
      }

      const rankedIds = fuseKv(rankLane(c0, ids), rankLane(g1, ids), rankLane(teacher, ids)).slice(0, 5);
      const results = rankedIds.map((id, index) => {
        const modelIndex = idToIndex.get(id);
        return { rank: index + 1, id, label: labels[modelIndex] || id };
      });

      return {
        results,
        diagnostics: {
          query_tokens_unique: uniqueTokens.length,
          matched_terms: matchedTerms,
          postings_visited: postingsVisited,
          exact_surface_docs: exactRows.length,
          search_ms: Number((performance.now() - started).toFixed(3)),
        },
      };
    },
  };
}

function boundedLevenshtein(a, b, limit) {
  if (Math.abs(a.length - b.length) > limit) return limit + 1;
  if (a === b) return 0;
  let previous = Array.from({ length: b.length + 1 }, (_, index) => index);
  for (let i = 1; i <= a.length; i += 1) {
    const current = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j += 1) {
      const value = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
      current.push(value);
      rowMin = Math.min(rowMin, value);
    }
    if (rowMin > limit) return limit + 1;
    previous = current;
  }
  return previous[previous.length - 1];
}

function fuzzyLimit(token) {
  if (token.length >= 9) return 2;
  if (token.length >= 6) return 1;
  return 0;
}

function yvSurfaceSignal(queryTokens, exactMatch, surfaceTokens) {
  if (exactMatch) return 4;
  const querySet = new Set(queryTokens);
  for (const token of surfaceTokens) {
    if (querySet.has(token)) return 3;
  }

  for (const queryToken of querySet) {
    if (queryToken.length < 6) continue;
    for (const surfaceToken of surfaceTokens) {
      if (surfaceToken.length < 6) continue;
      if (queryToken.includes(surfaceToken) || surfaceToken.includes(queryToken)) return 2;
    }
  }

  for (const queryToken of querySet) {
    const queryLimit = fuzzyLimit(queryToken);
    if (!queryLimit) continue;
    for (const surfaceToken of surfaceTokens) {
      if (surfaceToken.length < 6) continue;
      const effective = Math.min(queryLimit, fuzzyLimit(surfaceToken));
      if (effective && boundedLevenshtein(queryToken, surfaceToken, effective) <= effective) return 1;
    }
  }
  return 0;
}

function createYvEngine(model) {
  const ids = model.document_ids;
  const labelsById = model.label_by_id || {};
  const boosts = [0, 2_500, 5_000, 10_000, 1_000_000];

  return {
    name: model.engine,
    metadata: model.metadata,
    search(query) {
      const started = performance.now();
      const queryTokens = tokenize(query);
      const uniqueTokens = [...new Set(queryTokens)].sort(compareCodepoint);
      const lexicalScores = new Float64Array(ids.length);
      let postingsVisited = 0;
      let matchedTerms = 0;

      for (const token of uniqueTokens) {
        const rows = model.postings[token];
        if (!rows) continue;
        matchedTerms += 1;
        for (const row of rows) {
          lexicalScores[row[0]] += row[1];
          postingsVisited += 1;
        }
      }

      const normalized = normalizeText(query);
      const exactRows = model.exact_surfaces[normalized] || [];
      const exactSet = new Set(exactRows);
      const shortQuery = queryTokens.length <= 3;
      const scored = [];

      for (let index = 0; index < ids.length; index += 1) {
        const lexical = lexicalScores[index];
        let score = lexical;
        if (shortQuery) {
          const signal = yvSurfaceSignal(queryTokens, exactSet.has(index), model.surface_tokens[index] || []);
          if (!signal) continue;
          score += boosts[signal];
        } else {
          if (exactSet.has(index)) score += 1_000_000;
          if (score <= 0) continue;
        }
        scored.push([score, ids[index]]);
      }
      scored.sort((a, b) => (b[0] - a[0]) || compareCodepoint(a[1], b[1]));
      const c1Ranked = scored.map((row) => row[1]);
      const exactCanonical = c1Ranked.filter((id) => exactSet.has(ids.indexOf(id)));
      const routed = model.job_title_routes[normalized] || [];
      const merged = [];
      for (const id of [...exactCanonical, ...routed, ...c1Ranked]) {
        if (!merged.includes(id)) merged.push(id);
      }
      const rankedIds = merged.slice(0, 5);
      const results = rankedIds.map((id, index) => ({
        rank: index + 1,
        id,
        label: labelsById[id] || id,
      }));

      return {
        results,
        diagnostics: {
          query_tokens: queryTokens.length,
          query_tokens_unique: uniqueTokens.length,
          matched_terms: matchedTerms,
          postings_visited: postingsVisited,
          exact_surface_docs: exactRows.length,
          routed_job_title_parents: routed.length,
          search_ms: Number((performance.now() - started).toFixed(3)),
        },
      };
    },
  };
}

export function createSearchEngine(model) {
  if (!model || model.schema_version !== 1 || !Array.isArray(model.document_ids)) {
    throw new Error('Ogiltig eller inkompatibel sökmodell.');
  }
  if (model.engine === 'KV-G1+T3-plain-v1') return createKvEngine(model);
  if (model.engine === 'YV-C2-plain-v1') return createYvEngine(model);
  throw new Error(`Okänd sökmotor: ${String(model.engine || 'saknas')}`);
}
