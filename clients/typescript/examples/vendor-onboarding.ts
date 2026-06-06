import path from "node:path";
import { fileURLToPath } from "node:url";

import { createGwtProgram } from "@gwtlang/client";
import type { GwtOutputs, GwtRequests } from "./vendor-onboarding.generated.js";

type ReviewVendorRequest = GwtRequests["review vendor"];
type VendorDecision = GwtOutputs["review vendor"]["decision"];

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const rulesFile = path.join(repoRoot, "examples/vendor_onboarding/rules.gwt");

const payload: ReviewVendorRequest = {
  vendor: {
    vendor_name: "Cloud Ledger",
    country: "US",
    annual_spend: 125000,
    handles_customer_data: true,
    stores_payment_data: false,
    documents: [
      { name: "tax_form", status: "provided" },
      { name: "insurance", status: "expired" },
      { name: "security_questionnaire", status: "missing" },
    ],
    risk_signals: [
      { name: "new_vendor", severity: "low", points: 1 },
      { name: "data_region", severity: "medium", points: 2 },
    ],
  },
};
const rules = createGwtProgram<GwtRequests, GwtOutputs, "review vendor">({
  file: rulesFile,
  request: "review vendor",
  command: "python",
  commandArgs: ["-m", "gwtlang"],
  cwd: repoRoot,
});

const execution = await rules.runJson(payload);

printDecision(payload, execution.result.decision);

function printDecision(input: ReviewVendorRequest, decision: VendorDecision) {
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
