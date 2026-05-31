const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function activate(context) {
  const config = vscode.workspace.getConfiguration("gwt");
  const serverOptions = serverOptionsFromConfig(context, config);

  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "gwt" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.gwt"),
    },
  };

  client = new LanguageClient("gwtLanguageServer", "GWT Language Server", serverOptions, clientOptions);
  client.start();
}

function serverOptionsFromConfig(context, config) {
  const configuredCommand = config.get("server.command", "");
  const configuredArgs = config.get("server.args", []);

  if (configuredCommand) {
    return {
      command: configuredCommand,
      args: configuredArgs,
      transport: TransportKind.stdio,
    };
  }

  const repoRoot = path.resolve(context.extensionPath, "..");
  const repoServer = path.join(repoRoot, "gwtlang", "lsp.py");
  if (fs.existsSync(repoServer)) {
    return {
      command: process.env.GWT_PYTHON || "python",
      args: ["-m", "gwtlang", "lsp"],
      transport: TransportKind.stdio,
      options: {
        cwd: repoRoot,
        env: {
          ...process.env,
          PYTHONPATH: [repoRoot, process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
        },
      },
    };
  }

  return {
    command: "gwt",
    args: ["lsp"],
    transport: TransportKind.stdio,
  };
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
