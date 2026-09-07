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

function fuse(c0, g1, teacher) {
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

export function createSearchEngine(model) {
  if (!model || model.engine !== 'KV-G1+T3-plain-v1' || !Array.isArray(model.document_ids)) {
    throw new Error('Ogiltig eller inkompatibel sökmodell.');
  }
  const ids = model.document_ids;
  const labels = model.labels;
  const idToIndex = new Map(ids.map((id, index) => [id, index]));

  return {
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

      const rankedIds = fuse(rankLane(c0, ids), rankLane(g1, ids), rankLane(teacher, ids)).slice(0, 5);
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
