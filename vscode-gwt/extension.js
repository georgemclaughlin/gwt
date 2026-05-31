const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration("gwt");
  const command = config.get("server.command", "gwt");
  const args = config.get("server.args", ["lsp"]);

  const serverOptions = {
    command,
    args,
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "gwt" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.gwt"),
    },
  };

  client = new LanguageClient("gwtLanguageServer", "GWT Language Server", serverOptions, clientOptions);
  client.start();
}

function deactivate() {
  if (!client) {
    return undefined;
  }
  return client.stop();
}

module.exports = {
  activate,
  deactivate,
};
