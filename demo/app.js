import { createSearchEngine } from './search-engine.js?v=a593-cachefix-1';

const STORAGE_KEY = 'semantic-fallback-demo:mixed:v2';
const LEGACY_STORAGE_KEY = 'semantic-fallback-demo:skill:v1';
const MODEL_URLS = {
  occupation: './assets/yv-c2.json?v=a593-cachefix-1',
  skill: './assets/kv-g1-t3.json?v=a593-cachefix-1',
};
const STREAM_COPY = {
  occupation: {
    name: 'Yrke',
    heading: 'Beskriv ditt yrke',
    fieldLabel: 'Beskriv vad du gör på jobbet',
    help: 'Beskriv arbetsuppgifter, verktyg eller system, arbetsmiljö och ansvar som känns viktiga. Skriv helst inte yrkestiteln.',
    button: 'Sök yrke',
    resultsHeading: 'Vilket yrke ligger närmast?',
    resultsIntro: 'Välj ett yrke om något stämmer. Det är också helt okej om inget passar.',
    empty: 'Vi hittade inga yrkesförslag för den beskrivningen. Markera gärna ”Inget stämmer” och skriv vad du förväntade dig.',
  },
  skill: {
    name: 'Kompetens',
    heading: 'Beskriv en kompetens',
    fieldLabel: 'Beskriv en konkret kompetens',
    help: 'Beskriv vad du gör, med vilka verktyg eller metoder och vilket resultat du försöker uppnå. Skriv helst inte namnet på kompetensen.',
    button: 'Sök kompetens',
    resultsHeading: 'Vilken kompetens ligger närmast?',
    resultsIntro: 'Välj en kompetens om något stämmer. Det är också helt okej om inget passar.',
    empty: 'Vi hittade inga kompetensförslag för den beskrivningen. Markera gärna ”Inget stämmer” och skriv vad du förväntade dig.',
  },
};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const form = $('#search-form');
const description = $('#description');
const descriptionLabel = $('#description-label');
const descriptionHelp = $('#description-help');
const descriptionError = $('#description-error');
const charCount = $('#char-count');
const searchButton = $('#search-button');
const searchButtonLabel = $('#search-button-label');
const searchHeading = $('#search-heading');
const engineStatus = $('#engine-status');
const resultsPanel = $('#results-panel');
const resultsHeading = $('#results-heading');
const resultsIntro = $('#results-intro');
const resultsList = $('#results-list');
const searchTime = $('#search-time');
const feedbackStatus = $('#feedback-status');
const comment = $('#comment');
const commentCount = $('#comment-count');
const newTestButton = $('#new-test');
const testCount = $('#test-count');
const reviewedCount = $('#reviewed-count');
const history = $('#history');
const buildVersion = $('#build-version');
const exportButton = $('#export-button');
const clearButton = $('#clear-button');
const toast = $('#toast');

const engines = {};
const enginePromises = {};
let currentTestId = null;

function uid() {
  return globalThis.crypto?.randomUUID?.() || `t-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function freshState() {
  return { schema_version: 2, session_id: uid(), created_at: new Date().toISOString(), stream: 'mixed', tests: [] };
}

function loadState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (parsed?.schema_version === 2 && Array.isArray(parsed.tests)) return parsed;
  } catch (_) {}

  try {
    const legacy = JSON.parse(localStorage.getItem(LEGACY_STORAGE_KEY) || 'null');
    if (legacy?.schema_version === 1 && Array.isArray(legacy.tests)) {
      return {
        schema_version: 2,
        session_id: legacy.session_id || uid(),
        created_at: legacy.created_at || new Date().toISOString(),
        updated_at: legacy.updated_at,
        stream: 'mixed',
        migrated_from: LEGACY_STORAGE_KEY,
        tests: legacy.tests.map((test) => ({ ...test, stream: test.stream || 'skill' })),
      };
    }
  } catch (_) {}
  return freshState();
}

let state = loadState();

function saveState() {
  state.updated_at = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  renderSession();
}

if (!localStorage.getItem(STORAGE_KEY) && state.tests.length) saveState();

function activeStream() {
  return $('input[name="stream"]:checked')?.value || 'occupation';
}

function currentTest() {
  return state.tests.find((test) => test.test_id === currentTestId) || null;
}

function feedbackLabel(value) {
  return { correct: 'Rätt', partial: 'Delvis rätt', none: 'Inget stämmer' }[value] || 'Inte bedömt';
}

function renderSession() {
  testCount.textContent = String(state.tests.length);
  reviewedCount.textContent = String(state.tests.filter((test) => Boolean(test.feedback)).length);
  exportButton.disabled = state.tests.length === 0;
  clearButton.disabled = state.tests.length === 0;

  history.replaceChildren();
  [...state.tests].reverse().slice(0, 16).forEach((test) => {
    const item = document.createElement('div');
    item.className = 'history-item';
    const stream = test.stream === 'occupation' ? 'occupation' : 'skill';
    item.innerHTML = `
      <div class="history-item__meta">
        <span class="stream-badge" data-stream="${stream}">${STREAM_COPY[stream].name}</span>
        <span class="history-item__state" data-reviewed="${Boolean(test.feedback)}" aria-label="${test.feedback ? 'Bedömt' : 'Inte bedömt'}"></span>
      </div>
      <div class="history-item__query"></div>
      <small></small>`;
    item.querySelector('.history-item__query').textContent = test.description;
    item.querySelector('small').textContent = feedbackLabel(test.feedback);
    history.append(item);
  });
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 2600);
}

function renderEngineStatus(stream) {
  const loaded = engines[stream];
  if (loaded) {
    const build = loaded.metadata?.build_id || loaded.name;
    buildVersion.textContent = `${STREAM_COPY[stream].name}: ${build}`;
    engineStatus.dataset.state = 'ready';
    engineStatus.textContent = 'Sökningen körs lokalt i webbläsaren.';
  } else {
    buildVersion.textContent = `${STREAM_COPY[stream].name}: laddas vid första sökning`;
    engineStatus.dataset.state = '';
    engineStatus.textContent = '';
  }
}

async function ensureEngine(stream) {
  if (engines[stream]) return { engine: engines[stream], assetLoadMs: 0 };
  if (!enginePromises[stream]) {
    engineStatus.dataset.state = 'loading';
    engineStatus.textContent = `Laddar ${STREAM_COPY[stream].name.toLowerCase()}sdata första gången …`;
    const started = performance.now();
    enginePromises[stream] = fetch(MODEL_URLS[stream], { cache: 'no-cache' })
      .then((response) => {
        if (!response.ok) throw new Error(`Kunde inte ladda sökdata (${response.status}).`);
        return response.json();
      })
      .then((model) => {
        const engine = createSearchEngine(model);
        engines[stream] = engine;
        const assetLoadMs = performance.now() - started;
        renderEngineStatus(stream);
        return { engine, assetLoadMs };
      })
      .catch((error) => {
        enginePromises[stream] = null;
        engineStatus.dataset.state = 'error';
        engineStatus.textContent = 'Sökdata kunde inte laddas.';
        throw error;
      });
  }
  return enginePromises[stream];
}

function setStreamCopy(stream) {
  const copy = STREAM_COPY[stream];
  searchHeading.textContent = copy.heading;
  descriptionLabel.textContent = copy.fieldLabel;
  descriptionHelp.textContent = copy.help;
  searchButtonLabel.textContent = copy.button;
  resultsHeading.textContent = copy.resultsHeading;
  resultsIntro.textContent = copy.resultsIntro;
  resultsList.setAttribute('aria-label', `${copy.name} – sökresultat`);
  renderEngineStatus(stream);
}

function hideCurrentResult({ clearDescription = false } = {}) {
  currentTestId = null;
  description.removeAttribute('aria-invalid');
  descriptionError.textContent = '';
  resultsPanel.hidden = true;
  newTestButton.hidden = true;
  feedbackStatus.textContent = '';
  if (clearDescription) {
    description.value = '';
    charCount.textContent = '0 / 1200';
  }
}

function setSelectedResult(id) {
  const test = currentTest();
  if (!test) return;
  test.selected_id = id;
  $$('.result-card').forEach((card) => card.setAttribute('aria-checked', String(card.dataset.id === id)));
  if (test.feedback === 'none') {
    test.feedback = null;
    $$('.feedback-button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
  }
  saveState();
}

function renderResults(test) {
  const stream = test.stream === 'occupation' ? 'occupation' : 'skill';
  const copy = STREAM_COPY[stream];
  resultsHeading.textContent = copy.resultsHeading;
  resultsIntro.textContent = copy.resultsIntro;
  resultsList.replaceChildren();
  if (!test.results.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-results';
    empty.textContent = copy.empty;
    resultsList.append(empty);
  } else {
    test.results.forEach((result) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'result-card';
      card.dataset.id = result.id;
      card.setAttribute('role', 'radio');
      card.setAttribute('aria-checked', String(test.selected_id === result.id));
      card.innerHTML = `
        <span class="result-rank">${result.rank}</span>
        <span class="result-label"></span>
        <span class="result-radio" aria-hidden="true"></span>`;
      card.querySelector('.result-label').textContent = result.label;
      card.addEventListener('click', () => setSelectedResult(result.id));
      resultsList.append(card);
    });
  }

  $$('.feedback-button').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.feedback === test.feedback));
  });
  comment.value = test.comment || '';
  commentCount.textContent = `${comment.value.length} / 1000`;
  searchTime.textContent = `${Number(test.diagnostics.search_ms).toFixed(1)} ms lokalt`;
  feedbackStatus.textContent = test.feedback ? 'Bedömningen är sparad lokalt.' : '';
  resultsPanel.hidden = false;
  newTestButton.hidden = false;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = description.value.trim();
  const stream = activeStream();
  if (query.length < 8) {
    description.setAttribute('aria-invalid', 'true');
    descriptionError.textContent = 'Skriv lite mer så att det finns något att söka på.';
    description.focus();
    return;
  }
  description.removeAttribute('aria-invalid');
  descriptionError.textContent = '';
  searchButton.disabled = true;

  try {
    const loaded = await ensureEngine(stream);
    const response = loaded.engine.search(query);
    const test = {
      test_id: uid(),
      timestamp: new Date().toISOString(),
      stream,
      description: query,
      results: response.results,
      selected_id: null,
      feedback: null,
      comment: '',
      diagnostics: response.diagnostics,
      asset_load_ms: Number(loaded.assetLoadMs.toFixed(3)),
      engine: loaded.engine.name,
      build_id: loaded.engine.metadata?.build_id || null,
      taxonomy_version: loaded.engine.metadata?.taxonomy_version || 31,
    };
    state.tests.push(test);
    currentTestId = test.test_id;
    saveState();
    renderResults(test);
    resultsPanel.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  } catch (error) {
    descriptionError.textContent = error instanceof Error ? error.message : 'Något gick fel när sökningen skulle starta.';
  } finally {
    searchButton.disabled = false;
  }
});

description.addEventListener('input', () => {
  charCount.textContent = `${description.value.length} / 1200`;
  if (description.value.trim().length >= 8) {
    description.removeAttribute('aria-invalid');
    descriptionError.textContent = '';
  }
});

$$('input[name="stream"]').forEach((input) => {
  input.addEventListener('change', () => {
    const stream = activeStream();
    hideCurrentResult();
    setStreamCopy(stream);
    description.focus();
  });
});

$$('.feedback-button').forEach((button) => {
  button.setAttribute('aria-pressed', 'false');
  button.addEventListener('click', () => {
    const test = currentTest();
    if (!test) return;
    const value = button.dataset.feedback;
    if (value === 'correct' && !test.selected_id) {
      feedbackStatus.textContent = 'Välj först vilket förslag som stämmer.';
      feedbackStatus.style.color = '#da0000';
      resultsList.querySelector('.result-card')?.focus();
      return;
    }
    if (value === 'none') {
      test.selected_id = null;
      $$('.result-card').forEach((card) => card.setAttribute('aria-checked', 'false'));
    }
    test.feedback = value;
    feedbackStatus.style.color = '';
    $$('.feedback-button').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    saveState();
    feedbackStatus.textContent = 'Bedömningen är sparad lokalt.';
  });
});

comment.addEventListener('input', () => {
  commentCount.textContent = `${comment.value.length} / 1000`;
  const test = currentTest();
  if (!test) return;
  test.comment = comment.value;
  saveState();
});

newTestButton.addEventListener('click', () => {
  hideCurrentResult({ clearDescription: true });
  description.focus();
});

exportButton.addEventListener('click', () => {
  if (!state.tests.length) return;
  const payload = {
    schema_version: 2,
    export_type: 'semantic-fallback-demo-feedback',
    exported_at: new Date().toISOString(),
    session_id: state.session_id,
    stream: 'mixed',
    privacy_note: 'File exported explicitly by tester; demo sends no feedback automatically.',
    tests: state.tests,
  };
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
  link.href = url;
  link.download = `semantic-sok-feedback-${stamp}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  showToast('Testfilen har exporterats. Skicka den vidare när du är klar.');
});

clearButton.addEventListener('click', () => {
  if (!state.tests.length) return;
  if (!confirm('Rensa alla sparade tester på den här enheten? Det går inte att ångra.')) return;
  state = freshState();
  localStorage.removeItem(STORAGE_KEY);
  hideCurrentResult({ clearDescription: true });
  renderSession();
  showToast('Testomgången är rensad.');
});

setStreamCopy(activeStream());
renderSession();
