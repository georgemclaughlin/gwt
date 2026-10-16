const childProcess = require('child_process');
const crypto = require('crypto');
const path = require('path');

function inside(root, filename) {
  const relative = path.relative(root, filename);
  return relative !== '' && !path.isAbsolute(relative) && relative !== '..' && !relative.startsWith(`..${path.sep}`);
}
function snapshot(entry, root, documents) {
  const overlays = documents.filter(document => inside(root, document.filename))
    .map(document => ({ path: path.relative(root, document.filename).split(path.sep).join('/'), text: document.text }));
  return { entry, importRoot: root, documents: overlays };
}
function digest(text) { return `sha256:${crypto.createHash('sha256').update(text).digest('hex')}`; }
function byteOffset(source, offset) {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > source.length) throw new Error('Invalid editor offset.');
  if (offset > 0 && /[\uD800-\uDBFF]/.test(source[offset - 1]) && /[\uDC00-\uDFFF]/.test(source[offset] || '')) throw new Error('Editor offset splits a UTF-16 character.');
  return Buffer.byteLength(source.slice(0, offset), 'utf8');
}
function byteRange(source, span) {
  const bytes = Buffer.from(source, 'utf8');
  if (![span.start, span.end].every(Number.isSafeInteger) || span.start < 0 || span.end < span.start || span.end > bytes.length) throw new Error('Invalid native source span.');
  const position = offset => {
    const prefix = bytes.subarray(0, offset).toString('utf8');
    if (Buffer.byteLength(prefix, 'utf8') !== offset) throw new Error('Native span splits a UTF-8 character.');
    const lines = prefix.split('\n');
    return { line: lines.length - 1, character: lines[lines.length - 1].length };
  };
  return { start: position(span.start), end: position(span.end) };
}
function runNative(command, args, input, options = {}) {
  let child;
  const promise = new Promise((resolve, reject) => {
    child = childProcess.execFile(command, args, {
      cwd: options.cwd, encoding: 'utf8', shell: false, windowsHide: true,
      timeout: options.timeout ?? 10000, maxBuffer: options.maxBuffer ?? 8 * 1024 * 1024,
    }, (error, stdout, stderr) => {
      if (error && error.code !== 1) { reject(new Error(`Native GWT process failed: ${error.message}`)); return; }
      if (error?.code === 1 && stdout.trim() === '' && stderr.trim()) {
        reject(new Error(`Native GWT command failed: ${stderr.trim().slice(0, 1000)}`)); return;
      }
      try { resolve({ payload: JSON.parse(stdout), stdout, stderr, exitCode: error ? 1 : 0 }); }
      catch (_) { reject(new Error(`Native GWT returned invalid JSON. ${stderr.slice(0, 1000)}`)); }
    });
    child.stdin.on('error', () => {}); // Early process failure is reported by execFile's callback.
    child.stdin.end(input === undefined ? undefined : JSON.stringify(input));
  });
  return { promise, cancel: () => child?.kill() };
}
module.exports = { inside, snapshot, digest, byteOffset, byteRange, runNative };
