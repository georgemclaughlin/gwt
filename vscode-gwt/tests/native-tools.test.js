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

test('configured legacy preview paths migrate while the default is the single gwt command', () => {
  const { setting } = require('../native-tools');
  const values = { 'native.command': { workspaceValue: '/previous/engine' } };
  const config = { inspect: key => values[key] };
  assert.equal(setting(config, 'command', 'gwt'), '/previous/engine');
  values.command = { workspaceValue: '/installed/gwt' };
  assert.equal(setting(config, 'command', 'gwt'), '/installed/gwt');
  assert.equal(setting({ inspect: () => undefined }, 'command', 'gwt'), 'gwt');
});
test('an old Python gwt on PATH is rejected before any source command executes', async () => {
  const fs = require('node:fs/promises');
  const os = require('node:os');
  const { runGwt } = require('../native-tools');
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'gwt-engine-test-'));
  try {
    const marker = path.join(dir, 'executed');
    const executable = path.join(dir, 'gwt');
    await fs.writeFile(executable, `#!${process.execPath}\nif(process.argv[2]==='version')console.log(JSON.stringify({packageName:'gwtlang',packageVersion:'0.3.0'}));else require('node:fs').writeFileSync(${JSON.stringify(marker)},'bad');\n`, { mode: 0o755 });
    await assert.rejects(runGwt(executable, ['run', 'policy.gwt']).promise, /Remove the old gwtlang installation/);
    await assert.rejects(fs.stat(marker), { code: 'ENOENT' });
  } finally { await fs.rm(dir, { recursive: true, force: true }); }
});
