export async function createPreview(wasm) {
  const response = await fetch(new URL('./worker.mjs', import.meta.url));
  if (!response.ok) throw new Error('Could not load preview worker.');
  const workerUrl = URL.createObjectURL(new Blob([await response.text()], {type:'text/javascript'}));
  let disposed = false;
  return {
    run(request, options) {
      if (disposed) throw new Error('Preview has been disposed.');
      return runPreview(wasm, workerUrl, request, options);
    },
    dispose() { disposed = true; URL.revokeObjectURL(workerUrl); },
  };
}

function runPreview(wasm, workerUrl, request, {timeoutMs = 10000, signal} = {}) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > 2147483647) throw new TypeError('Invalid preview timeout.');
  if (typeof request !== 'string' || new TextEncoder().encode(request).length > 2 * 1024 * 1024) throw new TypeError('Supply at most two MiB of request JSON text.');
  return new Promise((resolve, reject) => {
    const worker = new Worker(workerUrl, {type:'module'});
    let finished = false;
    const done = (error, text) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      worker.terminate();
      if (error) reject(error); else resolve(text);
    };
    const abort = () => done(new Error('Preview cancelled.'));
    const timer = setTimeout(() => done(new Error('Preview deadline exceeded.')), timeoutMs);
    signal?.addEventListener('abort', abort, {once:true});
    if (signal?.aborted) { abort(); return; }
    worker.onerror = event => { event.preventDefault(); done(new Error(event.message || 'Preview worker failed.')); };
    worker.onmessage = ({data}) => data.error ? done(new Error(data.error)) : done(null, data.text);
    try { worker.postMessage({wasm, request}); } catch (error) { done(error); }
  });
}
