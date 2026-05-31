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
    this.breakpoints = new Map();
    this.pendingLaunch = undefined;
    this.configurationDone = false;
    this.lastStop = undefined;
    this.variableHandles = new Map();
    this.nextVariableHandle = 1;
    this.stdoutBuffer = "";
    this.terminated = false;
    this.onDidSendMessageEmitter = new vscode.EventEmitter();
    this.onDidSendMessage = this.onDidSendMessageEmitter.event;
  }

  handleMessage(message) {
    switch (message.command) {
      case "initialize":
        this.sendResponse(message, {
          supportsConfigurationDoneRequest: true,
          supportsTerminateRequest: true,
          supportsStepOverRequest: true,
        });
        this.sendEvent("initialized");
        break;
      case "setBreakpoints":
        this.setBreakpoints(message);
        break;
      case "setExceptionBreakpoints":
        this.sendResponse(message, { breakpoints: [] });
        break;
      case "configurationDone":
        this.configurationDone = true;
        this.sendResponse(message);
        this.startPendingLaunch();
        break;
      case "launch":
        this.pendingLaunch = message;
        this.sendResponse(message);
        this.startPendingLaunch();
        break;
      case "continue":
        this.sendDebugCommand("continue");
        this.sendResponse(message, { allThreadsContinued: true });
        break;
      case "next":
        this.sendDebugCommand("next");
        this.sendResponse(message);
        break;
      case "stackTrace":
        this.sendResponse(message, { stackFrames: this.stackFrames(), totalFrames: this.lastStop ? 1 : 0 });
        break;
      case "scopes":
        this.sendResponse(message, { scopes: this.scopes() });
        break;
      case "variables":
        this.sendResponse(message, { variables: this.variables(message.arguments?.variablesReference) });
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

  setBreakpoints(message) {
    const sourcePath = message.arguments?.source?.path;
    const breakpoints = message.arguments?.breakpoints || [];
    const lines = breakpoints.map((breakpoint) => breakpoint.line);
    if (sourcePath) {
      this.breakpoints.set(path.resolve(sourcePath), lines);
    }
    this.sendResponse(message, {
      breakpoints: lines.map((line) => ({ verified: true, line })),
    });
  }

  startPendingLaunch() {
    if (!this.pendingLaunch || !this.configurationDone || this.process) {
      return;
    }
    this.launch(this.pendingLaunch.arguments || {});
  }

  launch(args) {
    const program = normalizeProgramPath(args.program);
    const mode = args.mode === "run" ? "run" : "test";
    const processOptions = gwtProcessOptions(this.context, args.cwd || path.dirname(program));
    const commandArgs = [...processOptions.baseArgs, "debug", program, "--mode", mode];
    for (const [filename, lines] of this.breakpoints.entries()) {
      for (const line of lines) {
        commandArgs.push("--breakpoint", `${filename}:${line}`);
      }
    }

    this.terminated = false;
    this.process = childProcess.spawn(processOptions.command, commandArgs, {
      cwd: processOptions.cwd,
      env: processOptions.env,
      shell: false,
    });

    this.sendEvent("process", {
      name: "gwt",
      systemProcessId: this.process.pid || 0,
      isLocalProcess: true,
      startMethod: "launch",
    });
    this.sendOutput(`> ${processOptions.command} ${commandArgs.join(" ")}\n`);

    this.process.stdout.on("data", (data) => this.handleDebugOutput(data.toString()));
    this.process.stderr.on("data", (data) => this.sendOutput(data.toString(), "stderr"));
    this.process.on("error", (error) => {
      this.sendOutput(`${error.message}\n`, "stderr");
      this.markTerminated(1);
    });
    this.process.on("close", (code) => {
      if (!this.terminated) {
        this.sendOutput(`GWT exited with code ${code ?? 0}\n`, code === 0 ? "stdout" : "stderr");
        this.markTerminated(code ?? 0);
      }
      this.process = undefined;
    });
  }

  handleDebugOutput(chunk) {
    this.stdoutBuffer += chunk;
    while (true) {
      const index = this.stdoutBuffer.indexOf("\n");
      if (index < 0) {
        return;
      }
      const line = this.stdoutBuffer.slice(0, index);
      this.stdoutBuffer = this.stdoutBuffer.slice(index + 1);
      if (!line.trim()) {
        continue;
      }
      try {
        this.handleDebugEvent(JSON.parse(line));
      } catch (error) {
        this.sendOutput(`${line}\n`, "stdout");
      }
    }
  }

  handleDebugEvent(message) {
    if (message.event === "stopped") {
      this.lastStop = message;
      this.resetVariableHandles();
      this.sendOutput(`Stopped at ${message.file}:${message.line}: ${message.text}\n`);
      this.sendEvent("stopped", { reason: message.reason || "breakpoint", threadId: 1, allThreadsStopped: true });
    } else if (message.event === "output") {
      this.sendOutput(message.output || "", message.category || "stdout");
    } else if (message.event === "terminated") {
      const exitCode = message.exitCode || 0;
      this.markTerminated(exitCode);
    }
  }

  markTerminated(exitCode) {
    if (this.terminated) {
      return;
    }
    this.terminated = true;
    this.sendEvent("exited", { exitCode });
    this.sendEvent("terminated");
  }

  sendDebugCommand(command) {
    if (this.process && this.process.stdin.writable) {
      this.process.stdin.write(`${JSON.stringify({ command })}\n`);
    }
  }

  stackFrames() {
    if (!this.lastStop) {
      return [];
    }
    return [
      {
        id: 1,
        name: this.lastStop.text || "GWT",
        source: { name: path.basename(this.lastStop.file || ""), path: this.lastStop.file },
        line: this.lastStop.line || 1,
        column: this.lastStop.column || 1,
      },
    ];
  }

  scopes() {
    if (!this.lastStop) {
      return [];
    }
    return [
      {
        name: "Locals",
        variablesReference: this.variableHandle(this.lastStop.locals || {}),
        expensive: false,
      },
      {
        name: "State",
        variablesReference: this.variableHandle(this.lastStop.state || {}),
        expensive: false,
      },
    ];
  }

  variables(reference) {
    const value = this.variableHandles.get(reference);
    if (value === undefined) {
      return [];
    }
    if (Array.isArray(value)) {
      return value.map((item, index) => this.variable(String(index), item));
    }
    if (value && typeof value === "object") {
      return Object.entries(value).map(([name, item]) => this.variable(name, item));
    }
    return [];
  }

  variable(name, value) {
    const isExpandable = value !== null && typeof value === "object";
    return {
      name,
      value: isExpandable ? collectionLabel(value) : String(value),
      variablesReference: isExpandable ? this.variableHandle(value) : 0,
    };
  }

  variableHandle(value) {
    const handle = this.nextVariableHandle++;
    this.variableHandles.set(handle, value);
    return handle;
  }

  resetVariableHandles() {
    this.variableHandles = new Map();
    this.nextVariableHandle = 1;
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

function collectionLabel(value) {
  if (Array.isArray(value)) {
    return `list[${value.length}]`;
  }
  return "record";
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
