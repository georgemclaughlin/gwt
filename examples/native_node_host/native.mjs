// Reference process boundary for a trusted gwt-native executable; Node 22+.
import { execFile } from 'node:child_process';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { isAbsolute, join, resolve } from 'node:path';

export function parseExact(text) {
  return JSON.parse(text, (_key, value, context) => {
    if (typeof value !== 'number') return value;
    if (!context || !/^-?(0|[1-9][0-9]*)$/.test(context.source)) {
      throw new TypeError('Expected an integer JSON token; decimals use strings. Node 22+ is required.');
    }
    return Number.isSafeInteger(value) ? value : BigInt(context.source);
  });
}

// Accept data only: no toJSON conversions, omitted undefined fields, sparse
// arrays, or rounded Number values. Large integers must arrive as bigint.
export function stringifyExact(value) {
  const ancestors = new Set();
  function encode(item, depth) {
    if (depth > 100) throw new TypeError('Host input exceeds 100 nested containers.');
    if (item === null || typeof item === 'string' || typeof item === 'boolean') return JSON.stringify(item);
    if (typeof item === 'bigint') return item.toString();
    if (typeof item === 'number') {
      if (!Number.isSafeInteger(item)) throw new TypeError('Use bigint for large integers and strings for decimals.');
      return JSON.stringify(item);
    }
    if (typeof item !== 'object') throw new TypeError('Expected JSON data or bigint.');
    if (ancestors.has(item)) throw new TypeError('Circular host input.');
    if (!Array.isArray(item) && ![Object.prototype, null].includes(Object.getPrototypeOf(item))) {
      throw new TypeError('Expected a plain object or array.');
    }
    ancestors.add(item);
    try {
      if (Array.isArray(item)) {
        return '[' + Array.from({length: item.length}, (_, index) => encode(item[index], depth + 1)).join(',') + ']';
      }
      return '{' + Object.keys(item).map(key => JSON.stringify(key) + ':' + encode(item[key], depth + 1)).join(',') + '}';
    } finally {
      ancestors.delete(item);
    }
  }
  return encode(value, 0);
}

export class NativeHostError extends Error {
  constructor(message, {kind, cause, stdout = '', stderr = '', payload = null} = {}) {
    super(message, {cause});
    this.name = 'NativeHostError';
    Object.assign(this, {kind, stdout, stderr, payload});
  }
}

function positiveInteger(value, name) {
  if (!Number.isSafeInteger(value) || value <= 0) throw new TypeError(`${name} must be a positive safe integer.`);
}

export async function runNativeRequest({
  executable, program, request, input, importRoot, limits,
  timeoutMs = 10000, maxOutputBytes = 8 * 1024 * 1024, temporaryRoot = tmpdir(),
}) {
  if (typeof executable !== 'string' || !isAbsolute(executable)) throw new TypeError('Supply an absolute executable path.');
  if (typeof program !== 'string' || !program) throw new TypeError('Supply a program path.');
  if (typeof request !== 'string' || !request) throw new TypeError('Supply a named request.');
  positiveInteger(timeoutMs, 'timeoutMs');
  if (timeoutMs > 2147483647) throw new TypeError('timeoutMs exceeds the Node timer range.');
  positiveInteger(maxOutputBytes, 'maxOutputBytes');
  const inputText = stringifyExact(input);
  if (Buffer.byteLength(inputText) > 1048576) throw new TypeError('Host input exceeds the native 1 MiB file limit.');
  const limitsText = limits === undefined ? undefined : stringifyExact(limits);
  const directory = await mkdtemp(join(resolve(temporaryRoot), 'gwt-node-'));
  try {
    const inputFile = join(directory, 'input.json');
    await writeFile(inputFile, inputText, {mode: 0o600});
    const args = ['run', resolve(program), '--request', request, '--input', inputFile];
    if (importRoot !== undefined) args.push('--import-root', resolve(importRoot));
    if (limitsText !== undefined) {
      const limitsFile = join(directory, 'limits.json');
      await writeFile(limitsFile, limitsText, {mode: 0o600});
      args.push('--limits', limitsFile);
    }
    const {error, stdout, stderr} = await new Promise(resolveProcess => {
      const child = execFile(executable, args, {
        shell: false, encoding: 'utf8', windowsHide: true, timeout: timeoutMs,
        maxBuffer: maxOutputBytes, killSignal: 'SIGKILL',
      }, (error, stdout, stderr) => resolveProcess({error, stdout, stderr}));
      child.stdin.on('error', () => {});
      child.stdin.end();
    });
    if (error && (error.code !== 1 || error.signal || error.killed)) {
      throw new NativeHostError('Native process did not complete normally.', {kind: 'process', cause: error, stdout, stderr});
    }
    let payload;
    try { payload = parseExact(stdout); }
    catch (cause) {
      throw new NativeHostError('Native command did not return exact JSON.', {kind: 'protocol', cause, stdout, stderr});
    }
    const exitCode = error ? 1 : 0;
    if (exitCode === 1 && payload?.ok === false && typeof payload.phase === 'string' && payload.diagnostic) {
      throw new NativeHostError('Native command failed before request execution.', {kind: 'command', stdout, stderr, payload});
    }
    if (payload?.kind !== 'gwt.native-run' || payload.schemaVersion !== 1 ||
        typeof payload.ok !== 'boolean' || payload.ok !== (exitCode === 0) ||
        payload.request !== request || !Array.isArray(payload.events) ||
        (!payload.ok && !payload.diagnostic)) {
      throw new NativeHostError('Unexpected native execution envelope.', {kind: 'protocol', stdout, stderr, payload});
    }
    return {execution: payload, stdout, stderr, exitCode};
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
}
