const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { inside, snapshot, digest, byteOffset, byteRange, runNative } = require('../native-tools');

test('native byte spans map Unicode and CRLF to UTF-16 editor ranges', () => {
  const source = '# 😀\r\nTHEN "😀" + true\r\n';
  const start = Buffer.byteLength(source.slice(0, source.indexOf('true')));
  assert.deepEqual(byteRange(source, { start, end: start + 4 }), { start: { line: 1, character: 12 }, end: { line: 1, character: 16 } });
  assert.throws(() => byteRange('😀', { start: 1, end: 4 }), /UTF-8/);
  assert.throws(() => byteRange('a', { start: 0, end: 2 }), /span/);
  assert.equal(byteOffset(source, source.indexOf('true')), start);
  assert.throws(() => byteOffset('😀', 1), /UTF-16/);
  assert.throws(() => byteOffset('a', 2), /offset/);
});
test('snapshots include only canonical relative documents below the import root', () => {
  const root = path.resolve('/project');
  assert.equal(inside(root, path.join(root, '../other/file.gwt')), false);
  assert.equal(inside(root, root), false);
  const result = snapshot(path.join(root, 'entry.gwt'), root, [{ filename: path.join(root, 'entry.gwt'), text: 'unsaved' }, { filename: path.join(root, '../other/file.gwt'), text: 'outside' }]);
  assert.deepEqual(result.documents, [{ path: 'entry.gwt', text: 'unsaved' }]);
  assert.notEqual(digest('old'), digest('new'));
});
test('process output preserves exact number text and legitimate failure payloads', async () => {
  const result = await runNative(process.execPath, ['-e', 'process.stdout.write(\'{"ok":false,"value":9007199254740993}\');process.exitCode=1;']).promise;
  assert.equal(result.exitCode, 1);
  assert.match(result.stdout, /9007199254740993/);
  assert.equal(result.payload.ok, false);
});
test('missing commands, invalid output, timeouts, and output limits remain process errors', async () => {
  await assert.rejects(runNative('gwt-no-such-executable-for-test', []).promise, /process failed/);
  await assert.rejects(runNative(process.execPath, ['-e', 'console.log("not JSON")']).promise, /invalid JSON/);
  await assert.rejects(runNative(process.execPath, ['-e', 'setTimeout(()=>{},5000)'], undefined, { timeout: 20 }).promise, /process failed/);
  await assert.rejects(runNative(process.execPath, ['-e', 'process.stdout.write("x".repeat(2048))'], undefined, { maxBuffer: 1024 }).promise, /process failed/);
});
test('cancellation stops an obsolete native check', async () => {
  const job = runNative(process.execPath, ['-e', 'setTimeout(()=>{},5000)']);
  job.cancel();
  await assert.rejects(job.promise, /process failed/);
});
test('stderr-only configuration failures retain the command diagnostic and remain bounded', async () => {
  await assert.rejects(runNative(process.execPath, ['-e', 'process.stderr.write("limits.json: invalid execution limits: unknown field");process.exitCode=1;']).promise,
    /Native GWT command failed: limits.json: invalid execution limits: unknown field/);
  await assert.rejects(runNative(process.execPath, ['-e', 'process.stderr.write("x".repeat(2000));process.exitCode=1;']).promise,
    error => error.message.length <= 1030 && !error.message.includes('invalid JSON'));
});
