async page => {
  const root = 'http://127.0.0.1:8899/';
  const output = '/home/g/code/gwt/evaluations/workbench/2026-10-16-readability';
  const results = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: width === 390 ? 844 : 1100});
    for (const name of ['input_normalization', 'subscription']) {
      await page.goto(root + name + '/review.html');
      await page.locator('[data-filter="' + (name === 'subscription' ? 'path_changed' : 'incompatible') + '"]').click();
      const panel = page.locator('[data-case-panel]:visible');
      await panel.evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
      const measured = await panel.evaluate(element => {
        const top = element.getBoundingClientRect().top;
        const predicate = element.querySelector('.condition-fact')?.getBoundingClientRect();
        const error = element.querySelector('.error-card')?.getBoundingClientRect();
        const identity = element.querySelector('.impact-identity');
        return {viewportWidth: window.innerWidth, viewportHeight: window.innerHeight,
          panelTop: top, identityCollapsed: !identity.open,
          firstPredicateOffset: predicate ? predicate.top - top : null,
          firstErrorOffset: error ? error.top - top : null,
          firstErrorFullyVisibleWithoutScrolling: error ? error.top >= 0 && error.bottom <= window.innerHeight : null,
          horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth};
      });
      if (measured.horizontalOverflow || !measured.identityCollapsed) throw new Error('Collapsed layout ' + name);
      if (name === 'input_normalization' && !measured.firstErrorFullyVisibleWithoutScrolling) throw new Error('Rejection not visible ' + width);
      const suffix = width === 390 ? 'mobile' : 'desktop';
      await page.screenshot({path: output + '/' + name + '/selected-' + suffix + '.png'});
      const summary = panel.locator('.impact-identity > summary');
      await summary.focus();
      await page.keyboard.press('Enter');
      await summary.evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
      if (!(await panel.locator('.impact-hashes').isVisible())) throw new Error('Missing expanded identities');
      if (!(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))) throw new Error('Expanded overflow ' + width);
      if (width === 390) await page.screenshot({path: output + '/' + name + '/identities-mobile.png'});
      results.push({...measured, workflow: name, expandedIdentitiesVisible: true, expandedHorizontalOverflow: false});
    }
  }
  return results;
}
