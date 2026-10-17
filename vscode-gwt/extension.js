const vscode = require('vscode');
const path = require('path');
const { runGwt, setting } = require('./native-tools');

let output;
function activate(context) {
  output = vscode.window.createOutputChannel('GWT');
  context.subscriptions.push(output);
  if (!vscode.workspace.isTrusted) return;
  const editor = require('./native-editor').activateNative(vscode, context, output);
  const config = vscode.workspace.getConfiguration('gwt');
  if (config.get('engine') === 'python' || config.get('server.command') || config.get('server.args')?.length) {
    vscode.window.showWarningMessage('GWT now uses the Rust engine. Python engine/server settings are obsolete. Install GWT and set gwt.command if an older Python gwt is on PATH.');
  }
  for (const action of ['check', 'validate', 'test', 'run', 'profile', 'format']) {
    context.subscriptions.push(vscode.commands.registerCommand(`gwt.${action}CurrentFile`, () => editor.command(action)));
  }
  context.subscriptions.push(vscode.commands.registerCommand('gwt.showEngineInfo', showEngineInfo));
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
    if (event.affectsConfiguration('gwt')) editor.schedule();
  }));
}
async function showEngineInfo() {
  const uri = vscode.window.activeTextEditor?.document.uri;
  const folder = (uri && vscode.workspace.getWorkspaceFolder(uri)) || vscode.workspace.workspaceFolders?.[0];
  const config = vscode.workspace.getConfiguration('gwt', uri?.scheme === 'file' ? uri : folder?.uri);
  const command = setting(config, 'command', 'gwt');
  const cwd = folder?.uri.fsPath || (uri?.scheme === 'file' ? path.dirname(uri.fsPath) : undefined);
  output.show(true);
  output.appendLine(`> ${command} version --json`);
  try {
    const result = await runGwt(command, ['version', '--json'], undefined, { cwd }).promise;
    output.append(result.stdout);
    return { ok: true, engine: 'native', ...result };
  } catch (error) {
    output.appendLine(error.message);
    vscode.window.showErrorMessage(error.message);
    return { ok: false, engine: 'native' };
  }
}
function deactivate() {}
module.exports = { activate, deactivate };
