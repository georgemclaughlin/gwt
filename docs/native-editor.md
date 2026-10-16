# Native editor integration

GWT's VS Code extension has an explicit Rust mode for live diagnostics and
test/run/validation/profiling commands. Python remains the default. See the [extension setup and
capability table](../vscode-gwt/README.md) before switching engines. This is a
partial editor integration. Native hover and definitions cover resolved calls,
bindings, type references, and declared record fields. Native layout formatting
supports unsaved and untitled buffers, as does the local document outline;
scoped field/local completion, debugging, and broader semantic symbol coverage
remain open.

Native declaration completion suggests behavior signatures, request names, and
type names from the current import closure, including unsaved edits and incomplete
call/type lines. This is distinct from checked semantic navigation; see below.

`gwt.native.limitsFile` selects the [execution budget](native-execution-limits.md)
used by Run, Profile, Test, and Validate. The editor saves the selected file's
dirty buffer before execution and reports missing/malformed settings as command
failures. This resource-scoped setting resolves relative to the active workspace
folder (file parent outside a workspace), independently of the import root.
Changing it applies on the next command. Static snapshot checks, navigation,
outline, and formatting remain independent of execution settings. Profile uses
Run's existing target selection and preserves the CLI's exact output.

## Snapshot checking

`gwt-native check-editor` reads one JSON request from standard input and emits
one JSON response. It loads and checks source without executing behaviors or
scenarios, writing source files, or invoking Python.

From the repository root, this checks a saved native example:

```sh
printf '%s\n' '{"entry":"examples/native_print_expectations/rules.gwt","importRoot":".","documents":[]}' | target/debug/gwt-native check-editor
```

An editor supplies unsaved replacements in `documents`:

```json
{
  "entry": "/project/rules.gwt",
  "importRoot": "/project",
  "documents": [
    {"path": "rules.gwt", "text": "USE \"types.gwt\"\nSCENARIO example\nTHEN true\n"},
    {"path": "types.gwt", "text": "TYPE Amount is integer\n"}
  ]
}
```

The entry and optional root resolve against the process working directory.
Without a root, the entry's parent is used. Document paths are canonical relative
paths using `/`. Absolute paths, traversal, duplicate document paths, and unknown
request fields are refused. A replacement may represent a file that has never
been saved. Existing symlinks below the selected root remain forbidden, and an
existing directory cannot be replaced with source text. The loader is not a
sandbox against concurrent filesystem changes.

The encoded request is limited to eight MiB; source replacements are limited to
256 documents, one MiB each, and four MiB in total. The normal native import
closure, syntax nesting, and node limits also apply. Valid but unreachable
replacements do not affect program identity. All replacement paths and bounds
are validated even if the entry does not import them.

## Response and source locations

Responses have `kind: "gwt.native-editor-check"`, `schemaVersion: 1`, and:

| Field | Meaning |
| --- | --- |
| `ok` | Source loaded and compiled successfully; scenario assertions have not been executed |
| `requests`, `scenarios` | Names from the compiled program, empty when source loading/checking fails |
| `programIdentity` | Identity of the exact compiled source closure, or null when source loading/checking fails |
| `diagnostic` | First load/parse/type error, or null on success |
| `diagnosticSource` | Exact source text for the error span, or null when unavailable |
| `checkedSources` | Portable source paths mapped to SHA-256 hashes of the exact UTF-8 text read, including text read before failure |

Exit zero indicates successful checking; a source error returns the response
with exit one. Malformed or oversized protocol input is rejected on stderr and
does not produce a successful response. Callers must distinguish protocol/process
errors from source diagnostics.

The Rust library exposes `check_editor` and `EditorCheck` for the same operation.
Byte spans refer to `diagnosticSource`, including its original line endings.
The VS Code adapter converts UTF-8 offsets to UTF-16 positions and rejects
invalid boundaries. When no source is available, an error attaches to the
entry's start. Imported-source errors attach to the imported document.

## Semantic hover and definitions

An optional `query` adds semantic navigation to a snapshot check:

```json
{"path": "rules.gwt", "byteOffset": 42}
```

The path must identify a module actually read in the entry's closure. The offset
must be a UTF-8 character boundary in that exact source; end-of-file is permitted
and has no symbol. Invalid queries return `editor_query`. Source failures retain
their ordinary diagnostics and produce no navigation. The library equivalent
is `check_editor_query` with an optional `EditorQuery`.

An invalid query after successful compilation retains the program names and
identity, while setting `ok` to false and returning the query diagnostic.

A successful query adds `navigation` with `symbols` and `truncated`. Each symbol
has `kind`, a plain-text `label`, a `context`, its source `span`, and an optional
`definition` span. The smallest containing semantic source spans win. Exact
duplicate results are removed; table-expanded scenarios retain distinct context
names, up to 64 matches. Labels are bounded to 4096 UTF-8 bytes plus an ellipsis,
contexts to 512, and structural type descriptions to 1024. The existing schema
version remains one because this is an optional additive request/response field.

Behavior and request calls use the compiler's resolved target IDs. Variable
reads and mutations use resolved binding slots within each behavior, request,
or scenario. This distinguishes same-named locals in separate branches and
behaviors. Returning calls, traversal variables, aggregate projections, expected
failures, and implicit request outputs retain their actual declaration sites.
Implicit outputs point to the request call that introduces them. Within a field
path, selecting the root name navigates to its binding; selecting a field name
navigates to the field declaration when its type origin is known. Hover uses
the checked type of the selected component.

The compiler retains exact type-annotation locations separately from its
structural types. Named references in contracts, aliases, fields, and nested
`list<...>`/`optional<...>` annotations navigate to their declarations. Field
navigation follows aliases, nested records, copied locals, declared return
contracts, request outputs, traversal variables, and aggregate projections.
Separate `EXAMPLES` rows retain their own compiled type-annotation ranges.
Two records with equal shapes therefore do not become interchangeable
navigation targets.

This is declaration provenance, not a trace of runtime value history.
Kind-refined payload expressions retain the checker-selected kinds at each
path prefix. When one kind is known, field lookup follows that kind in the
binding's original declaration, including through aliases, optional ancestors,
nested one-of records, copied payloads, and collection items. This applies to
reads, mutation destinations, and shared arguments inside `IF`, `DECIDE`,
short-circuit expressions, and `DEPENDING ON`. Root selections still navigate
to the binding; selected fields navigate to their declarations. Explicit
selected-kind contracts retain their declared payload origins.

A field common to several remaining kinds still has several declaration sites.
Navigation falls back to the known binding instead of arbitrarily choosing one.
Equal structural shapes or identical field names do not identify declarations.
Each `EXAMPLES` row retains its own checked kind choices and navigation context;
a shared template path can therefore return distinct valid field targets. An
inferred list containing values from different record declarations has no
single declared field origin. In that case navigation falls back to the root
binding rather than choosing one record. Grouped or substituted source spans
that cannot identify an exact component also retain their mapped binding site.
Quoted text that happens to equal a type name is not a type reference.

Hover also describes checked type and field declarations and behavior
signatures/contracts. Navigation requires the
complete checked closure to compile; no old successful index is reused for
invalid edits. These metadata additions do not change execution, structural
type compatibility, or diagnostic locations.

[Common branch-exit proofs](native-branch-proofs.md) also refine later source
paths. When every continuing branch establishes the same optional payload kind,
hover/definitions can use that payload declaration afterward. Removing a proof
from one continuing branch restores the ordinary unsafe-path diagnostic. The
[branch-proof checkpoint](../evaluations/native_editor/2026-10-16-branch-proofs/README.md)
checks this with unsaved imported types in the installed extension host.

VS Code converts its UTF-16 cursor position to a UTF-8 offset, checks source
hashes before using results, and rechecks definition targets before returning
locations. Edits and cancellation invalidate in-flight navigation. Hover text
uses untrusted plain text rather than interpreting source as Markdown or command
links. An older native executable without query support does not trigger Python
fallback.

## Declaration completion

`gwt-native complete-editor` accepts the same snapshot request as `check-editor`,
with a required `query`. The library exports `complete_editor`,
`EditorCompletion`, and `CompletionItem`. It loads the current import closure and
indexes source declarations without executing or type-checking behavior bodies.
Incomplete calls and unknown type names can therefore receive suggestions while
ordinary diagnostics still report that the source does not compile.

Supported positions are:

- a scenario/request `WHEN` call or a behavior-body call;
- a whole-call `LET name be ...`, including scenario `WHEN LET`, restricted to
  behaviors declaring `THEN returns`;
- a root `REQUEST` invocation;
- type-name positions in `GIVEN`, `AND`, `OUTPUT`, aliases, record fields, and
  return contracts, including nested `list<...>` and `optional<...>` names.

Suggestions match the typed source prefix and carry declared contracts. Behavior
parameters become editable snippet tab stops. This does not select argument
bindings, guarantee type compatibility, or infer runtime values. Field paths,
local names, built-in step templates, selected-kind names, and general expression
completion are not provided. Suggestions are suppressed in quoted text, comments,
ordinary expression positions, and recognized behavior declaration headers.
Call suggestions do not overwrite an existing argument tail. Duplicate type,
request, or canonical behavior declarations are omitted rather than guessed.

Responses use `kind: "gwt.native-completion"`, `schemaVersion: 1`, and
`basis: "declarations"`. `ok` means indexing succeeded, not compilation or scenario
success. `items` contain `kind`, `label`, `insertText`, plain `detail`,
`returnsValue`, and an optional declaration `definition` span. `replacement` is
the exact UTF-8 source range to replace, or null outside a supported position.
`checkedSources` hashes the original texts read; `diagnostic` reports a load,
layout, or query failure. Such failures produce no suggestions. A successful
empty list is normal. No compiled program identity is claimed.

The existing snapshot/import limits apply. Responses retain at most 128 matches
in deterministic declaration-key order and set `truncated` when more match.
Declaration labels over 1024 bytes are omitted; detail is limited to 4096 bytes.
Invalid/unreachable query paths and non-UTF-8 offsets are rejected. Layout and
import failures stop indexing; it is not arbitrary syntax recovery. No previous
successful declaration index is reused.

VS Code supports file-backed buffers, rechecks every loaded source hash, and
discards cancelled responses or results made stale by edits/configuration changes.
It converts editor positions through UTF-16 offsets before forming UTF-8 queries.
Source documentation is appended as plain text, and snippet text/parameters use
the editor's escaping APIs. Completion neither saves files nor executes rules.
Older native executables without this command produce no native suggestions and
do not trigger Python fallback.

[Qualification](../evaluations/native_editor/2026-10-16-completion/README.md)
includes library/protocol tests, actual installed-editor snippet insertion and
stale-result cancellation, and preservation of retained execution observations.

## Editor lifecycle

Live checks debounce changes by 250 ms and cancel obsolete background processes.
Before publishing, the adapter checks that observed source hashes still match
current buffers or disk. A stale snapshot is retried. Explicit checks wait for
a current result if an edit or save event invalidates the in-flight check.
Repeated errors from several open entry points are deduplicated on their source.

Checks have a ten-second process timeout. Explicit validate/test/run commands save dirty
open GWT documents, abort on a failed save, and use saved source with a thirty-
second timeout. Run executes a sole entry scenario directly, including a readable
request entry that imports its rules. Zero or multiple scenarios retain the
scenario/request picker; selecting a request requires a JSON input file.
Run's preflight source check is part of the explicit command, so late save-watcher
notifications do not cancel it as a background diagnostic job. Source-hash
validation still rejects a snapshot changed during that check.
A cancelled run selection executes nothing. Commands run the
selected executable directly without a shell or Python fallback. Output is
bounded to 32 MiB and displayed as raw text so large integer tokens are preserved.

[Validation](native-validation.md) checks the saved closure, formatting, and
entry scenarios, requiring at least one scenario. Its report separates failures
from skipped or unexercised gates.
It also reports scenario expectations and recorded behavior/request entries.
Successful validation with missing expectation/call evidence shows a warning
notification and explanatory output; these observations are not a coverage score.

Formatting uses a separate [source-only protocol](native-formatting.md). It
edits the buffer with undo support and checks its version before returning edits;
it does not save, load imports, or execute scenarios.

## Evidence and limits

Rust tests cover snapshot substitution, never-saved imports, Unicode/CRLF error
source, unchanged disk contents, static-only checks, source identity, path and
size refusal, symlinks, and CLI input bounds. JavaScript tests cover range
conversion, snapshot roots, exact output text, process errors, and cancellation.

The [editor qualification](../evaluations/native_editor/2026-10-16/README.md)
records actual VS Code extension-host checks. It covers native diagnostics,
unsaved imports, stale results, unavailable executables, scenario execution,
and Python-mode startup/diagnostics/hover. This establishes local functionality,
not comprehensive IDE support, cross-platform qualification, or measured human
comprehension benefit.

The subsequent [semantic navigation checkpoint](../evaluations/native_editor/2026-10-16-navigation/README.md)
adds resolved calls and scoped bindings, imported unsaved definitions, Unicode
cursor conversion, invalid-edit refusal, and explicit expanded-context bounds.

The [type and field navigation checkpoint](../evaluations/native_editor/2026-10-16-type-navigation/README.md)
adds declaration provenance, identical-shape isolation, nested aliases and
fields, per-row type origins, and actual VS Code navigation into unsaved imports.

The [branch-field checkpoint](../evaluations/native_editor/2026-10-16-branch-navigation/README.md)
adds payload targets selected by checked kind facts, including nested paths,
mutations, copies, collection items, equal-shape isolation, and per-example
contexts. Installed editor checks follow changed conditions and moved unsaved
import declarations without using an old field target. Sixteen captured request
and scenario observations are identical across the metadata change; the engine
source identity still changes and requires explicit case migration.

Sequential [`REQUIRE` proofs](native-require.md) also carry checked presence and
kind information into subsequent payload reads, mutations, and copied values.
Hover and definitions retain the original payload declaration. Removing a
required proof in an unsaved buffer reports the unsafe access and invalidates
its navigation result. The [installed editor checkpoint](../evaluations/native_editor/2026-10-16-require/README.md)
checks both presence and kind removal without saving the source or imports.

[Collection filter proofs](native-filter-proofs.md) likewise preserve payload
hover and definitions inside selected FOR/FIND bodies, including optional list
items and copied values. The installed editor checks removing a filter or
selecting a kind without the requested field in an unsaved buffer.

[Early-return continuations](native-early-returns.md) retain checked payload
hover/definitions after presence and kind guards, including copies. The installed
editor check replaces each returning guard with PASS and verifies that the
newly unsafe unsaved access is diagnosed; restoring the return clears it.

[Explicit failure exits](native-failure-exits.md) likewise support payload hover
and imported definitions after literal-false guards. The
[installed editor qualification](../evaluations/native_editor/2026-10-16-failure-exits/README.md)
checks both plain and parenthesized false literals. Replacing a guard with PASS
or a nonliteral expression reports the first unsafe path and clears semantic
hover/definition results. Restoring the guards clears diagnostics; moving the
imported field through an unsaved Unicode edit updates its target. Positions
are checked against the editor's current text, including its line-ending
normalization, rather than offsets into the replacement string. Saved files
remain unchanged.

## Local document outline

The native VS Code mode provides Outline and Go to Symbol in Editor for local
PROGRAM headers, RECORD/TYPE declarations, behaviors, requests, BACKGROUND,
and SCENARIO sections. Record fields and scenario EXAMPLES tables are children.
Names retain domain wording and source order. Selection ranges point at the
name; block ranges include the body or scenario steps. A declaration between
scenario steps closes the preceding outline range to avoid overlapping siblings;
later steps still follow the language's scenario semantics.

The outline uses the Rust indentation parser on the current document alone.
It does not load imports, resolve types, expand example rows, or execute code.
Missing imports, unknown types, and incomplete expressions therefore do not
hide the surrounding outline. An outline entry identifies source structure,
not a checked declaration or a successful scenario. Semantic hover and
cross-file definitions still require a successful check. Invalid indentation
or exceeded source limits return no guessed outline. Empty/comment-only buffers
have an empty outline.

`gwt-native outline-editor` reads `{ "file": "untitled.gwt", "text": "..." }`
from standard input. It emits `kind: "gwt.native-outline"`, `schemaVersion: 1`,
`ok`, `sourceDigest`, `symbols`, and `diagnostic`. Each symbol has `name`, `kind`,
`range`, `selectionRange`, and `children`; ranges use the existing UTF-8 span
format. Kinds are `program`, `record`, `type`, `field`, `behavior`, `request`,
`background`, `scenario`, and `examples`. `ok` reports successful structural
indexing only. A layout failure has an empty symbols array and a diagnostic.
The CLI exits one for failure. Unknown request fields are rejected.

Requests are bounded to eight MiB of encoded JSON, a 4096-byte filename, and
the existing one-MiB source, 16,384-node, and 64-level nesting limits. No source
file is read or written. The editor verifies the source digest and document
version, discards obsolete/cancelled responses, and maps UTF-8 offsets to VS
Code positions. Untitled documents do not need a save location.

## Type-error explanations

Selected native static diagnostics use GWT type names such as `integer`,
`optional<integer>`, and `list<text>`, rather than Rust debug representations.
Assignments name the received and required types; operators name the offending
operator and operand types; conditions and collection steps name the expected
category and actual type. Structural descriptions include record fields and,
for diagnostic one-of descriptions, variant payload fields. Hover keeps its
compact kind summary. Each type description is bounded to 1024 UTF-8 bytes plus
an ellipsis; names over 128 characters and nesting beyond 64 levels are
abbreviated. These are explanatory descriptions, not new type syntax.

When a path traverses an unproven optional record, the diagnostic identifies the
exact path whose presence must be established. For example, accessing
`facts.customer.age` reports that `facts.customer is present` must be established
first. The same guidance applies to reads and mutation paths. An optional scalar
does not receive that suggestion: a presence guard cannot turn it into a record.

Shared-state argument errors report both the parameter's required type and the
argument's actual type. A parenthesized-copy suggestion appears only if the value
can satisfy that parameter contract. It explicitly states that changes to the
copy do not update the original; choosing a copy is a behavioral decision, not
an automatic fix. The diagnostic adds no conversion or truthiness behavior.

Error codes, locations, and the diagnostic JSON shape stay unchanged. The human
message text changes and should not be parsed as a protocol. This covers static
expression/assignment/condition/collection/path/shared-argument diagnostics;
host-input validation has its own [boundary explanations](native-embedding.md),
while remaining diagnostic categories retain their existing wording.
[Before/after and installed-editor evidence](../evaluations/native_editor/2026-10-16-type-diagnostics/README.md)
checks the changed wording and actual repairs. It is not a comprehension study.
