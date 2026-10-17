async page => {
  const root = 'http://127.0.0.1:8901/';
  const output = '/home/g/code/gwt/evaluations/human_review/2026-10-16-recovery-browser';
  const checks = [], errors = [], requests = [], timing = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('request', request => requests.push(request.url()));
  const check = (ok, name) => { if (!ok) throw new Error(name); checks.push(name); };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const download = async (label, name) => {
    const pending = page.waitForEvent('download');
    await page.locator('#download').click();
    await (await pending).saveAs(output + '/' + label + '/' + name + '.json');
    return (await page.request.get(root + label + '/' + name + '.json')).json();
  };
  const hidden = async value => page.evaluate(value => {
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => value});
    document.dispatchEvent(new Event('visibilitychange'));
  }, value);
  const answer = async key => {
    for (const [name, value] of Object.entries(key.predictions)) await page.locator('input[name="' + name + '"][value="' + value + '"]').check();
    await page.locator('[name=recommendation]').selectOption(key.recommendation);
    await page.locator('[name=confidence]').selectOption('4');
    await page.locator('[name=rationale]').fill('Synthetic browser rehearsal; answer key supplied to automation.');
  };
  for (const [label, width] of [['desktop', 1440], ['mobile', 390]]) {
    await page.setViewportSize({width, height: 1000});
    const key = await (await page.request.get(root + label + '/facilitator-key.json')).json();
    await page.goto(root + label + '/session.html');
    check(await page.locator('#recovery').isVisible(), label + ' recovery offered');
    await page.locator('#checkpoint').focus();
    check(await page.locator('#checkpoint').evaluate(element => document.activeElement === element), label + ' file control keyboard focus');
    const invalid = ['malformed', 'incomplete', 'oversized'].map(name => [name, output + '/invalid/' + name + '.json']);
    if (label === 'mobile') {
      invalid.push(['different-packet', output + '/desktop/checkpoint.json']);
    }
    for (const [name, path] of invalid) {
      await page.locator('#checkpoint').setInputFiles(path);
      await page.waitForFunction(() => document.querySelector('#recovery-error').textContent.length > 0);
      check(await page.locator('#setup').isVisible() && !(await page.locator('#session-controls').isVisible()), label + ' rejects ' + name + ' without starting');
      check(await page.locator('#checkpoint').inputValue() === '', label + ' resets file selection after ' + name);
    }
    await page.getByRole('button', {name: 'Begin review', exact: true}).click();
    check(await page.locator('#setup').isVisible(), label + ' profile required after rejected imports');
    for (const [name, value] of Object.entries({role:'developer',priorExposure:'yes',gwtFamiliarity:'3',pythonFamiliarity:'3'})) await page.locator('[name=' + name + ']').selectOption(value);
    await page.getByRole('button', {name: 'Begin review', exact: true}).click();
    check(await page.locator('#proposed').textContent() === key.packet.tasks[0].sources.proposed, label + ' first source exact');
    await answer(key.answers[0]);
    await page.getByRole('button', {name: 'Save and continue', exact: true}).click();
    await page.locator('#skip').click();
    check(await page.locator('#progress').innerText() === 'Task 3 of 4', label + ' submission and skip advance once');
    const firstPrediction = Object.entries(key.answers[2].predictions)[0];
    await page.locator('input[name="' + firstPrediction[0] + '"][value="' + firstPrediction[1] + '"]').check();
    const draft = 'Partial explanation <script>window.recoveryInjected = true</script> 🍂';
    await page.locator('[name=rationale]').fill(draft);
    await page.locator('[name=recommendation]').selectOption('unsure');
    await page.locator('[name=confidence]').selectOption('2');
    await page.locator('#pause').click();
    const checkpoint = await download(label, 'checkpoint');
    check(same(checkpoint.tasks.map(row => row.status), ['submitted','skipped','draft','unseen']), label + ' partial statuses complete');
    check(checkpoint.tasks[2].rationale === draft && checkpoint.tasks[2].resumeCount === 0, label + ' partial text and original recovery count');
    await page.waitForTimeout(350);
    await page.reload();
    await page.locator('#checkpoint').setInputFiles(output + '/' + label + '/checkpoint.json');
    await page.locator('#paused').waitFor({state:'visible'});
    check(!(await page.locator('#task-panel').isVisible()) && await page.locator('#pause').innerText() === 'Resume', label + ' restored task paused and hidden');
    check(await page.locator('#pause').evaluate(element => document.activeElement === element), label + ' recovery focuses Resume');
    const paused = await download(label, 'restored-paused');
    check(paused.responseId === checkpoint.responseId && same(paused.profile, checkpoint.profile), label + ' identity and profile retained');
    check(same(paused.tasks.slice(0,2), checkpoint.tasks.slice(0,2)), label + ' submitted and skipped records frozen');
    check(same(paused.tasks[3], checkpoint.tasks[3]), label + ' unseen task stays unseen');
    check(paused.tasks[2].resumeCount === 1 && paused.tasks[2].activeMs === checkpoint.tasks[2].activeMs, label + ' restore increments count without active time');
    await page.waitForTimeout(200);
    const later = await download(label, 'paused-later');
    check(later.tasks[2].activeMs === paused.tasks[2].activeMs && later.tasks[2].wallMs >= paused.tasks[2].wallMs + 150, label + ' paused active time fixed while wall advances');
    await page.reload();
    await page.locator('#checkpoint').setInputFiles(output + '/' + label + '/paused-later.json');
    await page.locator('#paused').waitFor({state:'visible'});
    await page.locator('#pause').focus();
    await page.keyboard.press('Enter');
    check(await page.locator('#task-panel').isVisible(), label + ' keyboard resumes task');
    check(await page.locator('[name=rationale]').inputValue() === draft, label + ' partial Unicode text restored literally');
    check(await page.locator('[name=recommendation]').inputValue() === 'unsure' && await page.locator('[name=confidence]').inputValue() === '2', label + ' draft selections restored');
    check(await page.locator('input[name="' + firstPrediction[0] + '"][value="' + firstPrediction[1] + '"]').isChecked(), label + ' partial prediction restored');
    check(await page.evaluate(() => window.recoveryInjected === undefined), label + ' restored text did not execute');
    check(await page.locator('#proposed').textContent() === key.packet.tasks[2].sources.proposed, label + ' restored candidate source exact');
    check(await page.locator('#baseline').textContent() === key.packet.tasks[2].sources.baseline, label + ' restored baseline source exact');
    await page.locator('#task-title').evaluate(element => element.scrollIntoView({block:'start',behavior:'instant'}));
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), label + ' no horizontal document overflow');
    await page.screenshot({path:output + '/' + label + '/restored.png'});
    await page.locator('#pause').click();
    const explicitPause = await download(label, 'explicit-pause');
    await hidden(true); // Simulated visibility event, not a claim about OS/tab scheduling.
    await page.locator('#pause').click();
    await page.waitForTimeout(200);
    const hiddenPause = await download(label, 'hidden-pause');
    check(hiddenPause.tasks[2].activeMs === explicitPause.tasks[2].activeMs, label + ' hidden pause survives ending explicit pause');
    await hidden(false);
    await page.waitForTimeout(200);
    const active = await download(label, 'active');
    check(active.tasks[2].activeMs >= hiddenPause.tasks[2].activeMs + 150, label + ' active time resumes after both pauses end');
    check(active.tasks[2].resumeCount === 2, label + ' repeated recovery counted');
    timing.push({label, initial:checkpoint.tasks[2], paused:paused.tasks[2], later:later.tasks[2], active:active.tasks[2]});
    await answer(key.answers[2]);
    await page.getByRole('button', {name:'Save and continue',exact:true}).click();
    await answer(key.answers[3]);
    await page.getByRole('button', {name:'Save and continue',exact:true}).click();
    check(await page.locator('#complete').isVisible(), label + ' completion shown');
    const completed = await download(label, 'complete');
    check(completed.finished && completed.purpose === 'rehearsal', label + ' complete synthetic record');
    check(same(completed.tasks.slice(0,2), checkpoint.tasks.slice(0,2)), label + ' frozen records survive completion');
    check(same(completed.tasks.map(row => row.resumeCount), [0,0,2,0]), label + ' only interrupted task marked resumed');
    check(completed.tasks.every(row => row.activeMs >= 0 && row.activeMs <= row.wallMs), label + ' duration ordering');
    await page.reload();
    await page.locator('#checkpoint').setInputFiles(output + '/' + label + '/complete.json');
    await page.waitForFunction(() => document.querySelector('#recovery-error').textContent.length > 0);
    check(await page.locator('#setup').isVisible() && !(await page.locator('#task-panel').isVisible()), label + ' completed record cannot reopen');
    await page.screenshot({path:output + '/' + label + '/completed-refused.png'});
  }
  check(errors.length === 0, 'no browser script errors');
  check(requests.every(url => url.startsWith(root)), 'no external requests');
  return {checks, count:checks.length, timing, browserVersion:page.context().browser().version(), humanParticipants:0, visibility:'simulated visibilitychange events'};
}
