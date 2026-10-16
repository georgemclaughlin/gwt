# Readable native request entries

A native request entry is an ordinary GWT program that imports its domain rules,
sets up state, and calls public requests. The dependency belongs in the source:

```gwt
USE "rules.gwt"

GIVEN receipt is Receipt
  lines: []
  total: 0

GIVEN receipt.lines are ReceiptLine
  | sku      | quantity |
  | "widget" | 2        |
  | "gadget" | 4        |

REQUEST summarize receipt
THEN receipt.total == 6
```

This example uses the declarations in `examples/native_setup_tables/rules.gwt`.
The [order-fulfillment entry](../examples/order_fulfillment/native_request.gwt)
is a complete checked-in example using its existing domain rules and ten explicit
expectations. It orders four units, reserves three, backorders one, and charges
an expedited shipping fee of 19.5.

## Execute the entry

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- run examples/order_fulfillment/native_request.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- validate examples/order_fulfillment/native_request.gwt
```

`run ENTRY.gwt` executes its sole scenario. Top-level setup and calls form the
implicit scenario `Main`. A sole named scenario or single expanded `EXAMPLES`
row also works. Zero or multiple scenarios produce a `scenario_selection`
diagnostic before execution. Choose `--scenario NAME` to run one explicitly,
or use `test ENTRY.gwt` to run every entry scenario. Capturing an entry follows
the same selection rule.

Imports provide declarations, not their embedded scenario execution or
background setup. The order entry therefore runs once, rather than also running
the five fulfillment scenarios in `rules.gwt`. Validate the rules file separately
to exercise those scenarios. Every loaded module is parsed and its declarations
checked; validation checks every loaded module's formatting too.

Inputs must satisfy the called request's types. Calls execute in source order,
and their outputs become available to later entry steps. Multiple calls share
the entry's state and execution/evidence budgets. Failure stops that entry unless
an explicit supported failure expectation handles it. Each independent run starts
with fresh state. There is no automatic transaction rollback.

The native run envelope stays unchanged. Entry execution returns the scenario's
complete state in `result` and `state`, including setup bindings. Its top-level
`request` is null because an entry may call several public requests. To return
only one request's declared outputs, keep using the JSON boundary:

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- run examples/order_fulfillment/rules.gwt --request "fulfill order" --input examples/order_fulfillment/request.json
```

`USE` paths resolve relative to the importing module. The default filesystem
root is the entry's parent. For an entry in a subfolder that imports sibling
rules, select a shared ancestor with `--import-root DIRECTORY`. Existing import
path, symlink, depth, module, and source-size limits apply.

## Capture, compare, and review

```sh
target/debug/gwt-native capture examples/order_fulfillment/native_request.gwt > /tmp/gwt-order-entry.case.json
target/debug/gwt-native replay /tmp/gwt-order-entry.case.json
```

A captured entry uses the existing scenario-case format. It freezes the exact
entry and imported sources, the selected scenario, limits, and execution. Replay
does not need the original files. Source evidence points to the original module,
line, and UTF-8 byte range, including Unicode/CRLF inputs; no injected import
line or concatenated source shifts those locations.

Compare a case against the candidate **entry**, with its imports pointing to the
candidate rules. Scenario comparison executes each revision's own setup and
expectations. To isolate a rule change, preserve the entry source and change only
the imported rules. The report distinguishes changed source/evidence from changed
outcomes. It does not silently treat edited input source as the original input.
For comparisons that require invariant host inputs by construction, use a captured
JSON request case instead.

`CompiledProgram::single_scenario()` exposes the same selection rule to Rust
hosts. Pass its returned name to `run_scenario` or `capture_scenario`.
VS Code's native Run command saves open GWT buffers and executes a sole entry
scenario directly; entries with zero or multiple scenarios retain target selection.

## Deliberate boundary

The Python CLI also supports `run RULES.gwt --input REQUEST.gwt`, where the
request file has no import and receives declarations from the command line.
Native entries use explicit `USE` instead. The native `--input` option continues
to mean JSON for `--request NAME`; it does not guess an input language from a file
extension. Existing Python request files remain usable with their Python command.
To make an independent native entry, add the explicit import in a separate file,
as the order example does.

This is source execution using the ordinary GWT grammar, not a new restricted
data-file grammar. Assertions are optional for execution; validation reports
missing scenario expectations as evidence gaps. Rules still need their own
embedded scenarios. The [language tour](../examples/language_tour/README.md) now
uses explicit `FIND ... ELSE` and has its own runnable native entry. Legacy
lowercase `exists`/`find` forms and other remaining native language gaps are not
supplied by this entry workflow.
