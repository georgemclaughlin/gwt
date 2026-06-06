import { createGwtProgram } from "@gwtlang/client";
import type { GwtOutputs, GwtRequests } from "../examples/vendor-onboarding.generated.js";

const request = null as unknown as GwtRequests["review vendor"];

const rules = createGwtProgram<GwtRequests, GwtOutputs, "review vendor">({
  file: "examples/vendor_onboarding/rules.gwt",
  request: "review vendor",
});

const execution = await rules.runJson(request);
const status: GwtOutputs["review vendor"]["decision"]["status"] =
  execution.result.decision.status;

await rules.runJson(request, { request: "review vendor" });

// @ts-expect-error request names must come from the generated request map.
await rules.runJson(request, { request: "missing request" });

// @ts-expect-error input must match the selected generated request shape.
await rules.runJson({}, { request: "review vendor" });

interface MultiRequests {
  "first request": {
    first: {
      value: string;
    };
  };
  "second request": {
    second: {
      value: number;
    };
  };
}

interface MultiOutputs {
  "first request": {
    result: {
      status: "first";
    };
  };
  "second request": {
    result: {
      total: number;
    };
  };
}

const narrowedMulti = createGwtProgram<MultiRequests, MultiOutputs, "first request">({
  file: "multi.gwt",
  request: "first request",
});

const firstExecution = await narrowedMulti.runJson({ first: { value: "ok" } });
const firstStatus: "first" = firstExecution.result.result.status;

// @ts-expect-error no-options runJson must use the narrowed default request shape.
await narrowedMulti.runJson({ second: { value: 1 } });

await narrowedMulti.runJson(
  { second: { value: 1 } },
  { request: "second request" },
);

const ambiguousMulti = createGwtProgram<MultiRequests, MultiOutputs>({
  file: "multi.gwt",
  request: "first request",
});

// @ts-expect-error multi-request programs without an explicit default generic require options.request.
await ambiguousMulti.runJson({ first: { value: "ok" } });

const secondExecution = await ambiguousMulti.runJson(
  { second: { value: 1 } },
  { request: "second request" },
);
const secondTotal: number = secondExecution.result.result.total;

// @ts-expect-error explicit request names must match the selected input shape.
await ambiguousMulti.runJson(
  { first: { value: "ok" } },
  { request: "second request" },
);
