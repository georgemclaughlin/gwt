self.postMessage({ready:true});
self.onmessage = async ({data}) => {
  try {
    const {instance} = await WebAssembly.instantiate(data.wasm, {});
    const api = instance.exports;
    const bytes = new TextEncoder().encode(data.request);
    if (!api.gwt_reset(bytes.length)) throw new Error('Preview input exceeds two MiB.');
    for (let offset = 0; offset < bytes.length; offset += 4) {
      let word = 0;
      for (let index = 0; index < 4 && offset + index < bytes.length; index++) word |= bytes[offset + index] << (index * 8);
      if (!api.gwt_put(offset, word >>> 0)) throw new Error('Input transfer refused.');
    }
    const length = api.gwt_run();
    if (length > 8 * 1024 * 1024) throw new Error('Invalid preview output length.');
    const output = new Uint8Array(length);
    for (let offset = 0; offset < length; offset += 4) {
      const word = api.gwt_get(offset);
      for (let index = 0; index < 4 && offset + index < length; index++) output[offset + index] = word >>> (index * 8);
    }
    self.postMessage({text:new TextDecoder('utf-8', {fatal:true}).decode(output)});
  } catch (error) {
    self.postMessage({error:String(error)});
  }
};
