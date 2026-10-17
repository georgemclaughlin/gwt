async page => {
  const root = 'http://127.0.0.1:8899/';
  const output = '/home/g/code/gwt/evaluations/workbench/2026-10-16-readability';
  const specs = await (await page.request.get(root + 'manifest.json')).json();
  const checks = [];
  const errors = [];
  const requests = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('request', request => requests.push(request.url()));
  const check = (condition, name) => {
    if (!condition) throw new Error(name);
    checks.push(name);
  };
  const canonical = value => Array.isArray(value) ? value.map(canonical)
    : value !== null && typeof value === 'object'
      ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
      : value;
  const same = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
  for (const spec of specs) {
    const name = spec.workflow;
    await page.setViewportSize({width: 1440, height: 1100});
    await page.goto(root + name + '/review.html');
    {
      const comparison = page.locator('[data-comparison]');
      const mapping = {unavailable: 'unavailable', output_changed: 'outputChanged', path_changed: 'pathChanged', new_failure: 'newFailure', resolved_failure: 'resolvedFailure', failure_changed: 'failureChanged', incompatible: 'incompatible', baseline_mismatch: 'baselineMismatch', unchanged: 'unchanged'};
      for (const [classification, key] of Object.entries(mapping)) {
        check(Number(await comparison.locator('[data-classification-total="' + classification + '"] strong').innerText()) === spec.totals[key], name + ' total ' + classification);
      }
      const changed = spec.rows.filter(row => row.classification !== 'unchanged');
      check(await comparison.locator('[data-case-choice]').count() === changed.length, name + ' queue coverage');
      if (!changed.length) {
        check(await comparison.getByText('No changed cases', {exact: true}).isVisible(), name + ' unchanged summary visible');
        check(await comparison.locator('[data-case-panel]').count() === 0, name + ' no false changed details');
      } else {
        if (name === 'subscription') {
          check(await comparison.locator('[data-path-placeholder]').isVisible(), name + ' path-only changes start collapsed');
          check(await comparison.locator('[data-case-panel]:visible').count() === 0, name + ' no implicit path selection');
        }
        for (const classification of [...new Set(changed.map(row => row.classification))]) {
          await comparison.locator('[data-filter="' + classification + '"]').click();
          check(await comparison.locator('[data-case-choice]:visible').count() === changed.filter(row => row.classification === classification).length, name + ' filter ' + classification);
        }
        await comparison.locator('[data-filter="all"]').click();
        const queue = comparison.locator('[data-path-queue]');
        if (await queue.count() && !(await queue.getAttribute('open') === '')) await queue.locator(':scope > summary').click();
        for (const row of changed) {
          const choice = comparison.locator('[data-case-choice]').filter({has: page.locator('.impact-case__id', {hasText: row.id})});
          await choice.click();
          const panel = comparison.locator('[data-case-panel]:visible');
          check(await panel.count() === 1 && (await panel.locator(':scope > header > code').innerText()) === row.id, name + ' selected ' + row.id);
          const identity = panel.locator('.impact-identity');
          check(await identity.count() === 1 && await identity.getAttribute('open') === null, name + ' identities initially collapsed ' + row.id);
          const codes = identity.locator('.impact-hashes code');
          const expectedHashes = [row.recordedProgramHash, row.capturedEvidenceDigest, row.executionCaseId, row.oldEvidenceDigest, row.newEvidenceDigest].filter(Boolean);
          check(same(await codes.allTextContents(), expectedHashes), name + ' all capture identities retained ' + row.id);
          check(!(await codes.first().isVisible()), name + ' collapsed hashes hidden ' + row.id);
          const summary = identity.locator('summary');
          await summary.focus();
          await page.keyboard.press('Enter');
          check(await codes.first().isVisible(), name + ' Enter reveals provenance ' + row.id);
          check(await summary.evaluate(element => getComputedStyle(element).outlineStyle !== 'none'), name + ' keyboard focus visible ' + row.id);
          await page.keyboard.press('Space');
          check(!(await codes.first().isVisible()), name + ' Space collapses provenance ' + row.id);
          check(await panel.evaluate(element => {
            const firstEvidence = element.querySelector('.impact-block');
            return [...element.querySelectorAll('.error-card')].every(error => Boolean(error.compareDocumentPosition(firstEvidence) & Node.DOCUMENT_POSITION_FOLLOWING));
          }), name + ' errors precede supporting evidence ' + row.id);
          const actualErrors = await panel.locator('.error-card > code').allTextContents();
          check(same(actualErrors, [row.oldError, row.newError].filter(Boolean).map(error => error.message)), name + ' exact errors ' + row.id);
          const actualConditions = await panel.locator('.condition-fact').evaluateAll(elements => elements.map(element => ({
            expression: element.querySelector(':scope > code').textContent,
            result: element.querySelector('.truth-chip').textContent,
            source: element.querySelector('.source-link')?.textContent || null
          })));
          const expectedConditions = [...row.oldEvaluatedConditions, ...row.newEvaluatedConditions].map(condition => ({
            expression: condition.expression, result: String(condition.result),
            source: condition.source ? condition.source.file + ':' + condition.source.line + ':' + condition.source.column : null
          }));
          check(same(actualConditions, expectedConditions), name + ' source-backed predicates ' + row.id);
        }
        await comparison.locator('[data-case-search]').fill('no-such-case-zzzz');
        check(await comparison.locator('[data-no-matches]').isVisible() && await comparison.locator('[data-case-panel]:visible').count() === 0, name + ' empty search clears stale detail');
        await comparison.locator('[data-case-search]').fill(changed[0].id);
        check(await comparison.locator('[data-case-choice]:visible').count() === 1, name + ' search finds case');
        await comparison.locator('[data-case-choice]:visible').click();
        await comparison.locator('[data-case-search]').fill('');
      }
      await comparison.evaluate(element => element.scrollIntoView({block: 'start'}));
    }
    const focus = spec.kind === 'native' ? page.locator('[data-case-panel] .table-wrap').first()
      : spec.rows.some(row => row.classification !== 'unchanged') ? page.locator('[data-comparison] [data-case-panel]:visible')
      : page.locator('[data-comparison] .empty-state');
    await focus.evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
    check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), name + ' desktop has no horizontal overflow');
    await page.screenshot({path: output + '/' + name + '/desktop.png'});
    await page.setViewportSize({width: 390, height: 844});
    await focus.evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
    check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), name + ' mobile has no horizontal overflow');
    await page.screenshot({path: output + '/' + name + '/mobile.png'});
  }
  check(errors.length === 0, 'no browser script errors');
  check(requests.every(url => url.startsWith(root)), 'pages made no external requests');
  return {count: checks.length, checks, errors, workflows: specs.length, recordedCases: specs.reduce((sum, spec) => sum + spec.rows.length, 0), browserVersion: page.context().browser().version(), historicalArtifacts: true};
}
