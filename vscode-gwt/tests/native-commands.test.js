const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const nativeTools = require('../native-tools');

// Exercise the adapter's public command path with deterministic editor dialogs
// and process responses. Actual CLI/extension-host agreement is checked separately.
async function harness(t, { workspace = '/project', limitsName = 'policies/operating limits.json', saveLimits = true } = {}) {
  const calls = [], messages = [], saved = [];
  let completionProvider;
  const uri = filename => ({ scheme: 'file', fsPath: path.resolve(filename), toString: () => filename });
  const root = path.resolve('/project/domain');
  const entry = { languageId: 'gwt', uri: uri(path.join(root, 'rules.gwt')), isDirty: true, getText: () => 'REQUEST allocate\n',
    async save() { this.isDirty = false; saved.push('source'); return true; } };
  const limitsPath = path.resolve(workspace || root, limitsName);
  const limits = { languageId: 'json', uri: uri(limitsPath), isDirty: true,
    async save() { saved.push('limits'); if (saveLimits) this.isDirty = false; return saveLimits; } };
  const other = { languageId: 'json', uri: uri('/project/unrelated.json'), isDirty: true,
    async save() { throw new Error('Unrelated JSON must not be saved'); } };
  const config = { 'native.command': 'selected-native', 'native.importRoot': root, 'native.limitsFile': limitsName };
  const report = { kind: 'gwt.native-editor-check', schemaVersion: 1, ok: true, requests: ['allocate'], scenarios: [], checkedSources: {} };
  const exact = '{"kind":"gwt.native-profile","ok":true,"steps":9007199254740993}\n';
  t.mock.method(nativeTools, 'runGwt', (command, args, input, options) => {
    calls.push({ command, args, input, options });
    const stdout = args[0] === 'check-editor' ? JSON.stringify(report) : args[0] === 'complete-editor'
      ? JSON.stringify({ kind: 'gwt.native-completion', schemaVersion: 1, basis: 'declarations', ok: true, items: [], replacement: null }) : exact;
    return { promise: Promise.resolve({ payload: JSON.parse(stdout), stdout, stderr: '', exitCode: 0 }), cancel() {} };
  });
  delete require.cache[require.resolve('../native-editor')];
  const disposable = () => ({ dispose() {} });
  const vscode = {
    workspace: { textDocuments: [entry, limits, other], workspaceFolders: workspace ? [{ uri: uri(workspace) }] : [],
      getWorkspaceFolder: () => workspace ? { uri: uri(workspace) } : undefined,
      getConfiguration: (_name, scope) => { assert.equal(scope, entry.uri); return { get: (key, fallback) => config[key] ?? fallback }; },
      createFileSystemWatcher: () => ({ dispose() {}, onDidChange: disposable, onDidCreate: disposable, onDidDelete: disposable }),
      onDidOpenTextDocument: disposable, onDidChangeTextDocument: disposable, onDidCloseTextDocument: disposable },
    window: { activeTextEditor: { document: entry },
      showQuickPick: async options => options.find(item => item.kind === 'request'),
      showOpenDialog: async () => [uri('/project/request input.json')],
      showErrorMessage: text => messages.push(text), showInformationMessage: text => messages.push(text) },
    languages: { createDiagnosticCollection: () => ({ clear() {}, set() {}, dispose() {} }),
      registerDocumentSymbolProvider: disposable, registerDocumentFormattingEditProvider: disposable,
      registerHoverProvider: disposable, registerDefinitionProvider: disposable,
      registerCompletionItemProvider: (_selector, provider) => { completionProvider = provider; return disposable(); } },
  };
  const context = { subscriptions: [] };
  const output = [];
  const editor = require('../native-editor').activateNative(vscode, context, {
    show() {}, append: text => output.push(text), appendLine: text => output.push(text),
  });
  t.after(() => { for (const item of context.subscriptions) item.dispose(); delete require.cache[require.resolve('../native-editor')]; });
  return { editor, vscode, calls, saved, config, limitsPath, root, output, messages, exact, other, completionProvider, entry };
}

test('completion converts the editor position through UTF-16 before sending the UTF-8 query', async t => {
  const h = await harness(t);
  const source = '# 😀 café\r\nWHEN rev';
  h.entry.getText = () => source;
  h.entry.offsetAt = position => {
    assert.deepEqual(position, { line: 1, character: 8 });
    return source.length;
  };
  const token = { isCancellationRequested: false, onCancellationRequested: () => ({ dispose() {} }) };
  assert.deepEqual(await h.completionProvider.provideCompletionItems(h.entry, { line: 1, character: 8 }, token), []);
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.calls[0].args, ['complete-editor']);
  assert.deepEqual(h.calls[0].input.query, { path: 'rules.gwt', byteOffset: Buffer.byteLength(source) });
  assert.deepEqual(h.saved, []);
});

test('request profiling forwards input and workspace budget independently of the import root', async t => {
  const h = await harness(t);
  const result = await h.editor.command('profile');
  assert.equal(result.ok, true);
  assert.equal(result.stdout, h.exact);
  assert.deepEqual(h.saved, ['source', 'limits']);
  assert.equal(h.other.isDirty, true);
  assert.deepEqual(h.calls.map(call => call.args[0]), ['check-editor', 'profile']);
  assert.deepEqual(h.calls[1].args, ['profile', path.join(h.root, 'rules.gwt'), '--request', 'allocate',
    '--input', path.resolve('/project/request input.json'), '--import-root', h.root, '--limits', h.limitsPath]);
  assert.equal(h.calls[1].command, 'selected-native');
  assert(h.output.includes(`Execution limits: ${h.limitsPath}`));
  assert(h.output.includes(h.exact), 'Exact output must not be reserialized through JS numbers');
});

test('cancelled budget save or request input selection prevents execution', async t => {
  const h = await harness(t, { saveLimits: false });
  assert.equal(await h.editor.command('profile'), undefined);
  assert.deepEqual(h.calls.map(call => call.args[0]), ['check-editor']);
  assert.deepEqual(h.saved, ['source', 'limits']);
  h.calls.length = 0;
  h.saved.length = 0;
  h.vscode.window.showOpenDialog = async () => undefined;
  assert.equal(await h.editor.command('profile'), undefined);
  assert.deepEqual(h.calls.map(call => call.args[0]), ['check-editor']);
  assert.deepEqual(h.saved, []);
});

test('outside-workspace budgets use the file parent and clearing configuration restores default arguments', async t => {
  const h = await harness(t, { workspace: null });
  const limits = h.vscode.workspace.textDocuments[1];
  await h.editor.command('test');
  assert.equal(h.calls[0].args.at(-1), limits.uri.fsPath);
  assert.deepEqual(h.saved, ['source', 'limits']);
  h.config['native.limitsFile'] = '';
  await h.editor.command('validate');
  assert.deepEqual(h.calls[1].args, ['validate', path.join(h.root, 'rules.gwt'), '--import-root', h.root]);
  assert(h.output.includes('Execution limits: native defaults'));
});
test('a malformed execution setting does not disable static checking or silently choose defaults', async t => {
  const h = await harness(t);
  h.config['native.limitsFile'] = 42;
  assert.equal((await h.editor.command('check')).ok, true);
  assert.equal((await h.editor.command('test')).ok, false);
  assert.deepEqual(h.calls.map(call => call.args[0]), ['check-editor']);
  assert(h.messages.some(message => message.includes('gwt.limitsFile must be a file path')));
});
