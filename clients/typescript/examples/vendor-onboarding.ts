import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { GwtClient } from "@gwtlang/client";
import type { GwtOutput, GwtRequest } from "./vendor-onboarding.generated.js";

type VendorDecision = GwtOutput["decision"];

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const rulesFile = path.join(repoRoot, "examples/vendor_onboarding/rules.gwt");
const requestFile = path.join(repoRoot, "examples/vendor_onboarding/request.json");

const request = JSON.parse(await readFile(requestFile, "utf8")) as GwtRequest;
const client = new GwtClient({
  file: rulesFile,
  command: "python",
  commandArgs: ["-m", "gwtlang"],
  cwd: repoRoot,
});

const check = await client.check();
if (!check.ok) {
  throw new Error(JSON.stringify(check.diagnostics, null, 2));
}

const execution = await client.runJson<GwtRequest, GwtOutput>(request, {
  entry: "review vendor into decision",
});

printDecision(request, execution.result.decision);

function printDecision(input: GwtRequest, decision: VendorDecision) {
  const missing = decision.missing_requirements.length
    ? decision.missing_requirements.join(", ")
    : "none";

  console.log(`Vendor: ${input.vendor.vendor_name}`);
  console.log(`Decision: ${decision.status} (${decision.reason})`);
  console.log(`Tier: ${decision.tier}`);
  console.log(`Risk points: ${decision.risk_points}`);
  console.log(`Missing requirements: ${missing}`);
  console.log(
    JSON.stringify(
      {
        documents: {
          required: decision.required_document_count,
          missing: decision.missing_document_count,
          expired: decision.expired_document_count,
        },
        dataReviewRequired: decision.data_review_required,
        reasons: decision.reasons,
      },
      null,
      2,
    ),
  );
}
