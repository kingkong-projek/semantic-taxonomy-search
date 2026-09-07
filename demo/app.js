import { createSearchEngine } from './search-engine.js';

const STORAGE_KEY = 'semantic-fallback-demo:skill:v1';
const MODEL_URL = './assets/kv-g1-t3.json';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const form = $('#search-form');
const description = $('#description');
const descriptionError = $('#description-error');
const charCount = $('#char-count');
const searchButton = $('#search-button');
const engineStatus = $('#engine-status');
const resultsPanel = $('#results-panel');
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

let engine = null;
let enginePromise = null;
let currentTestId = null;

function uid() {
  return globalThis.crypto?.randomUUID?.() || `t-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function freshState() {
  return { schema_version: 1, session_id: uid(), created_at: new Date().toISOString(), stream: 'skill', tests: [] };
}

function loadState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (parsed?.schema_version === 1 && Array.isArray(parsed.tests)) return parsed;
  } catch (_) {}
  return freshState();
}

let state = loadState();

function saveState() {
  state.updated_at = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  renderSession();
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
  [...state.tests].reverse().slice(0, 12).forEach((test) => {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `
      <div class="history-item__top">
        <span class="history-item__query"></span>
        <span class="history-item__state" data-reviewed="${Boolean(test.feedback)}" aria-label="${test.feedback ? 'Bedömt' : 'Inte bedömt'}"></span>
      </div>
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

async function ensureEngine() {
  if (engine) return { engine, assetLoadMs: 0 };
  if (!enginePromise) {
    engineStatus.dataset.state = 'loading';
    engineStatus.textContent = 'Laddar sökdata första gången …';
    const started = performance.now();
    enginePromise = fetch(MODEL_URL, { cache: 'force-cache' })
      .then((response) => {
        if (!response.ok) throw new Error(`Kunde inte ladda sökdata (${response.status}).`);
        return response.json();
      })
      .then((model) => {
        engine = createSearchEngine(model);
        const assetLoadMs = performance.now() - started;
        buildVersion.textContent = model.metadata?.build_id || model.engine;
        engineStatus.dataset.state = 'ready';
        engineStatus.textContent = 'Sökningen körs lokalt i webbläsaren.';
        return { engine, assetLoadMs };
      })
      .catch((error) => {
        enginePromise = null;
        engineStatus.dataset.state = 'error';
        engineStatus.textContent = 'Sökdata kunde inte laddas.';
        throw error;
      });
  }
  return enginePromise;
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
  resultsList.replaceChildren();
  if (!test.results.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-results';
    empty.textContent = 'Vi hittade inga förslag för den beskrivningen. Markera gärna ”Inget stämmer” och skriv vad du förväntade dig.';
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
  searchTime.textContent = `${test.diagnostics.search_ms.toFixed(1)} ms lokalt`;
  feedbackStatus.textContent = test.feedback ? 'Bedömningen är sparad lokalt.' : '';
  resultsPanel.hidden = false;
  newTestButton.hidden = false;
}

function resetComposer() {
  currentTestId = null;
  form.reset();
  description.removeAttribute('aria-invalid');
  descriptionError.textContent = '';
  charCount.textContent = '0 / 1200';
  resultsPanel.hidden = true;
  newTestButton.hidden = true;
  feedbackStatus.textContent = '';
  description.focus();
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = description.value.trim();
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
    const loaded = await ensureEngine();
    const response = loaded.engine.search(query);
    const test = {
      test_id: uid(),
      timestamp: new Date().toISOString(),
      stream: 'skill',
      description: query,
      results: response.results,
      selected_id: null,
      feedback: null,
      comment: '',
      diagnostics: response.diagnostics,
      asset_load_ms: Number(loaded.assetLoadMs.toFixed(3)),
      engine: 'KV-G1+T3-plain-v1',
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

newTestButton.addEventListener('click', resetComposer);

exportButton.addEventListener('click', () => {
  if (!state.tests.length) return;
  const payload = {
    schema_version: 1,
    export_type: 'semantic-fallback-demo-feedback',
    exported_at: new Date().toISOString(),
    session_id: state.session_id,
    stream: 'skill',
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
  resetComposer();
  renderSession();
  showToast('Testomgången är rensad.');
});

renderSession();
