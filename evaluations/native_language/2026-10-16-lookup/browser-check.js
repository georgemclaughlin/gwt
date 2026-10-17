async page => {
  const root = 'http://127.0.0.1:8900/';
  const output = '/home/g/code/gwt/evaluations/native_language/2026-10-16-lookup';
  const report = await (await page.request.get(root + 'packaged/review.json')).json();
  const checks = [];
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const check = (condition, name) => { if (!condition) throw new Error(name); checks.push(name); };
  const canonical = value => Array.isArray(value) ? value.map(canonical)
    : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
  const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  await page.goto(root + 'packaged/review.html');
  check(await page.locator('[data-case]').count() === 9, 'all nine captured cases selectable');
  for (const [filter, count] of [['outcome_changed', 3], ['candidate_failed', 1], ['unverified', 0], ['decision_pending', 9]]) {
    await page.locator('[data-filter]').selectOption(filter);
    check(await page.locator('[data-case]:visible').count() === count, 'filter ' + filter);
  }
  await page.locator('[data-filter]').selectOption('all');
  for (let index = 0; index < report.cases.length; index++) {
    const row = report.cases[index];
    await page.locator('[data-case]').nth(index).click();
    const panel = page.locator('[data-case-panel]');
    check(await panel.locator('h2').innerText() === row.id, 'selected ' + row.id);
    for (const [position, execution] of [[0, row.comparison.baseline.actual], [1, row.comparison.candidate]]) {
      const run = panel.locator('.run').nth(position);
      check(same(JSON.parse(await run.locator(':scope > pre').first().innerText()), execution.result), 'exact result ' + row.id + '/' + position);
      check(await run.locator(':scope > .badge').innerText() === (execution.ok ? 'Completed' : 'Execution failed'), 'status ' + row.id + '/' + position);
      if (!execution.ok) check((await run.innerText()).includes(execution.diagnostic.code), 'failure diagnostic ' + row.id + '/' + position);
    }
    check(same(await panel.locator('.table-wrap tbody tr td:first-child code').allTextContents(), row.comparison.outcomeDifferences.map(item => item.path)), 'changed paths ' + row.id);
  }
  await page.locator('[data-search]').fill('no-matching-case');
  check(await page.locator('[data-case-panel]').count() === 0, 'empty search clears selected detail');
  await page.locator('[data-search]').fill('');
  await page.locator('[data-case]').first().click();
  const waiting = page.waitForEvent('download');
  await page.locator('[data-download]').click();
  await (await waiting).saveAs(output + '/downloaded-review.json');
  for (const [name, width, height] of [['desktop', 1440, 1100], ['mobile', 390, 844]]) {
    await page.setViewportSize({width, height});
    await page.locator('[data-case-panel]').evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no horizontal overflow ' + name);
    await page.screenshot({path: output + '/' + name + '.png'});
  }
  check(errors.length === 0, 'no script errors');
  return {checks, count: checks.length, browserVersion: page.context().browser().version(), decisionsSaved: false};
}
