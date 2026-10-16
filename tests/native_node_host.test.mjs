import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { test } from 'node:test';
import { mkdtemp, readFile, writeFile, copyFile, readdir, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { parseExact, stringifyExact, runNativeRequest, NativeHostError } from '../examples/native_node_host/native.mjs';

const execute = promisify(execFile);
const executable = process.env.GWT_NATIVE_PATH;
const source = fileURLToPath(new URL('../crates/gwt-core/tests/fixtures/invoice.gwt', import.meta.url));
const adapter = fileURLToPath(new URL('../examples/native_node_host/native.mjs', import.meta.url));
const records = [];

test('exact JSON preserves unsafe integers and rejects lossy inputs', () => {
  const original = '{"large":9007199254740993,"negative":-9007199254740993,"decimal":"0.000000000000000001","safe":42,"nested":[null,true,"quoted \\\"9007199254740993\\\""]}';
  const value = parseExact(original);
  assert.equal(value.large, 9007199254740993n);
  assert.equal(value.negative, -9007199254740993n);
  assert.equal(value.safe, 42);
  assert.deepEqual(parseExact(stringifyExact(value)), value);
  for (const input of [1.1, Infinity, NaN, 9007199254740992, {lost: undefined}, [undefined], new Date(), new Array(1)]) {
    assert.throws(() => stringifyExact(input), TypeError);
  }
  for (const input of ['1.0', '1e3', '1e999', '{"x":0.01}']) assert.throws(() => parseExact(input), TypeError);
  const cyclic = {}; cyclic.self = cyclic;
  assert.throws(() => stringifyExact(cyclic), /Circular/);
  assert.equal(stringifyExact({text: 'not a numeric token: 9007199254740993'}), '{"text":"not a numeric token: 9007199254740993"}');
});

test('native host qualification', async t => {
  assert.ok(executable, 'Set GWT_NATIVE_PATH to an explicitly selected packaged executable.');
  const workspace = await mkdtemp(join(tmpdir(), 'gwt-node-host-'));
  const scratch = join(workspace, 'private inputs');
  await mkdir(scratch);
  const program = join(workspace, 'invoice ; $(touch unintended).gwt');
  const binary = join(workspace, 'native engine ; literal');
  await copyFile(source, program);
  await copyFile(executable, binary);
  const base = {executable: binary, program, request: 'price invoice', temporaryRoot: scratch};
  const invoice = (quantity = 3, unit_price = '10.25') => ({invoice: {quantity, unit_price}});
  const invoke = overrides => runNativeRequest({...base, input: invoice(), ...overrides});
  const retain = (name, value) => { records.push({name, ...value}); return value; };
  const clean = async () => assert.deepEqual(await readdir(scratch), [], 'Invocation input directories must be removed.');
  async function fake(name, body) {
    const path = join(workspace, name);
    await writeFile(path, `#!${process.execPath}\n${body}\n`, {mode: 0o700});
    return path;
  }
  try {
    await t.test('exact totals and complete observation equal direct native execution', async () => {
      // Expected totals are hand-derived rational products, independent of the adapter.
      for (const [quantity, price, total] of [
        [3, '10.25', '36.9'], [1, '0', '0'],
        [9007199254740993n, '0.01', '108086391056891.916'],
        [9007199254740993n, '0.000000000000000001', '0.0108086391056891916'],
      ]) {
        const input = invoice(quantity, price);
        const actual = retain('invoice-' + String(quantity) + '-' + price, await invoke({input}));
        assert.equal(actual.execution.ok, true);
        assert.equal(actual.execution.result.decision.total, total);
        assert.equal(actual.execution.state.invoice.quantity, quantity);
        const inputPath = join(workspace, 'direct.json');
        await writeFile(inputPath, stringifyExact(input));
        const direct = await execute(binary, ['run', program, '--request', base.request, '--input', inputPath]);
        assert.deepEqual(actual.execution, parseExact(direct.stdout));
        assert.equal(actual.stdout, direct.stdout);
      }
      await clean();
    });
    await t.test('contract and behavior failures stay structured failures', async () => {
      for (const [name, input, hasEvents] of [
        ['wrong-quantity-type', invoice(true), false],
        ['unknown-field', {invoice: {...invoice().invoice, extra: 'unexpected'}}, false],
        ['zero-quantity', invoice(0), true],
      ]) {
        const actual = retain(name, await invoke({input}));
        assert.equal(actual.execution.ok, false);
        assert.equal(actual.exitCode, 1);
        assert.ok(actual.execution.diagnostic.code);
        assert.equal(actual.execution.events.length > 0, hasEvents);
      }
      await clean();
    });
    await t.test('execution budget failure is distinct from process termination', async () => {
      const actual = retain('zero-step-budget', await invoke({limits: {
        execution: {steps: 0, evidenceBytes: 1048576, textBytes: 1048576}, callDepth: 64,
      }}));
      assert.equal(actual.execution.ok, false);
      assert.equal(actual.exitCode, 1);
      assert.match(actual.execution.diagnostic.code, /limit|budget/);
      await clean();
    });
    await t.test('concurrent requests keep independent state and private inputs', async () => {
      const results = await Promise.all(Array.from({length: 12}, (_, index) => invoke({input: invoice(index + 1, '5')})));
      results.forEach((result, index) => {
        assert.equal(result.execution.state.invoice.quantity, index + 1);
        assert.equal(result.execution.result.decision.total, String((index + 1) * 6));
      });
      records.push({name: 'concurrent', invocations: results.length});
      await clean();
    });
    await t.test('separate Node host runs copied module with empty PATH', async () => {
      await copyFile(adapter, join(workspace, 'native.mjs'));
      const driver = join(workspace, 'host.mjs');
      await writeFile(driver, `import {runNativeRequest} from './native.mjs';
        const result = await runNativeRequest({executable: process.argv[2], program: process.argv[3],
          request: 'price invoice', input: {invoice: {quantity: 9007199254740993n, unit_price: '0.01'}}});
        process.stdout.write(result.stdout);`);
      const {stdout} = await execute(process.execPath, [driver, binary, program], {cwd: workspace, env: {PATH: ''}, timeout: 10000});
      const parsed = parseExact(stdout);
      assert.equal(parsed.result.decision.total, '108086391056891.916');
      assert.equal(parsed.state.invoice.quantity, 9007199254740993n);
      records.push({name: 'independent-host', emptyPath: true, observation: parsed});
    });
    await t.test('compiler errors remain command errors', async () => {
      const invalid = join(workspace, 'invalid.gwt');
      await writeFile(invalid, 'not a GWT program\n');
      await assert.rejects(invoke({program: invalid}), error => error instanceof NativeHostError && error.kind === 'command' && error.payload.ok === false);
      await clean();
    });
    await t.test('missing executable and nonexistent source cannot become policy outcomes', async () => {
      await assert.rejects(invoke({executable: join(workspace, 'missing')}), error => error.kind === 'process');
      await assert.rejects(invoke({program: join(workspace, 'missing.gwt')}), error => error.kind === 'command' || error.kind === 'protocol');
      await clean();
    });
    await t.test('timeout kills a stalled process and removes its private inputs', async () => {
      const stalled = await fake('stall', 'setInterval(() => {}, 1000);');
      await assert.rejects(invoke({executable: stalled, timeoutMs: 100}), error => error.kind === 'process' && error.cause.signal === 'SIGKILL');
      await clean();
    });
    await t.test('output limit rejects truncated output', async () => {
      const noisy = await fake('noise', 'process.stdout.write("x".repeat(65536));');
      await assert.rejects(invoke({executable: noisy, maxOutputBytes: 1024}), error => error.kind === 'process');
      await clean();
    });
    await t.test('invalid and inconsistent protocol responses fail closed', async () => {
      for (const [name, body] of [
        ['invalid-json', 'console.log("not JSON");'],
        ['false-success', 'console.log(JSON.stringify({kind:"gwt.native-run",schemaVersion:1,ok:false,request:"price invoice",events:[],diagnostic:{code:"fake"}}));'],
        ['unknown-version', 'console.log(JSON.stringify({kind:"gwt.native-run",schemaVersion:2,ok:true,request:"price invoice",events:[]}));'],
        ['wrong-request', 'console.log(JSON.stringify({kind:"gwt.native-run",schemaVersion:1,ok:true,request:"another request",events:[]}));'],
      ]) {
        await assert.rejects(invoke({executable: await fake(name, body)}), error => error.kind === 'protocol');
      }
      await clean();
    });
    await t.test('input and process-limit errors do not create invocation files', async () => {
      for (const options of [{input: invoice(1.5)}, {input: {text: 'x'.repeat(1048576)}}, {timeoutMs: 0}, {timeoutMs: 2147483648}, {maxOutputBytes: 0}]) {
        await assert.rejects(invoke(options), TypeError);
      }
      await clean();
    });
    if (process.env.GWT_NODE_EVIDENCE) {
      const output = resolve(process.env.GWT_NODE_EVIDENCE);
      await mkdir(output, {recursive: true});
      const hash = async path => createHash('sha256').update(await readFile(path)).digest('hex');
      await writeFile(join(output, 'observations.json'), stringifyExact({
        node: process.version, platform: process.platform, architecture: process.arch,
        executable, executableSha256: await hash(executable), adapterSha256: await hash(adapter),
        sourceSha256: await hash(source), records,
      }) + '\n');
    }
  } finally {
    await rm(workspace, {recursive: true, force: true});
  }
});
