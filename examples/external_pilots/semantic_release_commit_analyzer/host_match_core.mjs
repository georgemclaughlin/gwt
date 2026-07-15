import { createRequire } from "node:module";
import path from "node:path";

const supportedCriteria = new Set(["type", "scope"]);
const ruleMetadata = new Set(["breaking", "revert", "release"]);

export function createHostMatcher(upstreamRoot) {
  const requireFromUpstream = createRequire(path.join(upstreamRoot, "package.json"));
  const micromatch = requireFromUpstream("micromatch");

  function matchesRule(rule, commit) {
    const unsupported = Object.keys(rule).filter(
      (key) => !supportedCriteria.has(key) && !ruleMetadata.has(key)
    );
    if (unsupported.length > 0) {
      throw new Error(`unsupported rule criteria: ${unsupported.join(", ")}`);
    }
    if (rule.breaking && !(commit.notes && commit.notes.length > 0)) return false;
    if (rule.revert && !commit.revert) return false;

    return [...supportedCriteria].every((name) => {
      if (!(name in rule)) return true;
      const expected = rule[name];
      const actual = commit[name];
      if (typeof expected === "string" && typeof actual === "string") {
        return micromatch.isMatch(actual, expected);
      }
      return Object.is(actual, expected);
    });
  }

  return (commit, rules) => rules.map((rule, index) => ({
    id: `rule-${index + 1}`,
    matched: matchesRule(rule, commit),
    release: normalizeRelease(rule.release),
  }));
}

export function normalizeRelease(value) {
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  if (value === false) return "false";
  return value;
}
