'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const reportText = byId('validation-data').textContent;
  const sourceText = byId('source-data').textContent;
  const report = JSON.parse(reportText), source = JSON.parse(sourceText), metadata = JSON.parse(byId('metadata-data').textContent);
  const node = (tag, text, className) => { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; if (className) item.className = className; return item; };
  const statusNames = { passed: 'Passed', failed: 'Failed', skipped: 'Skipped', notExercised: 'Not exercised', notObserved: 'No recorded outcome' };
  const statusClass = value => value === 'passed' ? 'good' : value === 'failed' ? 'bad' : value === 'skipped' ? 'quiet' : 'gap';
  const badge = value => node('span', statusNames[value] || value, `badge ${statusClass(value)}`);
  const bytes = new Map(), encoder = new TextEncoder(), decoder = new TextDecoder('utf-8', { fatal: true });
  const moduleBytes = file => { if (!source || !Object.hasOwn(source.modules, file)) return null; if (!bytes.has(file)) bytes.set(file, encoder.encode(source.modules[file])); return bytes.get(file); };
  const excerpt = span => { const text = moduleBytes(span.file); if (!text || !Number.isSafeInteger(span.start) || !Number.isSafeInteger(span.end) || span.start < 0 || span.end < span.start || span.end > text.length) return null; try { return decoder.decode(text.slice(span.start, span.end)); } catch (_) { return null; } };
  const location = span => `${span.file}:${span.line}:${span.column}`;
  let selectedSource = null;
  function showSource(span, full = false) {
    const text = moduleBytes(span.file); if (!text || excerpt(span) === null) return;
    selectedSource = span;
    const before = decoder.decode(text.slice(0, span.start));
    const selection = decoder.decode(text.slice(span.start, span.end));
    const after = decoder.decode(text.slice(span.end));
    const linesBefore = before.split('\n'), linesAfter = after.split('\n');
    const prefix = full ? before : linesBefore.slice(-4).join('\n');
    const suffix = full ? after : linesAfter.slice(0, 4).join('\n');
    const startLine = full ? 1 : Math.max(1, linesBefore.length - 3);
    byId('source-location').textContent = location(span);
    byId('source-range').textContent = full ? 'Full captured module. Highlight marks the selected source span.' : `Captured context starts at line ${startLine}. Highlight marks the selected source span.`;
    byId('source-code').replaceChildren(document.createTextNode(prefix), node('mark', selection || '⟵ source boundary'), document.createTextNode(suffix));
    byId('full-source').hidden = full;
    if (!byId('source-dialog').open) byId('source-dialog').showModal();
  }
  function sourceButton(span, label) {
    const button = node('button', label || location(span), 'source-link');
    button.setAttribute('aria-label', `View captured source at ${location(span)}`);
    if (excerpt(span) === null) { button.disabled = true; button.title = 'Source was not captured for this location'; }
    else button.addEventListener('click', () => showSource(span));
    return button;
  }
  function diagnostic(error) {
    const box = node('div', undefined, 'diagnostic');
    box.append(node('p', `${error.code}: ${error.message}`), sourceButton(error.span)); return box;
  }
  function download(name, text) {
    const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    const link = node('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  byId('download-report').addEventListener('click', () => download('gwt-validation.json', reportText));
  byId('download-source').disabled = !source;
  byId('download-source').addEventListener('click', () => { if (source) download('gwt-source-bundle.json', sourceText); });
  byId('close-source').addEventListener('click', () => byId('source-dialog').close());
  byId('full-source').addEventListener('click', () => showSource(selectedSource, true));
  byId('entry').textContent = source?.entry || report.programIdentity?.entry || 'Source closure unavailable';
  const gaps = report.warnings.length > 0;
  byId('outcome').textContent = report.ok ? (gaps ? 'Required checks passed · Evidence gaps remain' : report.scenarios.status === 'notExercised' ? 'Static and formatting checks passed · No scenarios exercised' : 'Required checks passed') : 'Validation did not pass';
  byId('outcome').className = report.ok ? (gaps || report.scenarios.status === 'notExercised' ? 'gap' : 'good') : 'bad';
  for (const [key, title] of [['load', 'Capture source'], ['check', 'Check program'], ['format', 'Check formatting'], ['scenarios', 'Run scenarios']]) {
    const phase = report[key], box = node('div', undefined, 'gate');
    box.append(node('h2', title), badge(phase.status));
    if (phase.reason) box.append(node('p', phase.reason, 'reason'));
    if (phase.diagnostic) box.append(diagnostic(phase.diagnostic));
    byId('gates').append(box);
  }
  byId('gaps').hidden = !gaps;
  for (const warning of report.warnings) byId('warnings').append(node('li', warning.message));
  const totals = report.evidence?.scenarioExpectations;
  byId('scenario-totals').textContent = totals ? `${totals.passed} passed · ${totals.failed} failed · ${totals.notObserved} without recorded outcome` : 'Execution evidence unavailable';
  const scenarioHasGap = item => item.expectations.length === 0 || item.expectations.some(expectation => expectation.outcome === 'notObserved');
  let selected = null;
  function showScenario(index) {
    selected = index;
    for (const item of byId('scenario-list').children) item.setAttribute('aria-pressed', String(Number(item.dataset.index) === index));
    const result = report.results[index], panel = byId('scenario-detail'); panel.replaceChildren();
    panel.append(node('h2', result.name), badge(result.ok ? 'passed' : 'failed'), node('p', `${result.steps} execution steps · ${result.expectations.length} declared expectations`, 'muted'));
    if (result.diagnostic) panel.append(diagnostic(result.diagnostic));
    if (!result.expectations.length) panel.append(node('p', 'No scenario or background THEN expectations were declared. A successful action alone does not establish a scenario-specific expected outcome.', 'notice'));
    for (const expectation of result.expectations) {
      const box = node('div', undefined, 'expectation'), heading = node('div', undefined, 'expectation-heading');
      heading.append(node('strong', ({ condition: 'Condition', printedOutput: 'Printed output', failure: 'Expected failure' })[expectation.kind]), badge(expectation.outcome)); box.append(heading);
      const text = excerpt(expectation.span);
      if (text !== null) { const characters = Array.from(text); box.append(node('p', characters.slice(0, 180).join('') + (characters.length > 180 ? '…' : ''), 'preview')); }
      box.append(sourceButton(expectation.span));
      if (expectation.event !== null) box.append(node('p', `Recorded event #${expectation.event} in this scenario. Full execution trace is available through run/test.`, 'muted'));
      else box.append(node('p', 'No result was recorded. Execution may have stopped before or during this expectation.', 'muted'));
      panel.append(box);
    }
  }
  function filterScenarios() {
    const query = byId('search').value.toLocaleLowerCase(), filter = byId('filter').value;
    const visible = report.results.map((item, index) => ({ item, index })).filter(({ item }) => item.name.toLocaleLowerCase().includes(query) && (filter === 'all' || (filter === 'failed' ? !item.ok : scenarioHasGap(item))));
    byId('scenario-list').replaceChildren();
    for (const { item, index } of visible) {
      const button = node('button', undefined, 'scenario-choice'); button.dataset.index = index;
      button.append(node('strong', item.name), badge(item.ok ? 'passed' : 'failed'));
      if (scenarioHasGap(item)) button.append(node('span', ' · Evidence gap', 'muted'));
      button.addEventListener('click', () => showScenario(index)); byId('scenario-list').append(button);
    }
    byId('visible-count').textContent = `${visible.length} of ${report.results.length} scenarios shown`;
    if (visible.length) showScenario(visible.some(item => item.index === selected) ? selected : visible[0].index);
    else { selected = null; byId('scenario-detail').replaceChildren(node('p', report.results.length ? 'No scenarios match these filters.' : report.scenarios.status === 'notExercised' ? 'This entry has no executable scenarios.' : 'No scenarios were executed. See the validation gates above.', 'empty')); }
  }
  byId('search').addEventListener('input', filterScenarios); byId('filter').addEventListener('change', filterScenarios); filterScenarios();
  let callLimit = 100;
  function showCalls() {
    const calls = (report.evidence?.callables || []).filter(item => byId('calls-filter').value === 'all' || item.recordedEntries === 0);
    byId('calls').replaceChildren();
    for (const item of calls.slice(0, callLimit)) {
      const row = node('tr'), name = node('td'); name.append(node('strong', item.name), node('div', item.kind, 'muted'));
      const entries = node('td', String(item.recordedEntries)), scenarios = node('td', String(item.scenariosWithEntries)), link = node('td');
      entries.dataset.label = 'Recorded entries'; scenarios.dataset.label = 'Scenario runs'; link.dataset.label = 'Source';
      link.append(sourceButton(item.definition));
      row.append(name, entries, scenarios, link); byId('calls').append(row);
    }
    byId('call-count').textContent = report.evidence ? `${Math.min(callLimit, calls.length)} of ${calls.length} matching declarations shown` : 'Declaration observations are unavailable because checking did not pass.';
    byId('more-calls').hidden = callLimit >= calls.length;
  }
  byId('calls-filter').addEventListener('change', () => { callLimit = 100; showCalls(); });
  byId('more-calls').addEventListener('click', () => { callLimit += 100; showCalls(); }); showCalls();
  for (const item of report.modules) {
    const row = node('li', `${item.file} — ${item.changed === false ? 'Formatting passed' : item.changed === true ? 'Needs formatting' : 'Could not format'}`);
    if (item.diagnostic) row.append(diagnostic(item.diagnostic)); byId('formats').append(row);
  }
  if (!report.modules.length) byId('formats').append(node('li', 'Formatting was not checked.'));
  byId('capture-note').textContent = source ? 'These are the captured source texts used for validation. Later file edits are not reflected here. Capturing several files is not an atomic filesystem snapshot.' : 'A complete source snapshot was not retained because loading or source bounds prevented capture. Locations without captured source cannot be opened.';
  for (const file of Object.keys(source?.modules || {})) {
    const row = node('li'), button = sourceButton({ file, start: 0, end: 0, line: 1, column: 1 }, file); row.append(button); byId('source-files').append(row);
  }
  byId('identity').textContent = report.programIdentity ? JSON.stringify(report.programIdentity, null, 2) : 'No compiled program identity: static checking did not pass.';
  byId('engine').textContent = JSON.stringify(metadata.engine, null, 2);
  byId('limits').textContent = metadata.limitsText;
  byId('policy').textContent = report.allowNoScenarios ? 'A declaration-only entry was explicitly allowed. No scenarios still means not exercised.' : 'Validation requires at least one executable scenario.';
})();
