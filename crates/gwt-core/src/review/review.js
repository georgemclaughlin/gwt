'use strict';
const choices = Array.from(document.querySelectorAll('[data-case]'));
const panel = document.querySelector('[data-panel]');
const empty = document.querySelector('[data-empty]');
const search = document.querySelector('[data-search]');
const filter = document.querySelector('[data-filter]');
const decisionTemplate = JSON.parse(document.getElementById('decision-data').textContent);
const reviewer = document.querySelector('[data-reviewer]');
const decisionMessage = document.querySelector('[data-decision-message]');
const decisionNames = {pending: 'Pending', accept: 'Accepted', reject: 'Rejected', needs_information: 'Needs information'};
let decisions = new Map(decisionTemplate.decisions.map(item => [item.id, {...item}]));
let selected = null;
function select(choice) {
  selected = choice;
  for (const item of choices) item.setAttribute('aria-pressed', String(item === choice));
  panel.replaceChildren();
  if (choice) {
    panel.append(document.getElementById('case-' + choice.dataset.case).content.cloneNode(true));
    const decision = decisions.get(decisionTemplate.decisions[Number(choice.dataset.case)].id);
    panel.querySelector('[data-decision]').value = decision.status;
    panel.querySelector('[data-decision-note]').value = decision.note;
    const toggle = panel.querySelector('[data-all-events]');
    if (toggle) toggle.addEventListener('change', () => panel.classList.toggle('show-all', toggle.checked));
  }
  panel.classList.remove('show-all');
}
function applyFilters() {
  const query = search.value.toLocaleLowerCase().trim();
  for (const item of choices) {
    const status = item.dataset.status;
    const choiceDecision = decisions.get(decisionTemplate.decisions[Number(item.dataset.case)].id);
    const match = filter.value.startsWith('decision_') ? choiceDecision.status === filter.value.slice(9) : filter.value === 'all' || (filter.value === 'unverified' ? ['unavailable', 'baseline_mismatch'].includes(status) : filter.value === 'outcome_changed' ? item.dataset.changed === 'true' : status === filter.value);
    item.hidden = !match || !item.dataset.searchText.toLocaleLowerCase().includes(query);
  }
  const visible = choices.filter(item => !item.hidden);
  document.querySelector('[data-count]').textContent = `${visible.length} of ${choices.length} cases shown`;
  empty.hidden = visible.length !== 0;
  if (!selected || selected.hidden) select(visible[0] || null);
}
for (const item of choices) item.addEventListener('click', () => select(item));
search.addEventListener('input', applyFilters);
filter.addEventListener('change', applyFilters);
panel.addEventListener('click', event => {
  const link = event.target.closest('[data-operand]');
  if (!link) return;
  event.preventDefault();
  const target = document.getElementById(link.getAttribute('href').slice(1));
  if (!target) return;
  panel.classList.add('show-all');
  const toggle = panel.querySelector('[data-all-events]');
  if (toggle) toggle.checked = true;
  target.querySelector('details').open = true;
  target.scrollIntoView({block: 'center'});
});
document.querySelector('[data-download]').addEventListener('click', () => {
  const blob = new Blob([document.getElementById('review-data').textContent], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = 'gwt-native-review.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

function message(text, isError = false) {
  decisionMessage.textContent = text;
  decisionMessage.classList.toggle('error', isError);
}
function updateDecisionSummary() {
  const counts = {pending: 0, accept: 0, reject: 0, needs_information: 0};
  for (const decision of decisions.values()) counts[decision.status]++;
  document.querySelector('[data-decision-count]').textContent = `${counts.accept} accepted · ${counts.reject} rejected · ${counts.needs_information} need information · ${counts.pending} pending`;
  for (const choice of choices) {
    let badge = choice.querySelector('.decision-label');
    if (!badge) { badge = document.createElement('span'); badge.className = 'decision-label'; choice.append(badge); }
    badge.textContent = decisionNames[decisions.get(decisionTemplate.decisions[Number(choice.dataset.case)].id).status];
  }
}
function documentDecisions() {
  return {...decisionTemplate, reviewer: reviewer.value, decisions: decisionTemplate.decisions.map(item => ({...decisions.get(item.id)}))};
}
const byteLength = text => new TextEncoder().encode(text).length;
const hasContent = text => /[^\p{White_Space}]/u.test(text);
function exactKeys(value, keys) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function validateDecisions(value) {
  if (!exactKeys(value, ['kind', 'schemaVersion', 'reportIdentity', 'reviewer', 'decisions'])
      || value.kind !== decisionTemplate.kind || value.schemaVersion !== 1) throw new Error('Expected native-review-decisions schema version 1.');
  if (!exactKeys(value.reportIdentity, ['algorithm', 'digest'])
      || value.reportIdentity.algorithm !== decisionTemplate.reportIdentity.algorithm
      || value.reportIdentity.digest !== decisionTemplate.reportIdentity.digest) throw new Error('These decisions belong to a different review. Current decisions were kept.');
  if (typeof value.reviewer !== 'string' || byteLength(value.reviewer) > 256 || /[\u0000-\u001f\u007f-\u009f]/u.test(value.reviewer)) throw new Error('Reviewer permits at most 256 UTF-8 bytes and no control characters.');
  if (!Array.isArray(value.decisions) || value.decisions.length !== choices.length) throw new Error('Include every case exactly once.');
  const seen = new Set();
  const expected = new Map(decisionTemplate.decisions.map((item, index) => [item.id, choices[index]]));
  for (const decision of value.decisions) {
    if (!exactKeys(decision, ['id', 'status', 'note']) || typeof decision.id !== 'string'
        || !expected.has(decision.id) || seen.has(decision.id)) throw new Error('Include every case exactly once, without extra fields.');
    seen.add(decision.id);
    if (typeof decision.status !== 'string' || !Object.hasOwn(decisionNames, decision.status) || typeof decision.note !== 'string'
        || byteLength(decision.note) > 4096) throw new Error('Use a supported decision and a note of at most 4096 UTF-8 bytes.');
    if (decision.status !== 'pending' && !hasContent(value.reviewer)) throw new Error('Enter a reviewer before saving a decision.');
    if (['reject', 'needs_information'].includes(decision.status) && !hasContent(decision.note)) throw new Error('Rejection or a request for information requires a note.');
    if (decision.status === 'accept' && ['unavailable', 'baseline_mismatch'].includes(expected.get(decision.id).dataset.status)) throw new Error('Unverified cases cannot be accepted.');
  }
  if (byteLength(JSON.stringify(value)) > 2 * 1048576) throw new Error('Decision file exceeds two MiB.');
}
panel.addEventListener('input', event => {
  if (!selected || !event.target.matches('[data-decision], [data-decision-note]')) return;
  const decision = decisions.get(decisionTemplate.decisions[Number(selected.dataset.case)].id);
  decision.status = panel.querySelector('[data-decision]').value;
  decision.note = panel.querySelector('[data-decision-note]').value;
  updateDecisionSummary();
  message('Unsaved changes. Download decisions to keep them.');
  if (event.target.matches('[data-decision]')) applyFilters();
});
reviewer.addEventListener('input', () => message('Unsaved changes. Download decisions to keep them.'));
document.querySelector('[data-download-decisions]').addEventListener('click', () => {
  try {
    const value = documentDecisions();
    validateDecisions(value);
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + '\n'], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url; link.download = 'gwt-native-review-decisions.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message('Decision download prepared. Keep the file to restore this review later.');
  } catch (error) { message(error.message, true); }
});
// JSON.parse normalizes duplicate keys; reject that ambiguity before accepting a file.
function rejectDuplicateKeys(text) {
  const stack = [];
  for (let index = 0; index < text.length; index++) {
    const ch = text[index];
    if (ch === '"') {
      const start = index++;
      while (index < text.length && text[index] !== '"') {
        if (text[index] === '\\') index++;
        index++;
      }
      const parent = stack[stack.length - 1];
      if (parent && parent.object && parent.key) {
        const key = JSON.parse(text.slice(start, index + 1));
        if (parent.keys.has(key)) throw new Error('Decision file contains a duplicate JSON key.');
        parent.keys.add(key); parent.key = false;
      }
    } else if (ch === '{' || ch === '[') {
      stack.push({object: ch === '{', key: ch === '{', keys: new Set()});
    } else if (ch === '}' || ch === ']') {
      stack.pop();
    } else if (ch === ',' && stack.length && stack[stack.length - 1].object) {
      stack[stack.length - 1].key = true;
    }
  }
}
let decisionLoad = 0;
document.querySelector('[data-load-decisions]').addEventListener('change', async event => {
  const loading = ++decisionLoad;
  try {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 2 * 1048576) throw new Error('Decision file exceeds two MiB.');
    message('Loading decisions…');
    const text = await file.text();
    if (loading !== decisionLoad) return;
    const value = JSON.parse(text);
    rejectDuplicateKeys(text);
    validateDecisions(value);
    decisions = new Map(value.decisions.map(item => [item.id, {...item}]));
    reviewer.value = value.reviewer;
    updateDecisionSummary();
    applyFilters();
    select(selected);
    message('Saved decisions restored for this exact review.');
  } catch (error) { if (loading === decisionLoad) message(error.message, true); }
  finally { if (loading === decisionLoad) event.target.value = ''; }
});
updateDecisionSummary();
applyFilters();
