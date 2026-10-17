const fs = require('fs/promises');
const path = require('path');
const { inside, snapshot, digest, byteOffset, byteRange, runGwt: runNative, setting } = require('./native-tools');

function activateNative(vscode, context, output) {
  const collection = vscode.languages.createDiagnosticCollection('gwt');
  const jobs = new Set();
  let timer, generation = 0, disposed = false;
  const documents = () => vscode.workspace.textDocuments.filter(document => document.languageId === 'gwt' && document.uri.scheme === 'file');
  function settings(document, execution = false) {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri) || (document.uri.scheme === 'untitled' ? vscode.workspace.workspaceFolders?.[0] : undefined);
    const config = vscode.workspace.getConfiguration('gwt', document.uri.scheme === 'untitled' ? workspaceFolder?.uri : document.uri);
    const folder = workspaceFolder?.uri.fsPath;
    const base = folder || path.dirname(document.uri.fsPath);
    const configuredRoot = setting(config, 'importRoot', '');
    const configuredLimits = execution ? setting(config, 'limitsFile', '') : '';
    if (typeof configuredLimits !== 'string') throw new Error('gwt.limitsFile must be a file path or an empty string.');
    return { command: setting(config, 'command', 'gwt'), root: configuredRoot ? path.resolve(base, configuredRoot) : base,
      limitsFile: configuredLimits ? path.resolve(base, configuredLimits) : undefined };
  }
  function invoke(command, args, input, root, timeout = 10000, background = true, token) {
    const job = runNative(command, args, input, { cwd: root, timeout, maxBuffer: 32 * 1024 * 1024 });
    job.background = background;
    jobs.add(job);
    const cancellation = token?.onCancellationRequested(() => job.cancel());
    if (token?.isCancellationRequested) job.cancel();
    return job.promise.finally(() => { cancellation?.dispose(); jobs.delete(job); });
  }
  async function sourceText(filename) {
    const open = documents().find(document => path.resolve(document.uri.fsPath) === path.resolve(filename));
    if (open) return open.getText();
    const file = await fs.open(filename, 'r');
    try {
      const bytes = Buffer.alloc(1024 * 1024 + 1);
      let length = 0;
      while (length < bytes.length) {
        const { bytesRead } = await file.read(bytes, length, bytes.length - length, length);
        if (bytesRead === 0) break;
        length += bytesRead;
      }
      if (length > 1024 * 1024) throw new Error('Source exceeds one MiB.');
      return bytes.subarray(0, length).toString('utf8');
    } finally { await file.close(); }
  }
  async function check(document, query, token, background = true) {
    const { command, root } = settings(document);
    const request = snapshot(document.uri.fsPath, root, documents().map(item => ({ filename: item.uri.fsPath, text: item.getText() })));
    if (query) request.query = query;
    const result = await invoke(command, ['check-editor'], request, root, 10000, background, token);
    const report = result.payload;
    if (report.kind !== 'gwt.native-editor-check' || report.schemaVersion !== 1 || typeof report.ok !== 'boolean' || (report.ok && result.exitCode !== 0) || !Array.isArray(report.requests) || !Array.isArray(report.scenarios)) throw new Error('Selected executable does not support the native editor-check protocol.');
    for (const [relative, hash] of Object.entries(report.checkedSources)) {
      const filename = path.resolve(root, relative);
      if (!inside(root, filename) || digest(await sourceText(filename)) !== hash) return { stale: true };
    }
    if (report.ok) return { report, diagnostics: [] };
    const diagnostic = report.diagnostic;
    let filename = path.resolve(root, diagnostic.span.file);
    if (!inside(root, filename) || report.diagnosticSource === null) filename = document.uri.fsPath;
    const range = report.diagnosticSource === null ? { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } } : byteRange(report.diagnosticSource, diagnostic.span);
    const item = new vscode.Diagnostic(new vscode.Range(range.start.line, range.start.character, range.end.line, range.end.character), diagnostic.message, vscode.DiagnosticSeverity.Error);
    item.code = diagnostic.code; item.source = 'gwt';
    return { report, diagnostics: [{ uri: vscode.Uri.file(filename), diagnostic: item }] };
  }
  async function navigation(document, position, token, definition) {
    const epoch = generation;
    try {
      if (disposed || token.isCancellationRequested) return;
      const { root } = settings(document);
      if (!inside(root, document.uri.fsPath)) return;
      const query = { path: path.relative(root, document.uri.fsPath).split(path.sep).join('/'), byteOffset: byteOffset(document.getText(), document.offsetAt(position)) };
      const checked = await check(document, query, token);
      if (disposed || epoch !== generation || token.isCancellationRequested || checked.stale || !checked.report.ok) return;
      const report = checked.report;
      if (!report.navigation) throw new Error('Selected native executable does not support semantic navigation.');
      const symbols = report.navigation.symbols;
      if (symbols.length === 0) return;
      const range = (source, span) => {
        const value = byteRange(source, span);
        return new vscode.Range(value.start.line, value.start.character, value.end.line, value.end.character);
      };
      if (!definition) {
        const text = new vscode.MarkdownString();
        // Language source is plain text, never trusted Markdown or command links.
        for (const symbol of symbols) text.appendText(`${symbol.label}\n${symbol.context}\n\n`);
        if (report.navigation.truncated) text.appendText('Additional expanded contexts omitted.');
        return new vscode.Hover(text, range(document.getText(), symbols[0].span));
      }
      const locations = [];
      for (const symbol of symbols) {
        const span = symbol.definition;
        if (!span) continue;
        const filename = path.resolve(root, span.file);
        if (!inside(root, filename)) continue;
        const source = await sourceText(filename);
        if (digest(source) !== report.checkedSources[span.file]) return;
        const uri = vscode.Uri.file(filename);
        const target = range(source, span);
        if (!locations.some(item => item.uri.toString() === uri.toString() && item.range.isEqual(target))) locations.push(new vscode.Location(uri, target));
      }
      if (disposed || epoch !== generation || token.isCancellationRequested) return;
      return locations;
    } catch (error) {
      if (!disposed && epoch === generation && !token.isCancellationRequested) output.appendLine(`Native navigation: ${error.message}`);
    }
  }
  async function completion(document, position, token) {
    const epoch = generation, version = document.version;
    const source = document.getText();
    try {
      if (disposed || token.isCancellationRequested) return [];
      const { command, root } = settings(document);
      if (!inside(root, document.uri.fsPath)) return [];
      const request = snapshot(document.uri.fsPath, root, documents().map(item => ({ filename: item.uri.fsPath, text: item.getText() })));
      request.query = { path: path.relative(root, document.uri.fsPath).split(path.sep).join('/'), byteOffset: byteOffset(source, document.offsetAt(position)) };
      const result = await invoke(command, ['complete-editor'], request, root, 10000, true, token);
      const report = result.payload;
      if (report.kind !== 'gwt.native-completion' || report.schemaVersion !== 1 || report.basis !== 'declarations' || !Array.isArray(report.items)) throw new Error('Selected executable does not support native declaration completion.');
      if (!report.ok || result.exitCode !== 0 || !report.replacement) return [];
      for (const [relative, hash] of Object.entries(report.checkedSources)) {
        const filename = path.resolve(root, relative);
        if (!inside(root, filename) || digest(await sourceText(filename)) !== hash) return [];
      }
      if (disposed || epoch !== generation || token.isCancellationRequested || document.version !== version) return [];
      const replacement = byteRange(source, report.replacement);
      const range = new vscode.Range(replacement.start.line, replacement.start.character, replacement.end.line, replacement.end.character);
      const kinds = { behavior: vscode.CompletionItemKind.Function, request: vscode.CompletionItemKind.Interface, type: vscode.CompletionItemKind.Class };
      const items = report.items.map(item => {
        if (!Object.hasOwn(kinds, item.kind)) throw new Error('Unknown native completion kind.');
        const suggestion = new vscode.CompletionItem(item.label, kinds[item.kind]);
        suggestion.range = range;
        suggestion.detail = item.definition ? `Declared in ${item.definition.file}` : 'Native built-in type';
        suggestion.documentation = new vscode.MarkdownString().appendText(item.detail);
        if (item.kind === 'behavior') {
          const snippet = new vscode.SnippetString();
          let offset = 0;
          for (const match of item.insertText.matchAll(/<([A-Za-z_][A-Za-z_0-9]*)>/g)) {
            snippet.appendText(item.insertText.slice(offset, match.index));
            snippet.appendPlaceholder(match[1]);
            offset = match.index + match[0].length;
          }
          snippet.appendText(item.insertText.slice(offset));
          suggestion.insertText = snippet;
        } else suggestion.insertText = item.insertText;
        return suggestion;
      });
      return new vscode.CompletionList(items, report.truncated);
    } catch (error) {
      if (!disposed && epoch === generation && !token.isCancellationRequested) output.appendLine(`Native completion: ${error.message}`);
      return [];
    }
  }
  async function outline(document, token) {
    const version = document.version;
    const source = document.getText();
    try {
      if (disposed || token.isCancellationRequested) return [];
      const { command, root } = settings(document);
      const result = await invoke(command, ['outline-editor'], { file: document.uri.fsPath || document.uri.toString(), text: source }, root, 10000, false, token);
      const report = result.payload;
      if (disposed || token.isCancellationRequested || document.version !== version) return [];
      if (report.kind !== 'gwt.native-outline' || report.schemaVersion !== 1 || report.sourceDigest !== digest(source)) throw new Error('Selected executable does not support the native outline protocol.');
      if (!report.ok || result.exitCode !== 0) return [];
      const kinds = { program: vscode.SymbolKind.Module, record: vscode.SymbolKind.Struct,
        type: vscode.SymbolKind.TypeParameter, field: vscode.SymbolKind.Field,
        behavior: vscode.SymbolKind.Function, request: vscode.SymbolKind.Interface,
        scenario: vscode.SymbolKind.Event, background: vscode.SymbolKind.Namespace,
        examples: vscode.SymbolKind.Array };
      const range = span => {
        const value = byteRange(source, span);
        return new vscode.Range(value.start.line, value.start.character, value.end.line, value.end.character);
      };
      const convert = item => {
        if (!Object.hasOwn(kinds, item.kind)) throw new Error('Unknown native outline symbol kind.');
        const symbol = new vscode.DocumentSymbol(item.name, item.kind, kinds[item.kind], range(item.range), range(item.selectionRange));
        symbol.children = item.children.map(convert);
        return symbol;
      };
      return report.symbols.map(convert);
    } catch (error) {
      if (!disposed && !token.isCancellationRequested && document.version === version) output.appendLine(`Native outline: ${error.message}`);
      return [];
    }
  }
  async function format(document, token) {
    const version = document.version;
    const source = document.getText();
    try {
      if (disposed || token.isCancellationRequested) return [];
      const { command, root } = settings(document);
      const result = await invoke(command, ['format-editor'], { file: document.uri.fsPath || document.uri.toString(), text: source }, root, 10000, false, token);
      const report = result.payload;
      if (disposed || token.isCancellationRequested || document.version !== version) return [];
      if (report.kind !== 'gwt.native-format' || report.schemaVersion !== 1 || report.sourceDigest !== digest(source)) throw new Error('Selected executable does not support the native formatter protocol.');
      if (!report.ok || result.exitCode !== 0) throw new Error(report.diagnostic?.message || 'Native formatting failed.');
      if (typeof report.text !== 'string') throw new Error('Native formatter returned invalid source.');
      if (report.text === source) return [];
      return [vscode.TextEdit.replace(new vscode.Range(document.positionAt(0), document.positionAt(source.length)), report.text)];
    } catch (error) {
      if (!disposed && !token.isCancellationRequested && document.version === version) {
        output.appendLine(`Native format: ${error.message}`);
        vscode.window.showErrorMessage(`Native format: ${error.message}`);
      }
      return [];
    }
  }
  function schedule() {
    if (disposed) return;
    generation++;
    clearTimeout(timer);
    for (const job of jobs) if (job.background) job.cancel();
    collection.clear();
    timer = setTimeout(() => refresh(generation), 250);
  }
  async function refresh(epoch) {
    const byFile = new Map();
    for (const document of documents()) {
      if (disposed || epoch !== generation) return;
      try {
        const result = await check(document);
        if (disposed || epoch !== generation) return;
        if (result.stale) { schedule(); return; }
        for (const { uri, diagnostic } of result.diagnostics) {
          const key = uri.toString();
          if (!byFile.has(key)) byFile.set(key, { uri, diagnostics: [] });
          const group = byFile.get(key).diagnostics;
          if (!group.some(item => item.code === diagnostic.code && item.message === diagnostic.message && item.range.isEqual(diagnostic.range))) group.push(diagnostic);
        }
      } catch (error) {
        if (disposed || epoch !== generation) return;
        const diagnostic = new vscode.Diagnostic(new vscode.Range(0, 0, 0, 0), error.message, vscode.DiagnosticSeverity.Error);
        diagnostic.code = 'native_tool'; diagnostic.source = 'gwt';
        byFile.set(document.uri.toString(), { uri: document.uri, diagnostics: [diagnostic] });
        output.appendLine(error.message);
      }
    }
    if (!disposed && epoch === generation) {
      collection.set([...byFile.values()].map(item => [item.uri, item.diagnostics]));
      return { ok: [...byFile.values()].every(item => item.diagnostics.length === 0), checked: documents().length };
    }
  }
  async function execute(subcommand) {
    const document = vscode.window.activeTextEditor?.document;
    if (subcommand === 'format') {
      if (!document || document.languageId !== 'gwt') { vscode.window.showErrorMessage('Open a GWT document first.'); return; }
      return vscode.commands.executeCommand('editor.action.formatDocument');
    }
    if (!document || document.languageId !== 'gwt' || document.uri.scheme !== 'file') { vscode.window.showErrorMessage('Open a file-backed GWT document first.'); return; }
    if (subcommand === 'check') {
      schedule();
      // A save watcher or a later edit may invalidate an in-flight check. The
      // explicit command waits for a current result, just like live diagnostics.
      while (!disposed) {
        clearTimeout(timer);
        const result = await refresh(generation);
        if (result) return result;
      }
      return;
    }
    // Explicit execution uses saved source; save all open GWT buffers so imports agree.
    for (const item of documents()) if (item.isDirty && !(await item.save())) return;
    const { command: executable, root, limitsFile } = settings(document, true);
    let args = [subcommand, document.uri.fsPath];
    if (subcommand === 'run' || subcommand === 'profile') {
      // Save notifications may arrive after save() resolves. They should cancel
      // background diagnostics, not the check required by this explicit Run.
      // Source digests still reject an edit made while the check is running.
      const checked = await check(document, undefined, undefined, false);
      if (checked.stale || !checked.report.ok) { schedule(); return; }
      // A complete single-scenario entry already supplies its inputs and calls.
      // Use the CLI's unambiguous entry selection; otherwise ask for a target.
      if (checked.report.scenarios.length !== 1) {
        const options = [...checked.report.scenarios.map(name => ({ label: name, description: 'Scenario', kind: 'scenario' })), ...checked.report.requests.map(name => ({ label: name, description: 'Request', kind: 'request' }))];
        const selected = await vscode.window.showQuickPick(options, { placeHolder: `Select the scenario or request to ${subcommand}` });
        if (!selected) return;
        args.push(`--${selected.kind}`, selected.label);
        if (selected.kind === 'request') {
          const input = await vscode.window.showOpenDialog({ canSelectMany: false, filters: { 'JSON input': ['json'] }, title: 'Select request input' });
          if (!input?.length) return;
          args.push('--input', input[0].fsPath);
        }
      }
    }
    args.push('--import-root', root);
    if (limitsFile) {
      const limitsDocument = vscode.workspace.textDocuments.find(item => item.uri.scheme === 'file' && path.resolve(item.uri.fsPath) === limitsFile);
      if (limitsDocument?.isDirty && !(await limitsDocument.save())) return;
      args.push('--limits', limitsFile);
    }
    output.show(true);
    output.appendLine(`Native GWT: ${subcommand} ${document.uri.fsPath}`);
    output.appendLine(`Execution limits: ${limitsFile || 'native defaults'}`);
    try {
      const result = await invoke(executable, args, undefined, root, 30000, false);
      output.append(result.stdout); // Preserve exact integer tokens; never reserialize through JS numbers.
      if (result.stderr) output.append(result.stderr);
      const evidenceWarnings = subcommand === 'validate' && Array.isArray(result.payload.warnings) ? result.payload.warnings : [];
      for (const warning of evidenceWarnings) output.appendLine(`Validation evidence: ${warning.message}`);
      if (result.exitCode === 0 && result.payload.ok === true && evidenceWarnings.length) vscode.window.showWarningMessage('Native GWT validation passed with evidence gaps. See the GWT output channel.');
      else if (result.exitCode === 0 && result.payload.ok === true) vscode.window.showInformationMessage(`Native GWT ${subcommand} passed.`);
      else vscode.window.showErrorMessage(`Native GWT ${subcommand} failed. See the GWT output channel.`);
      return { ok: result.exitCode === 0 && result.payload.ok === true, exitCode: result.exitCode, stdout: result.stdout };
    } catch (error) { output.appendLine(error.message); vscode.window.showErrorMessage(error.message); return { ok: false }; }
  }
  const watcher = vscode.workspace.createFileSystemWatcher('**/*.gwt');
  context.subscriptions.push(collection, watcher,
    vscode.languages.registerCompletionItemProvider({ scheme: 'file', language: 'gwt' }, {
      provideCompletionItems: (document, position, token) => completion(document, position, token),
    }, ' ', '<'),
    vscode.languages.registerDocumentSymbolProvider([{ scheme: 'file', language: 'gwt' }, { scheme: 'untitled', language: 'gwt' }], {
      provideDocumentSymbols: (document, token) => outline(document, token),
    }),
    vscode.languages.registerDocumentFormattingEditProvider([{ scheme: 'file', language: 'gwt' }, { scheme: 'untitled', language: 'gwt' }], {
      provideDocumentFormattingEdits: (document, _options, token) => format(document, token),
    }),
    vscode.languages.registerHoverProvider({ scheme: 'file', language: 'gwt' }, {
      provideHover: (document, position, token) => navigation(document, position, token, false),
    }),
    vscode.languages.registerDefinitionProvider({ scheme: 'file', language: 'gwt' }, {
      provideDefinition: (document, position, token) => navigation(document, position, token, true),
    }),
    vscode.workspace.onDidOpenTextDocument(document => { if (document.languageId === 'gwt') schedule(); }),
    vscode.workspace.onDidChangeTextDocument(event => { if (event.document.languageId === 'gwt') schedule(); }),
    vscode.workspace.onDidCloseTextDocument(document => { if (document.languageId === 'gwt') schedule(); }),
    watcher.onDidChange(schedule), watcher.onDidCreate(schedule), watcher.onDidDelete(schedule),
    { dispose() { disposed = true; generation++; clearTimeout(timer); for (const job of jobs) job.cancel(); } });
  schedule();
  return { schedule, async command(subcommand) {
    try { return await execute(subcommand); }
    catch (error) { output.appendLine(error.message); vscode.window.showErrorMessage(error.message); return { ok: false }; }
  } };
}
module.exports = { activateNative };
