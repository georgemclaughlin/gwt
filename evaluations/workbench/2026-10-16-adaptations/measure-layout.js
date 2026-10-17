async page => {
  await page.setViewportSize({width: 390, height: 844});
  const results = [];
  for (const name of ['input_normalization', 'subscription']) {
    await page.goto('http://127.0.0.1:8898/' + name + '/review.html');
    await page.locator('[data-filter="' + (name === 'subscription' ? 'path_changed' : 'incompatible') + '"]').click();
    const panel = page.locator('[data-case-panel]:visible');
    await panel.evaluate(element => element.scrollIntoView({block: 'start', behavior: 'instant'}));
    const measured = await panel.evaluate(element => {
      const top = element.getBoundingClientRect().top;
      const hashes = element.querySelector('.impact-hashes').getBoundingClientRect();
      const predicate = element.querySelector('.condition-fact')?.getBoundingClientRect();
      const error = element.querySelector('.error-card')?.getBoundingClientRect();
      return {viewportHeight: window.innerHeight, panelTop: top, identityHeight: hashes.height,
        firstPredicateOffset: predicate ? predicate.top - top : null,
        firstErrorOffset: error ? error.top - top : null,
        firstErrorVisibleWithoutScrolling: error ? error.top < window.innerHeight && error.bottom > 0 : null};
    });
    results.push({workflow: name, ...measured});
  }
  return results;
}
