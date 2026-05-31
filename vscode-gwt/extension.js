const vscode = require("vscode");
const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;
let debugFactory;

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

  debugFactory = new GwtDebugAdapterFactory(context);
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory("gwt", debugFactory));
  context.subscriptions.push(vscode.debug.registerDebugConfigurationProvider("gwt", new GwtDebugConfigurationProvider()));
  context.subscriptions.push(
    vscode.commands.registerCommand("gwt.debugCurrentFile", () => debugCurrentFile())
  );
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

function repoRootFromContext(context) {
  const repoRoot = path.resolve(context.extensionPath, "..");
  if (fs.existsSync(path.join(repoRoot, "gwtlang", "__main__.py"))) {
    return repoRoot;
  }
  return undefined;
}

function gwtProcessOptions(context, cwd) {
  const repoRoot = repoRootFromContext(context);
  if (repoRoot) {
    return {
      command: process.env.GWT_PYTHON || "python",
      baseArgs: ["-m", "gwtlang"],
      cwd: cwd || repoRoot,
      env: {
        ...process.env,
        PYTHONPATH: [repoRoot, process.env.PYTHONPATH || ""].filter(Boolean).join(path.delimiter),
      },
    };
  }

  return {
    command: "gwt",
    baseArgs: [],
    cwd: cwd || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
    env: process.env,
  };
}

class GwtDebugConfigurationProvider {
  provideDebugConfigurations() {
    return [defaultDebugConfiguration()];
  }

  resolveDebugConfiguration(folder, config) {
    const resolved = { ...defaultDebugConfiguration(), ...config };
    if (!resolved.program) {
      const editor = vscode.window.activeTextEditor;
      if (editor && editor.document.languageId === "gwt") {
        resolved.program = editor.document.uri.fsPath;
      }
    }
    if (!resolved.program) {
      vscode.window.showErrorMessage("Open a .gwt file before starting the GWT debugger.");
      return undefined;
    }
    if (!resolved.cwd) {
      resolved.cwd = folder?.uri.fsPath || path.dirname(resolved.program);
    }
    return resolved;
  }
}

function defaultDebugConfiguration() {
  return {
    type: "gwt",
    request: "launch",
    name: "Debug Current GWT File",
    program: "${file}",
    mode: "test",
    json: false,
  };
}

function debugCurrentFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "gwt") {
    vscode.window.showErrorMessage("Open a .gwt file before starting the GWT debugger.");
    return;
  }
  const folder = vscode.workspace.getWorkspaceFolder(editor.document.uri);
  vscode.debug.startDebugging(folder, {
    ...defaultDebugConfiguration(),
    program: editor.document.uri.fsPath,
    cwd: folder?.uri.fsPath || path.dirname(editor.document.uri.fsPath),
  });
}

class GwtDebugAdapterFactory {
  constructor(context) {
    this.context = context;
  }

  createDebugAdapterDescriptor() {
    return new vscode.DebugAdapterInlineImplementation(new GwtDebugAdapter(this.context));
  }
}

class GwtDebugAdapter {
  constructor(context) {
    this.context = context;
    this.seq = 1;
    this.process = undefined;
    this.onDidSendMessageEmitter = new vscode.EventEmitter();
    this.onDidSendMessage = this.onDidSendMessageEmitter.event;
  }

  handleMessage(message) {
    switch (message.command) {
      case "initialize":
        this.sendResponse(message, {
          supportsConfigurationDoneRequest: false,
          supportsTerminateRequest: true,
        });
        this.sendEvent("initialized");
        break;
      case "launch":
        this.launch(message);
        break;
      case "disconnect":
      case "terminate":
        this.stopProcess();
        this.sendResponse(message);
        this.sendEvent("terminated");
        break;
      case "threads":
        this.sendResponse(message, { threads: [{ id: 1, name: "GWT" }] });
        break;
      default:
        this.sendResponse(message);
        break;
    }
  }

  launch(message) {
    const args = message.arguments || {};
    const program = normalizeProgramPath(args.program);
    const mode = args.mode === "run" ? "run" : "test";
    const processOptions = gwtProcessOptions(this.context, args.cwd || path.dirname(program));
    const commandArgs = [...processOptions.baseArgs, mode, program];
    if (args.json) {
      commandArgs.push("--json");
    }

    this.process = childProcess.spawn(processOptions.command, commandArgs, {
      cwd: processOptions.cwd,
      env: processOptions.env,
      shell: false,
    });

    this.sendResponse(message);
    this.sendEvent("process", {
      name: "gwt",
      systemProcessId: this.process.pid || 0,
      isLocalProcess: true,
      startMethod: "launch",
    });
    this.sendOutput(`> ${processOptions.command} ${commandArgs.join(" ")}\n`);

    this.process.stdout.on("data", (data) => this.sendOutput(data.toString(), "stdout"));
    this.process.stderr.on("data", (data) => this.sendOutput(data.toString(), "stderr"));
    this.process.on("error", (error) => {
      this.sendOutput(`${error.message}\n`, "stderr");
      this.sendEvent("terminated");
    });
    this.process.on("close", (code) => {
      this.sendOutput(`GWT exited with code ${code ?? 0}\n`, code === 0 ? "stdout" : "stderr");
      this.sendEvent("exited", { exitCode: code ?? 0 });
      this.sendEvent("terminated");
    });
  }

  stopProcess() {
    if (this.process && !this.process.killed) {
      this.process.kill();
    }
  }

  sendOutput(output, category = "console") {
    this.sendEvent("output", { category, output });
  }

  sendResponse(request, body = {}) {
    this.send({
      type: "response",
      request_seq: request.seq,
      success: true,
      command: request.command,
      body,
    });
  }

  sendEvent(event, body = {}) {
    this.send({ type: "event", event, body });
  }

  send(message) {
    this.onDidSendMessageEmitter.fire({ seq: this.seq++, ...message });
  }

  dispose() {
    this.stopProcess();
    this.onDidSendMessageEmitter.dispose();
  }
}

function normalizeProgramPath(program) {
  if (program && program !== "${file}") {
    return program;
  }
  const editor = vscode.window.activeTextEditor;
  if (editor) {
    return editor.document.uri.fsPath;
  }
  return program;
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
