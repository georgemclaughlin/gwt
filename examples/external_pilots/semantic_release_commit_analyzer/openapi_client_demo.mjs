#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

import { createHostMatcher, normalizeRelease } from "./host_match_core.mjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptDir, "../../..");
const rulesFile = join(scriptDir, "rules.gwt");
const fixtureFile = join(scriptDir, "conformance_cases.json");
const upstreamCommit = "f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758";
const upstreamRoot = process.argv[2] ? resolve(process.argv[2]) : null;
if (!upstreamRoot) {
  throw new Error("usage: node openapi_client_demo.mjs <pinned-upstream-root>");
}

const actualCommit = captureChecked("git", ["-C", upstreamRoot, "rev-parse", "HEAD"]).trim();
if (actualCommit !== upstreamCommit) {
  throw new Error(`upstream checkout must be pinned at ${upstreamCommit}`);
}

const fixture = JSON.parse(readFileSync(fixtureFile, "utf8"));
const evaluateRules = createHostMatcher(upstreamRoot);
const analyzerUrl = pathToFileURL(join(upstreamRoot, "lib", "analyze-commit.js"));
const { default: analyzeCommit } = await import(analyzerUrl.href);
const httpCases = fixture.cases.map(({ id, commit, rules }) => ({
  id,
  request: { evaluations: evaluateRules(commit, rules) },
  expected: normalizeRelease(analyzeCommit(rules, commit)),
}));

const python = process.env.PYTHON ?? "python";
const npx = process.platform === "win32" ? "npx.cmd" : "npx";
const openapiGeneratorCli = "@openapitools/openapi-generator-cli@2.38.0";
const tsx = "tsx@4.22.4";
const tempDir = mkdtempSync(join(tmpdir(), "gwt-commit-analyzer-openapi-"));
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
  runChecked(
    python,
    ["-m", "gwtlang", "openapi", rulesFile, "--output", openapiPath],
    {},
    { quiet: true },
  );
  assertPilotOperation(JSON.parse(readFileSync(openapiPath, "utf8")));
  console.log(`Generated and verified OpenAPI at ${openapiPath}`);

  runChecked(
    npx,
    [
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
    ],
    {},
    { cwd: tempDir, quiet: true },
  );
  console.log(`Generated TypeScript fetch client at ${generatedClientDir}`);

  writeFileSync(demoPath, demoSource(httpCases), "utf8");
  server = await startGwtServer();
  await waitForHealth(server.baseUrl);
  console.log(`Started gwt serve at ${server.baseUrl}`);

  runChecked(npx, ["--yes", tsx, demoPath], {
    GWT_BASE_URL: server.baseUrl,
  });
} finally {
  if (server) server.process.kill();
  if (process.env.GWT_KEEP_OPENAPI_DEMO !== "1") {
    rmSync(tempDir, { recursive: true, force: true });
  } else {
    console.log(`Kept generated OpenAPI client demo files at ${tempDir}`);
  }
}

function assertPilotOperation(openapi) {
  const route = openapi.paths?.["/requests/select-release-from-evaluated-rules"]?.post;
  if (route?.operationId !== "selectReleaseFromEvaluatedRules") {
    throw new Error("generated OpenAPI is missing the evaluated-rule operation");
  }
  const requestRef = route.requestBody?.content?.["application/json"]?.schema?.$ref;
  if (requestRef !== "#/components/schemas/SelectReleaseFromEvaluatedRulesRequest") {
    throw new Error(`unexpected evaluated-rule request schema: ${requestRef}`);
  }
}

function runChecked(command, args, extraEnv = {}, options = {}) {
  const completed = spawnSync(command, args, {
    cwd: options.cwd ?? repoRoot,
    env: { ...env, ...extraEnv },
    encoding: options.quiet ? "utf8" : undefined,
    stdio: options.quiet ? "pipe" : "inherit",
  });
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    if (options.quiet) {
      if (completed.stdout) process.stderr.write(completed.stdout);
      if (completed.stderr) process.stderr.write(completed.stderr);
    }
    throw new Error(`${command} ${args.join(" ")} exited with ${completed.status}`);
  }
}

function captureChecked(command, args) {
  const completed = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: "utf8",
  });
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    throw new Error(completed.stderr || `${command} exited with ${completed.status}`);
  }
  return completed.stdout;
}

async function startGwtServer() {
  const child = spawn(
    python,
    ["-m", "gwtlang", "serve", rulesFile, "--host", "127.0.0.1", "--port", "0"],
    { cwd: repoRoot, env, stdio: ["ignore", "pipe", "pipe"] },
  );
  const logs = { stderr: "" };
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", chunk => {
    logs.stderr += chunk;
  });
  const readyLine = await firstStdoutLine(child, logs);
  const match = readyLine.match(/(http:\/\/[^\s]+)/);
  if (!match) throw new Error(`could not find service URL in: ${readyLine}`);
  return { process: child, baseUrl: match[1] };
}

async function firstStdoutLine(child, logs) {
  const lines = createInterface({ input: child.stdout });
  const linePromise = new Promise((resolveLine, reject) => {
    lines.once("line", line => {
      lines.close();
      resolveLine(line);
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
      if (response.ok) return;
    } catch {
      // Retry until the service accepts connections.
    }
    await delay(100);
  }
  throw new Error(`gwt serve did not become healthy at ${baseUrl}`);
}

function demoSource(cases) {
  return `import {
  Configuration,
  DefaultApi,
  type SelectReleaseFromEvaluatedRulesOutput,
  type SelectReleaseFromEvaluatedRulesRequest,
} from "./client/index.ts";

type HttpCase = {
  id: string;
  request: SelectReleaseFromEvaluatedRulesRequest;
  expected: string;
};

const cases: HttpCase[] = ${JSON.stringify(cases, null, 2)};

function fromWire(value: string): string | false | null | undefined {
  if (value === "undefined") return undefined;
  if (value === "null") return null;
  if (value === "false") return false;
  return value;
}

async function main(): Promise<void> {
  const api = new DefaultApi(new Configuration({
    basePath: process.env.GWT_BASE_URL ?? "http://127.0.0.1:8080",
  }));

  for (const item of cases) {
    const output: SelectReleaseFromEvaluatedRulesOutput =
      await api.selectReleaseFromEvaluatedRules({
        selectReleaseFromEvaluatedRulesRequest: item.request,
      });
    const actual = fromWire(output.result.release);
    const expected = fromWire(item.expected);
    if (!Object.is(actual, expected)) {
      throw new Error(
        \`${"${item.id}"}: HTTP result ${"${String(actual)}"}, expected ${"${String(expected)}"}\`,
      );
    }
  }

  console.log(\`generated OpenAPI client/gwt serve parity: ${"${cases.length}"}/${"${cases.length}"}\`);
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
`;
}
