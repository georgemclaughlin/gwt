#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "../..");
const rulesFile = join(scriptDir, "rules.gwt");
const python = process.env.PYTHON ?? "python";
const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const openapiGeneratorCli = "@openapitools/openapi-generator-cli@2.38.0";
const tsx = "tsx@4.22.4";
const tempDir = mkdtempSync(join(tmpdir(), "gwt-openapi-client-"));
const openapiPath = join(tempDir, "openapi.json");
const generatedClientDir = join(tempDir, "client");
const demoPath = join(tempDir, "demo.ts");

const env = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH
    ? `${repoRoot}${delimiter}${process.env.PYTHONPATH}`
    : repoRoot,
};

let server;
try {
  runChecked(python, [
    "-m",
    "gwtlang",
    "openapi",
    rulesFile,
    "--output",
    openapiPath,
  ], {}, { quiet: true });
  console.log(`Generated OpenAPI at ${openapiPath}`);

  runChecked(npx, [
    "--yes",
    openapiGeneratorCli,
    "generate",
    "-i",
    openapiPath,
    "-g",
    "typescript-fetch",
    "-o",
    generatedClientDir,
    "--additional-properties=supportsES6=true",
    "--global-property=apiDocs=false,modelDocs=false",
  ], {}, { cwd: tempDir, quiet: true });
  console.log(`Generated TypeScript fetch client at ${generatedClientDir}`);

  writeFileSync(demoPath, demoSource(), "utf8");

  server = await startGwtServer();
  await waitForHealth(server.baseUrl);
  console.log(`Started gwt serve at ${server.baseUrl}`);

  runChecked(npx, ["--yes", tsx, demoPath], {
    GWT_BASE_URL: server.baseUrl,
  });
} finally {
  if (server) {
    server.process.kill();
  }
  if (process.env.GWT_KEEP_OPENAPI_DEMO !== "1") {
    rmSync(tempDir, { recursive: true, force: true });
  } else {
    console.log(`Kept generated OpenAPI client demo files at ${tempDir}`);
  }
}

function runChecked(command, args, extraEnv = {}, options = {}) {
  const completed = spawnSync(command, args, {
    cwd: options.cwd ?? repoRoot,
    env: { ...env, ...extraEnv },
    encoding: options.quiet ? "utf8" : undefined,
    stdio: options.quiet ? "pipe" : "inherit",
  });
  if (completed.error) {
    throw completed.error;
  }
  if (completed.status !== 0) {
    if (options.quiet) {
      if (completed.stdout) {
        process.stderr.write(completed.stdout);
      }
      if (completed.stderr) {
        process.stderr.write(completed.stderr);
      }
    }
    throw new Error(`${command} ${args.join(" ")} exited with ${completed.status}`);
  }
}

async function startGwtServer() {
  const child = spawn(
    python,
    [
      "-m",
      "gwtlang",
      "serve",
      rulesFile,
      "--host",
      "127.0.0.1",
      "--port",
      "0",
    ],
    {
      cwd: repoRoot,
      env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  const logs = { stderr: "" };
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", chunk => {
    logs.stderr += chunk;
  });

  const readyLine = await firstStdoutLine(child, logs);
  const match = readyLine.match(/(http:\/\/[^\s]+)/);
  if (!match) {
    throw new Error(`Could not find service URL in: ${readyLine}`);
  }
  return { process: child, baseUrl: match[1] };
}

async function firstStdoutLine(child, logs) {
  const lines = createInterface({ input: child.stdout });
  const linePromise = new Promise((resolve, reject) => {
    lines.once("line", line => {
      lines.close();
      resolve(line);
    });
    child.once("exit", code => {
      reject(new Error(`gwt serve exited before startup with ${code}: ${logs.stderr}`));
    });
    child.once("error", reject);
  });
  const timeout = delay(5000).then(() => {
    throw new Error(`timed out waiting for gwt serve startup: ${logs.stderr}`);
  });
  return await Promise.race([linePromise, timeout]);
}

async function waitForHealth(baseUrl) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(`${baseUrl}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until the server accepts connections.
    }
    await delay(100);
  }
  throw new Error(`gwt serve did not become healthy at ${baseUrl}`);
}

function demoSource() {
  return `import {
  Configuration,
  DefaultApi,
  type TriageTicketOutput,
  type TriageTicketRequest,
} from "./client/index.ts";

async function main(): Promise<void> {
  const api = new DefaultApi(new Configuration({
    basePath: process.env.GWT_BASE_URL ?? "http://127.0.0.1:8080",
  }));

  const request: TriageTicketRequest = {
    ticket: {
      customerId: "C-100",
      subject: "checkout unavailable",
      severity: "medium",
      accountValue: 5000,
      hasOutage: true,
    },
  };

  const result: TriageTicketOutput = await api.triageTicket({
    triageTicketRequest: request,
  });

  if (result.decision.status !== "escalated" || result.decision.queue !== "incident") {
    throw new Error(\`unexpected triage result: \${JSON.stringify(result)}\`);
  }

  console.log(JSON.stringify(result, null, 2));
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
`;
}
