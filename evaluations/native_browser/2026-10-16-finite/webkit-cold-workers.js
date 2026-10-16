async page => {
  await page.goto('http://127.0.0.1:8904/index.html');
  await page.evaluate(async()=>{
    window.sources=Array.from({length:4},()=>URL.createObjectURL(new Blob(['self.postMessage("ready")'],{type:'text/javascript'})));
    window.test=(index,type)=>new Promise(resolve=>{const w=new Worker(sources[index],type?{type}:{});const t=setTimeout(()=>{w.terminate();resolve('timeout')},2000);const done=v=>{clearTimeout(t);w.terminate();resolve(v)};w.onmessage=e=>done(e.data);w.onerror=e=>done({error:e.message,filename:e.filename,line:e.lineno});});
  });
  await page.context().setOffline(true);
  const cold=await page.evaluate(async()=>({classic:await test(0),module:await test(1,'module')}));
  await page.context().setOffline(false);
  const warm=await page.evaluate(async()=>({classic:await test(2),module:await test(3,'module')}));
  await page.context().setOffline(true);
  const warmedOffline=await page.evaluate(async()=>({classic:await test(2),module:await test(3,'module')}));
  await page.context().setOffline(false);
  return {cold,warm,warmedOffline};
}
