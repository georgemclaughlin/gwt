import { spawn } from "node:child_process";

export class GwtClientError extends Error {
  constructor(message, { exitCode = null, stdout = "", stderr = "" } = {}) {
    super(message);
    this.name = "GwtClientError";
    this.exitCode = exitCode;
    this.stdout = stdout;
    this.stderr = stderr;
  }
}

export class GwtClient {
  constructor(options) {
    const normalized = typeof options === "string" ? { file: options } : { ...options };
    if (!normalized.file) {
      throw new TypeError("GwtClient requires a file path");
    }
    this.file = normalized.file;
    this.command = normalized.command ?? "gwt";
    this.commandArgs = normalized.commandArgs ?? [];
    this.cwd = normalized.cwd;
    this.env = normalized.env;
  }

  async check(options = {}) {
    const result = await this.#run(["check", this.file, "--json"], {
      ...options,
      allowNonZeroJson: true,
    });
    return normalizeCheckPayload(parsePayload(result.stdout, result));
  }

  async runJson(input, options) {
    if (!options?.entry) {
      throw new TypeError("runJson requires an entry behavior");
    }
    const result = await this.#run(
      ["run", this.file, "--json-input", "-", "--entry", options.entry, "--json"],
      {
        ...options,
        input: JSON.stringify(input),
      },
    );
    return parsePayload(result.stdout, result);
  }

  async runRequest(requestFile, options = {}) {
    const result = await this.#run(["run", this.file, "--input", requestFile, "--json"], options);
    return parsePayload(result.stdout, result);
  }

  async #run(args, options = {}) {
    const result = await runProcess(this.command, [...this.commandArgs, ...args], {
      cwd: options.cwd ?? this.cwd,
      env: options.env ?? this.env,
      input: options.input,
    });
    if (result.exitCode !== 0 && !options.allowNonZeroJson) {
      throw new GwtClientError(errorMessage(result), result);
    }
    return result;
  }
}

export async function checkFile(file, options = {}) {
  return new GwtClient({ ...options, file }).check();
}

export async function runFile(file, options) {
  if (!options?.requestFile && (!options?.entry || options.input === undefined)) {
    throw new TypeError("runFile requires either requestFile or input with entry");
  }
  const client = new GwtClient({ ...options, file });
  if (options?.requestFile) {
    return client.runRequest(options.requestFile);
  }
  return client.runJson(options.input, { entry: options.entry });
}

function runProcess(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env ? { ...process.env, ...options.env } : undefined,
      shell: false,
    });
    let stdout = "";
    let stderr = "";

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", chunk => {
      stdout += chunk;
    });
    child.stderr.on("data", chunk => {
      stderr += chunk;
    });
    child.on("error", error => {
      reject(new GwtClientError(error.message, { stdout, stderr }));
    });
    child.on("close", exitCode => {
      resolve({ exitCode, stdout, stderr });
    });

    if (options.input !== undefined) {
      child.stdin.write(options.input);
    }
    child.stdin.end();
  });
}

function parsePayload(raw, result) {
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new GwtClientError(`GWT did not return valid JSON: ${error.message}`, result);
  }
}

function normalizeCheckPayload(payload) {
  if (Object.hasOwn(payload, "ok")) {
    return payload;
  }
  const diagnostics = Array.isArray(payload.diagnostics) ? payload.diagnostics : [];
  return {
    ok: !diagnostics.some(diagnostic => diagnostic?.severity === "error"),
    ...payload,
  };
}

function errorMessage(result) {
  const stderr = result.stderr.trim();
  if (stderr) {
    return stderr.split("\n")[0];
  }
  return `gwt exited with code ${result.exitCode}`;
}
