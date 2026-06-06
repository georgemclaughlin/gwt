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
    this.stopStack = [];
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
          supportsBreakpointLocationsRequest: true,
        });
        this.sendEvent("initialized");
        break;
      case "setBreakpoints":
        this.setBreakpoints(message);
        break;
      case "breakpointLocations":
        this.breakpointLocations(message);
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
        this.sendResponse(message, this.stackTrace(message));
        break;
      case "scopes":
        this.sendResponse(message, { scopes: this.scopes(message.arguments?.frameId) });
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
    if (breakpoints.length === 0) {
      if (sourcePath) {
        this.breakpoints.set(path.resolve(sourcePath), []);
      }
      this.sendResponse(message, { breakpoints: [] });
      return;
    }

    const validation = this.executableLinesForSource(sourcePath);
    const resolvedBreakpoints = breakpoints.map((breakpoint) =>
      this.resolveBreakpoint(sourcePath, breakpoint.line, validation)
    );
    const lines = resolvedBreakpoints
      .filter((breakpoint) => breakpoint.verified)
      .map((breakpoint) => breakpoint.line);
    if (sourcePath) {
      this.breakpoints.set(path.resolve(sourcePath), lines);
    }
    this.sendResponse(message, {
      breakpoints: resolvedBreakpoints,
    });
  }

  breakpointLocations(message) {
    const sourcePath = message.arguments?.source?.path;
    const startLine = message.arguments?.line || 1;
    const endLine = message.arguments?.endLine || startLine;
    const validation = this.executableLinesForSource(sourcePath);
    if (!validation.lines) {
      this.sendResponse(message, { breakpoints: [] });
      return;
    }

    const breakpoints = [...validation.lines]
      .filter((line) => line >= startLine && line <= endLine)
      .sort((left, right) => left - right)
      .map((line) => ({ line, column: 1 }));
    this.sendResponse(message, { breakpoints });
  }

  executableLinesForSource(sourcePath) {
    if (!sourcePath) {
      return { lines: undefined, message: "Breakpoint source is unavailable." };
    }

    const processOptions = gwtProcessOptions(this.context, path.dirname(sourcePath));
    const commandArgs = [...processOptions.baseArgs, "debug-lines", sourcePath, "--json"];
    const result = childProcess.spawnSync(processOptions.command, commandArgs, {
      cwd: processOptions.cwd,
      env: processOptions.env,
      encoding: "utf8",
      shell: false,
    });

    if (result.error) {
      return { lines: undefined, message: result.error.message };
    }
    if (result.status !== 0) {
      return {
        lines: undefined,
        message: firstLine(result.stderr) || firstLine(result.stdout) || "Could not analyze GWT breakpoints.",
      };
    }

    try {
      const payload = JSON.parse(result.stdout || "{}");
      const resolvedSourcePath = path.resolve(sourcePath);
      const lines = new Set(
        (payload.lines || [])
          .filter((line) => line.file && path.resolve(line.file) === resolvedSourcePath)
          .map((line) => line.line)
      );
      return { lines };
    } catch (error) {
      return { lines: undefined, message: `Could not parse GWT breakpoint analysis: ${error.message}` };
    }
  }

  resolveBreakpoint(sourcePath, line, validation) {
    if (!validation.lines) {
      return {
        verified: false,
        line,
        message: validation.message || "Could not analyze GWT breakpoints.",
      };
    }
    if (validation.lines.has(line)) {
      return { verified: true, line };
    }

    const sourceKind = sourceLineKind(sourcePath, line);
    if (sourceKind === "blank" || sourceKind === "comment") {
      const nextLine = nextExecutableLine(validation.lines, line);
      if (nextLine !== undefined) {
        return {
          verified: true,
          line: nextLine,
          message: "Moved to the next executable GWT line.",
        };
      }
    }

    return {
      verified: false,
      line,
      message: nonExecutableBreakpointMessage(sourceKind),
    };
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
      this.stopStack = this.stackFromStop(message);
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

  stackTrace(message) {
    if (!this.lastStop) {
      return { stackFrames: [], totalFrames: 0 };
    }

    const start = message.arguments?.startFrame || 0;
    const end = message.arguments?.levels ? start + message.arguments.levels : this.stopStack.length;
    const stackFrames = this.stopStack.slice(start, end).map((frame, index) => ({
      id: start + index + 1,
      name: frame.name || frame.text || "GWT",
      source: { name: path.basename(frame.file || ""), path: frame.file },
      line: frame.line || 1,
      column: frame.column || 1,
    }));
    return { stackFrames, totalFrames: this.stopStack.length };
  }

  stackFromStop(message) {
    if (Array.isArray(message.stack) && message.stack.length > 0) {
      return message.stack;
    }
    return [
      {
        name: message.text || "GWT",
        file: message.file,
        line: message.line,
        column: message.column,
        text: message.text,
        locals: message.locals || {},
      },
    ];
  }

  scopes(frameId) {
    if (!this.lastStop) {
      return [];
    }
    const frame = this.stopStack[Math.max(0, (frameId || 1) - 1)] || this.stopStack[0] || {};
    return [
      {
        name: "Locals",
        variablesReference: this.variableHandle(frame.locals || {}),
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

function firstLine(text) {
  return (text || "").split(/\r?\n/).find((line) => line.trim())?.trim();
}

function nextExecutableLine(lines, line) {
  return [...lines]
    .filter((candidate) => candidate > line)
    .sort((left, right) => left - right)[0];
}

function sourceLineKind(sourcePath, line) {
  if (!sourcePath) {
    return "unknown";
  }
  try {
    const lines = fs.readFileSync(sourcePath, "utf8").split(/\r?\n/);
    const text = lines[line - 1] || "";
    const stripped = text.split("#", 1)[0].trim();
    if (!stripped) {
      return text.trim().startsWith("#") ? "comment" : "blank";
    }
    if (stripped === "EXAMPLES" || stripped.startsWith("|")) {
      return "examples";
    }
    if (/^REQUEST\b/.test(stripped)) {
      const nextText = lines[line] || "";
      const hasBody = /^\s{2,}\S/.test(nextText);
      return hasBody ? "declaration" : "unknown";
    }
    if (/^OUTPUT\b/.test(stripped)) {
      return "contract";
    }
    if (/^(PROGRAM|BACKGROUND|SCENARIO|USE|RECORD|DTO)\b/.test(stripped)) {
      return "declaration";
    }
    if (/^THEN returns\b/.test(stripped)) {
      return "contract";
    }
    if (/^(GIVEN|AND)\b/.test(stripped) && /\bis\s+[A-Za-z][A-Za-z0-9_]*$/.test(stripped)) {
      return "contract";
    }
    if (/^WHEN\b/.test(stripped)) {
      const nextText = lines[line] || "";
      const hasBody = /^\s{2,}\S/.test(nextText);
      return hasBody ? "behavior-definition" : "unknown";
    }
    return "unknown";
  } catch (error) {
    return "unknown";
  }
}

function nonExecutableBreakpointMessage(kind) {
  if (kind === "examples") {
    return "EXAMPLES rows are data; set breakpoints on GIVEN, WHEN, THEN, or behavior body lines.";
  }
  if (kind === "declaration") {
    return "Declarations are not executable GWT lines.";
  }
  if (kind === "contract") {
    return "Contracts are metadata; set breakpoints inside behavior bodies or on executable steps.";
  }
  if (kind === "behavior-definition") {
    return "Behavior definitions are not executable; set breakpoints inside the body or on a call.";
  }
  return "No executable GWT statement exists on this line.";
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
