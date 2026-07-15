import { createHostMatcher } from "./host_match_core.mjs";

const upstreamRoot = process.argv[2];
if (!upstreamRoot) {
  throw new Error("usage: node host_match_adapter.mjs <upstream-root>");
}

const evaluateRules = createHostMatcher(upstreamRoot);

let inputText = "";
for await (const chunk of process.stdin) inputText += chunk;
const cases = JSON.parse(inputText);

const output = cases.map(({ id, commit, rules }) => ({
  id,
  evaluations: evaluateRules(commit, rules),
}));

process.stdout.write(`${JSON.stringify(output)}\n`);
