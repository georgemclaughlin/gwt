async page => {
  const root = 'http://127.0.0.1:8897/packaged/';
  const output = '/home/g/code/gwt/evaluations/native_review/2026-10-16-review-identity/browser';
  const checks = [];
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const check = (condition, name) => {
    if (!condition) throw new Error(name);
    checks.push(name);
  };
  await page.setViewportSize({width: 1440, height: 1100});
  await page.goto(root + 'default.html');
  await page.getByText('Captured execution limits', {exact: true}).click();
  const defaults = JSON.parse(await page.locator('[data-captured-limits] pre').innerText());
  check(defaults.execution.steps === 100000 && defaults.callDepth === 64, 'captured limits are rendered');
  await page.getByRole('textbox', {name: 'Reviewer', exact: true}).fill('Synthetic browser identity fixture');
  await page.getByRole('combobox', {name: 'Decision', exact: true}).selectOption('accept');
  await page.getByRole('textbox', {name: 'Review note', exact: true}).fill('Synthetic test only; no project approval.');
  let waiting = page.waitForEvent('download');
  await page.getByRole('button', {name: 'Download decisions', exact: true}).click();
  await (await waiting).saveAs(output + '/default.decisions.json');
  await page.screenshot({path: output + '/default-desktop.png', fullPage: true});
  await page.reload();
  await page.locator('[data-load-decisions]').setInputFiles(output + '/default.decisions.json');
  await page.locator('[data-decision-count]').filter({hasText: '1 accepted'}).waitFor();
  check(await page.getByRole('combobox', {name: 'Decision', exact: true}).inputValue() === 'accept', 'matching saved choices restore');
  waiting = page.waitForEvent('download');
  await page.getByRole('button', {name: 'Download review JSON', exact: true}).click();
  await (await waiting).saveAs(output + '/downloaded-review.json');
  for (const [name, key, expected] of [['steps', 'steps', 99999], ['evidence', 'evidenceBytes', 1048575], ['text', 'textBytes', 1], ['depth', 'callDepth', 63]]) {
    await page.goto(root + name + '.html');
    await page.getByText('Captured execution limits', {exact: true}).click();
    const limits = JSON.parse(await page.locator('[data-captured-limits] pre').innerText());
    check((key === 'callDepth' ? limits[key] : limits.execution[key]) === expected, name + ' limit visible');
    await page.getByRole('textbox', {name: 'Reviewer', exact: true}).fill('Current synthetic reviewer');
    await page.getByRole('combobox', {name: 'Decision', exact: true}).selectOption('needs_information');
    await page.getByRole('textbox', {name: 'Review note', exact: true}).fill('This budget needs fresh review.');
    await page.locator('[data-load-decisions]').setInputFiles(output + '/default.decisions.json');
    await page.getByRole('status').filter({hasText: 'different review'}).waitFor();
    check(await page.getByRole('combobox', {name: 'Decision', exact: true}).inputValue() === 'needs_information', name + ' stale decision refused');
    check(await page.getByRole('textbox', {name: 'Review note', exact: true}).inputValue() === 'This budget needs fresh review.', name + ' current note retained');
    check(await page.getByRole('textbox', {name: 'Reviewer', exact: true}).inputValue() === 'Current synthetic reviewer', name + ' current reviewer retained');
    if (name === 'steps') {
      await page.screenshot({path: output + '/stale-desktop.png', fullPage: true});
      await page.setViewportSize({width: 390, height: 844});
      check(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'mobile page has no horizontal overflow');
      await page.screenshot({path: output + '/stale-mobile.png', fullPage: true});
      await page.setViewportSize({width: 1440, height: 1100});
    }
  }
  check(errors.length === 0, 'no browser script errors');
  return {checks, count: checks.length, browserVersion: page.context().browser().version(), screenshots: ['default-desktop.png', 'stale-desktop.png', 'stale-mobile.png'], errors};
}
