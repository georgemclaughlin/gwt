import path from "node:path";
import { pathToFileURL } from "node:url";

const upstreamRoot = process.argv[2];
if (!upstreamRoot) {
  throw new Error("usage: node upstream_oracle.mjs <upstream-root>");
}

const moduleUrl = pathToFileURL(path.join(upstreamRoot, "lib", "analyze-commit.js"));
const { default: analyzeCommit } = await import(moduleUrl.href);
let inputText = "";
for await (const chunk of process.stdin) inputText += chunk;
const input = JSON.parse(inputText);

function normalizeRelease(value) {
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  if (value === false) return "false";
  return value;
}

const output = input.map(({ id, commit, rules }) => ({
  id,
  release: normalizeRelease(analyzeCommit(rules, commit)),
}));

process.stdout.write(`${JSON.stringify(output)}\n`);
