async page => {
  const messages=[];
  page.on('console',m=>messages.push({type:m.type(),text:m.text()}));
  page.on('pageerror',e=>messages.push({error:String(e)}));
  await page.goto('http://127.0.0.1:8904/index.html');
  const online=await page.evaluate(async()=>{
    window.testBytes=await(await fetch('gwt_browser_preview.wasm')).arrayBuffer();
    window.testCases=await(await fetch('corpus/cases.json')).json();
    const {createPreview}=await import('./preview.mjs');window.host=await createPreview(testBytes);
    const results={};
    try {const {instance}=await WebAssembly.instantiate(testBytes,{});results.instantiate=Object.keys(instance.exports);}catch(e){results.instantiate=String(e);}
    try {results.host=(await host.run(testCases[0].requestJson)).slice(0,200);}catch(e){results.host=String(e);}
    window.workerUrl=URL.createObjectURL(new Blob(['self.postMessage("ready")'],{type:'text/javascript'}));
    window.workerTest=type=>new Promise(resolve=>{
      const w=new Worker(workerUrl,type?{type}:{});const timer=setTimeout(()=>{w.terminate();resolve('timeout')},2000);
      const done=value=>{clearTimeout(timer);w.terminate();resolve(value)};
      w.onmessage=e=>done({text:e.data});w.onerror=e=>done({error:e.message,filename:e.filename,line:e.lineno});
    });
    results.classic=await workerTest();results.module=await workerTest('module');return results;
  });
  await page.context().setOffline(true);
  const offline=await page.evaluate(async()=>{
    const results={};try {results.host=(await host.run(testCases[0].requestJson)).slice(0,200);}catch(e){results.host=String(e)}
    results.classic=await workerTest();results.module=await workerTest('module');host.dispose();URL.revokeObjectURL(workerUrl);return results;
  });
  await page.context().setOffline(false);
  return {online,offline,messages,browserVersion:page.context().browser().version()};
}
