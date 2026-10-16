async (page) => {
  const ensure = (ok, msg) => { if (!ok) throw new Error(msg); };
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('[data-filter]').selectOption('all');
  ensure(await page.locator('[data-case]:visible').count() === 9, 'nine cases');
  await page.locator('[data-filter]').selectOption('outcome_changed');
  ensure(await page.locator('[data-case]:visible').count() === 2, 'two outcome changes');
  await page.locator('[data-case="2"]').click();
  const panel = page.locator('[data-case-panel]');
  const text = await panel.innerText();
  ensure(text.includes('/result/quote/fee') && text.includes('parcel.weight_grams <= 1000') && text.includes('parcel.weight_grams <= 1500'), 'difference and source conditions');
  const event = panel.locator('.event').filter({has:page.locator('summary strong', {hasText:/^set$/})}).first();
  await event.locator(':scope > details > summary').click();
  const link = event.locator('[data-operand]').first();
  const target = await link.getAttribute('href');
  await link.click();
  ensure(await page.locator('[data-all-events]').isChecked(), 'operand expands expression view');
  ensure(await page.locator(target).isVisible(), 'operand target visible');
  await page.locator('[data-all-events]').uncheck();
  await page.locator('[data-filter]').selectOption('candidate_failed');
  ensure(await page.locator('[data-case]:visible').count() === 1, 'one expected failure');
  await page.locator('[data-case="8"]').click();
  ensure((await panel.innerText()).includes('assertion_failed'), 'failure code visible');
  await page.locator('[data-filter]').selectOption('all');
  for (const [index,id] of ['old-limit','new-band','new-limit','above-limit','member','maximum','heavy','heavy-member','invalid-weight'].entries()) {
    await page.locator(`[data-case="${index}"]`).click();
    ensure(await panel.locator('h2').innerText() === id, 'case selection '+id);
  }
  ensure((await page.locator('[data-decision-count]').innerText()).includes('9 pending'), 'all choices pending');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button',{name:'Download decisions',exact:true}).click();
  await (await downloadPromise).saveAs('/tmp/gwt-walkthrough-browser-decisions.json');
  await page.locator('[data-filter]').selectOption('outcome_changed');
  await page.locator('[data-case="2"]').click();
  await page.evaluate(()=>scrollTo(0,0));
  ensure(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth), 'desktop overflow');
  await page.screenshot({path:'/tmp/gwt-walkthrough-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  ensure(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth), 'mobile overflow');
  await page.screenshot({path:'/tmp/gwt-walkthrough-mobile.png'});
  return {cases:9,outcomeChanges:2,preservedFailure:1,operandNavigation:true,allChoicesPending:true,downloadedPendingDecisions:true,desktopWidth:1440,mobileWidth:390,horizontalOverflow:false};
}