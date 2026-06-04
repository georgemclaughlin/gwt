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
    this.importRoots = normalized.importRoots ?? [];
    this.allowAbsoluteImports = normalized.allowAbsoluteImports ?? true;
  }

  async check(options = {}) {
    const result = await this.#run(["check", this.file, ...this.#importPolicyArgs(options), "--json"], {
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
      [
        "run",
        this.file,
        ...this.#importPolicyArgs(options),
        "--json-input",
        "-",
        "--entry",
        options.entry,
        "--json",
      ],
      {
        ...options,
        input: JSON.stringify(input),
      },
    );
    return parsePayload(result.stdout, result);
  }

  async runRequest(requestFile, options = {}) {
    const result = await this.#run(
      ["run", this.file, ...this.#importPolicyArgs(options), "--input", requestFile, "--json"],
      options,
    );
    return parsePayload(result.stdout, result);
  }

  async test(options = {}) {
    const result = await this.#run(
      ["test", this.file, ...this.#importPolicyArgs(options), "--json"],
      options,
    );
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

  #importPolicyArgs(options = {}) {
    const args = [];
    for (const root of options.importRoots ?? this.importRoots) {
      args.push("--import-root", root);
    }
    if ((options.allowAbsoluteImports ?? this.allowAbsoluteImports) === false) {
      args.push("--no-absolute-imports");
    }
    return args;
  }
}

export class GwtSpec {
  #checkPromises = new Map();

  constructor(options, specOptions = {}) {
    if (options instanceof GwtClient) {
      this.client = options;
      this.entry = specOptions.entry;
      this.checkBeforeRun = specOptions.checkBeforeRun ?? true;
      return;
    }

    const normalized = typeof options === "string" ? { file: options } : { ...options };
    this.client = new GwtClient(normalized);
    this.entry = specOptions.entry ?? normalized.entry;
    this.checkBeforeRun = specOptions.checkBeforeRun ?? normalized.checkBeforeRun ?? true;
  }

  async checkOnce(options = {}) {
    const cacheKey = checkCacheKey(this.client, options);
    let checkPromise = this.#checkPromises.get(cacheKey);
    if (!checkPromise) {
      checkPromise = this.client.check(options).then(check => {
        if (!check.ok) {
          throw new GwtClientError(checkFailedMessage(check), {
            exitCode: 1,
            stdout: JSON.stringify(check, null, 2),
            stderr: diagnosticsMessage(check),
          });
        }
        return check;
      });
      this.#checkPromises.set(cacheKey, checkPromise);
    }
    return checkPromise;
  }

  resetCheck() {
    this.#checkPromises.clear();
  }

  async runJson(input, options = {}) {
    const entry = options.entry ?? this.entry;
    if (!entry) {
      throw new TypeError("GwtSpec.runJson requires an entry behavior");
    }
    if (this.checkBeforeRun) {
      await this.checkOnce(options);
    }
    return this.client.runJson(input, { ...options, entry });
  }

  async runRequest(requestFile, options = {}) {
    if (this.checkBeforeRun) {
      await this.checkOnce(options);
    }
    return this.client.runRequest(requestFile, options);
  }

  async test(options = {}) {
    if (this.checkBeforeRun) {
      await this.checkOnce(options);
    }
    return this.client.test(options);
  }
}

export function createGwtSpec(options, specOptions) {
  return new GwtSpec(options, specOptions);
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

function checkCacheKey(client, options) {
  return JSON.stringify({
    file: client.file,
    command: client.command,
    commandArgs: client.commandArgs,
    cwd: options.cwd ?? client.cwd ?? null,
    env: stableEntries(options.env ?? client.env),
    importRoots: (options.importRoots ?? client.importRoots).map(root => String(root)),
    allowAbsoluteImports: options.allowAbsoluteImports ?? client.allowAbsoluteImports,
  });
}

function stableEntries(record) {
  if (!record) {
    return null;
  }
  return Object.entries(record).sort(([left], [right]) => left.localeCompare(right));
}

function checkFailedMessage(check) {
  const diagnostics = Array.isArray(check.diagnostics) ? check.diagnostics : [];
  const errorCount = diagnostics.filter(diagnostic => diagnostic?.severity === "error").length;
  return `GWT check failed for ${check.file ?? "rules"} with ${errorCount} error(s)`;
}

function diagnosticsMessage(check) {
  const diagnostics = Array.isArray(check.diagnostics) ? check.diagnostics : [];
  return diagnostics
    .filter(diagnostic => diagnostic?.severity === "error")
    .map(diagnostic => diagnostic?.message ?? JSON.stringify(diagnostic))
    .join("\n");
}

function errorMessage(result) {
  const stderr = result.stderr.trim();
  if (stderr) {
    return stderr.split("\n")[0];
  }
  return `gwt exited with code ${result.exitCode}`;
}
