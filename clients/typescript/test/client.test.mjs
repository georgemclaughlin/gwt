import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { GwtClient, GwtClientError, createGwtSpec, runFile } from "../src/index.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

function repoClient(file) {
  return new GwtClient({
    file,
    command: "python",
    commandArgs: ["-m", "gwtlang"],
    cwd: repoRoot,
  });
}

test("GwtClient checks and runs JSON input", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "checkout.gwt");
  await writeFile(
    file,
    `
RECORD Cart
  subtotal: number
  shipping: number
  total: number

REQUEST cart is Cart
OUTPUT cart is Cart

WHEN checkout <cart>
  GIVEN cart is Cart
  set cart.total to cart.subtotal + cart.shipping
`,
  );

  const client = repoClient(file);
  const check = await client.check();
  const result = await client.runJson(
    { cart: { subtotal: 84, shipping: 8, total: 0 } },
    { entry: "checkout cart" },
  );

  assert.equal(check.ok, true);
  assert.equal(result.result.cart.total, 92);
});

test("GwtClient runs embedded scenarios as JSON", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "scenarios.gwt");
  await writeFile(
    file,
    `
SCENARIO one
GIVEN count is 1
THEN count == 1

SCENARIO two
GIVEN count is 2
THEN count == 2
`,
  );

  const result = await repoClient(file).test();

  assert.equal(result.scenario_count, 2);
  assert.deepEqual(
    result.scenarios.map(scenario => scenario.name),
    ["one", "two"],
  );
});

test("GwtSpec caches check and runs JSON input with a default entry", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "checkout.gwt");
  await writeFile(
    file,
    `
WHEN checkout <cart>
  set cart.total to cart.subtotal + cart.shipping
`,
  );

  const spec = createGwtSpec({
    file,
    command: "python",
    commandArgs: ["-m", "gwtlang"],
    cwd: repoRoot,
    entry: "checkout cart",
  });
  const firstCheck = await spec.checkOnce();
  const secondCheck = await spec.checkOnce();
  const result = await spec.runJson({ cart: { subtotal: 84, shipping: 8, total: 0 } });

  assert.equal(firstCheck, secondCheck);
  assert.equal(result.result.cart.total, 92);
});

test("GwtSpec reports check failures before running", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "checkout.gwt");
  await writeFile(
    file,
    `
WHEN checkout <cart>
  GIVEN cart is MissingCart
  PASS
`,
  );

  const spec = createGwtSpec({
    file,
    command: "python",
    commandArgs: ["-m", "gwtlang"],
    cwd: repoRoot,
    entry: "checkout cart",
  });

  await assert.rejects(
    () => spec.runJson({ cart: {} }),
    error => {
      assert.equal(error instanceof GwtClientError, true);
      assert.match(error.message, /GWT check failed/);
      assert.match(error.stderr, /unknown contract type: MissingCart/);
      return true;
    },
  );
});

test("GwtSpec preflight check uses per-call import policy options", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const moduleFile = path.join(dir, "steps.gwt");
  const file = path.join(dir, "workflow.gwt");
  await writeFile(
    moduleFile,
    `
WHEN touch <count>
  add 1 to count
`,
  );
  await writeFile(
    file,
    `
USE "${moduleFile}"
`,
  );

  const spec = createGwtSpec({
    file,
    command: "python",
    commandArgs: ["-m", "gwtlang"],
    cwd: repoRoot,
    entry: "touch count",
  });
  const defaultCheck = await spec.checkOnce();

  assert.equal(defaultCheck.ok, true);
  await assert.rejects(
    () => spec.runJson({ count: 1 }, { allowAbsoluteImports: false }),
    error => {
      assert.equal(error instanceof GwtClientError, true);
      assert.match(error.message, /GWT check failed/);
      assert.match(error.stderr, /USE absolute import is not allowed/);
      return true;
    },
  );
});

test("runFile helper can run JSON input with the same runner options", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "checkout.gwt");
  await writeFile(
    file,
    `
WHEN checkout <cart>
  set cart.total to cart.subtotal + cart.shipping
`,
  );

  const result = await runFile(file, {
    command: "python",
    commandArgs: ["-m", "gwtlang"],
    cwd: repoRoot,
    input: { cart: { subtotal: 84, shipping: 8, total: 0 } },
    entry: "checkout cart",
  });

  assert.equal(result.result.cart.total, 92);
});

test("runFile helper can run a GWT request file", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "checkout.gwt");
  const requestFile = path.join(dir, "request.gwt");
  await writeFile(
    file,
    `
WHEN checkout cart
  set cart.total to cart.subtotal + cart.shipping
`,
  );
  await writeFile(
    requestFile,
    `
GIVEN cart.subtotal is 84
AND cart.shipping is 8

WHEN checkout cart
`,
  );

  const result = await runFile(file, {
    command: "python",
    commandArgs: ["-m", "gwtlang"],
    cwd: repoRoot,
    requestFile,
  });

  assert.equal(result.result.cart.total, 92);
});

test("runFile helper requires either requestFile or input with entry", async () => {
  await assert.rejects(
    () => runFile("rules.gwt", {}),
    error => {
      assert.equal(error instanceof TypeError, true);
      assert.match(error.message, /requires either requestFile or input with entry/);
      return true;
    },
  );
});

test("runJson exposes GWT failures as client errors", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "gwt-client-"));
  const file = path.join(dir, "checkout.gwt");
  await writeFile(
    file,
    `
RECORD Cart
  subtotal: number

REQUEST cart is Cart

WHEN checkout <cart>
  GIVEN cart is Cart
  PASS
`,
  );

  const client = repoClient(file);

  await assert.rejects(
    () => client.runJson({}, { entry: "checkout cart" }),
    error => {
      assert.equal(error instanceof GwtClientError, true);
      assert.equal(error.exitCode, 1);
      assert.match(error.stderr, /REQUEST contract failed for cart/);
      return true;
    },
  );
});
