async page => {
  const root = 'http://127.0.0.1:8901/';
  const output = '/home/g/code/gwt/evaluations/human_review/2026-10-16-recovery-browser';
  for (const [label, width] of [['desktop',1440],['mobile',390]]) {
    await page.setViewportSize({width,height:1000});
    await page.goto(root + label + '/session.html');
    await page.locator('#checkpoint').setInputFiles(output + '/' + label + '/complete.json');
    await page.waitForFunction(() => document.querySelector('#recovery-error').textContent.length > 0);
    await page.locator('#recovery').evaluate(element => element.scrollIntoView({block:'center',behavior:'instant'}));
    await page.screenshot({path:output + '/' + label + '/completed-refused.png'});
    await page.reload();
    await page.locator('#checkpoint').setInputFiles(output + '/' + label + '/checkpoint.json');
    await page.locator('#paused').waitFor({state:'visible'});
    await page.locator('#session-controls').evaluate(element => element.scrollIntoView({block:'center',behavior:'instant'}));
    await page.screenshot({path:output + '/' + label + '/paused-restoration.png'});
  }
  return {screenshots:4,downloadedRecordsChanged:false};
}
