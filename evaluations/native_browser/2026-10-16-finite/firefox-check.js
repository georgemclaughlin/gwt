async page => {
  const root = 'http://127.0.0.1:8904/';
  const output = '/home/g/code/gwt/evaluations/native_browser/2026-10-16-finite/firefox';
  const cases = await (await page.request.get(root + 'corpus/cases.json')).json();
  await page.goto(root + 'index.html');
  await page.locator('#run').waitFor({state:'visible'});
  await page.waitForFunction(() => !document.querySelector('#run').disabled);
  const checks = [];
  const check = (ok, name) => {if (!ok) throw new Error(name); checks.push(name);};
  const buildNames = ['gwt_browser_preview.wasm', 'gwt_browser_preview-1.85.0.wasm'];
  const prepared = await page.evaluate(async buildNames => {
    const {createPreview} = await import('./preview.mjs');
    window.previewHosts = [];
    const modules = [];
    for (const name of buildNames) {
      const bytes = await (await fetch(name)).arrayBuffer();
      const module = await WebAssembly.compile(bytes);
      modules.push({name, imports:WebAssembly.Module.imports(module),exports:WebAssembly.Module.exports(module)});
      window.previewHosts.push(await createPreview(bytes));
    }
    window.invalidPreview = await createPreview(new Uint8Array([0]).buffer);
    return modules;
  }, buildNames);
  for (const module of prepared) check(module.imports.length === 0, module.name + ' has no host imports');
  await page.context().setOffline(true);
  try {
    const observations = await page.evaluate(async cases => {
      const exact = text => JSON.parse(text, (_key,value,context) => typeof value === 'number' && !Number.isSafeInteger(value) && /^-?[0-9]+$/.test(context.source) ? BigInt(context.source) : value);
      const same = (a,b) => {
        if (typeof a !== typeof b) return false;
        if (a === null || b === null || typeof a !== 'object') return a === b;
        if (Array.isArray(a) !== Array.isArray(b)) return false;
        const ak = Object.keys(a).sort(), bk = Object.keys(b).sort();
        return ak.length === bk.length && ak.every((key,index) => key === bk[index] && same(a[key],b[key]));
      };
      const results = [];
      for (let build = 0; build < previewHosts.length; build++) {
        for (const row of cases) {
          const actual = exact(await previewHosts[build].run(row.requestJson));
          if (actual.kind !== 'gwt.browser-preview' || !same(actual.engine,row.engine) || !same(actual.execution,exact(row.expectedJson))) {
            throw new Error('Observation or engine mismatch: ' + build + '/' + row.id);
          }
          results.push({build,id:row.id,ok:actual.execution.ok});
        }
      }
      return results;
    }, cases);
    check(observations.length === cases.length * 2, 'both compilers preserve all captured observations offline');
    checks.push(...observations.map(row => 'exact execution and engine ' + row.build + '/' + row.id));
    const safety = await page.evaluate(async first => {
      const host = previewHosts[0];
      const checks = [];
      const expectFailure = async (fn, pattern, label) => {
        try {await fn();} catch (error) {if (!pattern.test(error.message)) throw error;checks.push(label);return;}
        throw new Error('Unexpected successful execution: ' + label);
      };
      const controller = new AbortController(); controller.abort();
      await expectFailure(() => host.run(first,{signal:controller.signal}), /cancelled/, 'pre-cancelled request');
      const active = new AbortController(); const pending = host.run(first,{signal:active.signal}); active.abort();
      await expectFailure(() => pending, /cancelled/, 'in-flight cancellation');
      await expectFailure(() => host.run(first,{timeoutMs:1}), /deadline/, 'worker deadline');
      await expectFailure(() => host.run(' '.repeat(2*1024*1024+1)), /two MiB/, 'input cap');
      await expectFailure(() => invalidPreview.run(first), /CompileError|WebAssembly/, 'invalid module failure');
      const malformed = JSON.parse(await host.run('{'));
      if (malformed.kind !== 'gwt.browser-error' || malformed.phase !== 'input') throw new Error('Malformed protocol accepted');
      checks.push('malformed protocol error');
      const largeBudget = JSON.parse(first); largeBudget.limits.execution.steps = 100001;
      if (JSON.parse(await host.run(JSON.stringify(largeBudget))).phase !== 'limits') throw new Error('Preview cap ignored');
      checks.push('native budget ceiling');
      const concurrent = await Promise.all(Array.from({length:8}, async (_,index) => {
        const request = JSON.parse(first); request.input = {invoice:{quantity:index+1,unit_price:'5'}};
        const response = JSON.parse(await host.run(JSON.stringify(request)));
        if (!response.execution.ok || response.execution.result.decision.total !== String((index+1)*6)) throw new Error('Concurrent state leak');
      }));
      checks.push('eight independent concurrent previews after failures');
      return checks;
    }, cases[0].requestJson);
    checks.push(...safety);
    await page.locator('#run').click();
    await page.waitForFunction(() => !document.querySelector('#result').hidden);
    const text = await page.locator('#result').textContent();
    check(text.includes('9007199254740993') && text.includes('108086391056891.916'), 'interactive offline preview preserves exact numbers');
    check(await page.locator('#outcome').innerText() === 'Total: 108086391056891.916', 'readable total preserves exact decimal text');
    await page.locator('#input').fill('{');
    await page.locator('#run').click();
    await page.waitForFunction(() => !document.querySelector('#result').hidden && document.querySelector('#result').textContent.includes('gwt.browser-error'));
    check((await page.locator('#result').textContent()).includes('"phase":"input"'), 'interactive malformed input stays an error');
    await page.locator('#input').fill('{"invoice":{"unit_price":"10.25","quantity":3}}');
    await page.locator('#run').click();
    await page.waitForFunction(() => !document.querySelector('#result').hidden && document.querySelector('#result').textContent.includes('"total":"36.9"'));
    for (const [name,width] of [['desktop',1440],['mobile',390]]) {
      await page.setViewportSize({width,height:1000});
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no page overflow ' + name);
      await page.screenshot({path:output + '/' + name + '.png'});
    }
    return {count:checks.length,checks,observations,modules:prepared,browserVersion:page.context().browser().version(),offlineDuringExecution:true};
  } finally {
    await page.context().setOffline(false);
    await page.evaluate(() => {for (const host of previewHosts) host.dispose(); invalidPreview.dispose();});
  }
}
