# Inspect native contracts

Use native inspection to discover the contracts in the program you are about to
integrate or change:

```sh
cargo run -p gwt-core --bin gwt-native -- inspect examples/native_early_returns/rules.gwt
```

An installed executable accepts the same `inspect FILE.gwt` command. Add
`--import-root DIRECTORY` when the import root differs from the entry's parent.
Output is JSON; no `--json` flag is needed. Source loading, import resolution,
scenario expansion, and type checking use the same compiled program as execution.
A load/check failure returns the usual diagnostic and exits one. No program,
scenario, initializer, postcondition, or behavior is executed by inspection.

Inspection helps find existing names and contracts. Read the relevant source
bodies and scenarios before making a change, and use `validate`, captured cases,
and review to establish its behavior. Successful inspection does not prove that
an assertion passes, a request returns successfully, or a policy is correct.

## Report

A successful report has `kind: "gwt.native-inspection"`, `schemaVersion: 1`,
and `ok: true`.

| Field | Meaning |
| --- | --- |
| `program` | Optional PROGRAM title |
| `programIdentity` | Identity of the checked source closure, including module paths, hashes, and imports; null for the library's single-string `compile_program` path |
| `types` | Named records and aliases, with the declaration header, fully resolved type, and declaration span |
| `requests` | Named host entry points, caller inputs, required input names, outputs, and source spans |
| `behaviors` | Domain signatures, ordered parameter contracts, optional return contract and its span, and definition span |
| `scenarios` | Entry scenarios after example expansion, original source spans, optional one-based example row/span, and declared expectation counts |

Each input/output/parameter entry has `name`, `type`, and `span`. Spans use
half-open UTF-8 byte offsets and one-based lines/columns, including original
Unicode/CRLF and imported source locations. Requests/behaviors retain compiled
declaration order; named types are ordered by name. The identity describes the
exact frozen closure; inspecting a compiled library object does not reopen files.

Request-local initialized values are not caller inputs. For example, invoice
pricing takes `invoice`; its locally initialized `decision` appears only in
outputs. `requiredInputs` excludes optional inputs, which may be omitted or null.
Successful outputs include every declared output name; an absent optional output
is JSON null. Declared contracts remain unchanged by a branch's local narrowing.

Scenario expectation counts describe compiled top-level scenario/background
expectations, not executed assertions, branch coverage, or behavior-local REQUIRE
steps. Imported scenarios do not become entry scenarios. Example rows are listed
individually, including rows whose assertions would fail when executed.

## Resolved types and host encoding

The `type` field uses the existing native `Type` representation, not JSON Schema:

| Type | Representation |
| --- | --- |
| Primitive | `{"kind":"boolean"}`, `{"kind":"integer"}`, `{"kind":"decimal"}`, or `{"kind":"text"}` |
| Text alternatives | `{"kind":"text_union","value":["new","used"]}` |
| List | `{"kind":"list","value":ITEM_TYPE}` |
| Optional | `{"kind":"optional","value":INNER_TYPE}` |
| Record | `{"kind":"record","value":{"field":FIELD_TYPE}}` |
| One-of | `{"kind":"one_of","value":{"email":{"address":{"kind":"text"}},"phone":{"number":{"kind":"text"}}}}` |

Records are closed: nonoptional fields are required and unknown fields are
rejected. One-of input includes a text `kind` matching a variant key plus that
variant's fields; the automatic discriminator is not repeated in the variant's
field map. Kind-specific aliases resolve to the permitted subset. Aliases are
resolved structurally in contracts while their named declarations remain in
`types`.

Follow the [host encoding rules](native-embedding.md): exact decimal strings,
arbitrary-precision integer tokens, strict booleans, and explicit optional
absence. The report does not encode all language limits as a JSON validator,
execute setup to invent defaults, or summarize behavioral pre/postconditions.
Do not treat it as a replacement for the native input checker or policy source.

## Rust API and bounds

After compilation, `program.inspect()` returns a borrowed `ProgramInspection`
with typed request, parameter, behavior, type, and scenario descriptors. Access
these directly in a Rust host, or call `program.inspect().to_json()?` for the
same bounded report used by the CLI. Borrowing preserves the compiled contracts;
it does not clone or normalize host input.

Normal source/import/type limits apply before inspection. `to_json()` bounds the
complete encoded report to eight MiB. Oversized output returns `inspection_limit`
and no partial report; contracts are never abbreviated or omitted. The CLI emits
that diagnostic with `phase: "inspect"` and exits one. Direct serialization of
the borrowed descriptor is available to library hosts but does not apply this
extra report-size bound. Metadata is versioned independently from run/case
payloads, whose shapes are unchanged.

[Conformance and packaged-host evidence](../evaluations/native_editor/2026-10-16-inspection/README.md)
cover exact host contracts, optional omission, imports/kind aliases, original
locations, failing-but-unexecuted scenarios, deep types, output refusal, and CLI
behavior. Human comprehension benefits remain unmeasured.
