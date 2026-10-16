# Native Node host qualification — 2026-10-16

The [reference Node adapter](../../../examples/native_node_host/README.md) calls
the existing packaged Rust engine directly. This extends local host qualification
beyond Rust without introducing a second evaluator or changing the native engine.
The Python-backed TypeScript client remains a separate boundary.

**All 13 Node tests pass** on Node **22.22.2**, Linux x86_64. The selected static
executable has SHA-256
`f3c425ef4ff8d00a73f0e92121d61d25a8220febd0820057120bfd4eb2ab298a` and packaged
engine source identity
`sha256:f5b1f33b4ce11bd6721ab3fd2546e3827e193fcb6928736a2d97e9fa530dfd1c`.
Its package and Rust-host qualification is retained in the
[review identity checkpoint](../../native_review/2026-10-16-review-identity/README.md).

The tests establish:

- Four independent invoice totals, including quantities above JavaScript's safe
  integer range and a price of `0.000000000000000001`. Complete parsed observations
  and raw stdout match direct native CLI execution for each successful case.
- Input-contract failures preserve empty behavior evidence; a zero-quantity
  requirement failure retains executed evidence; a zero-step limit remains a
  structured native failure rather than a host process error.
- Twelve concurrent requests preserve independent quantities, results, and
  invocation files.
- A copied adapter, source file, binary, and Node driver run outside the repository
  with `PATH` empty. The engine requires no Python or Rust installation to execute.
- Spaces and shell metacharacters in program and executable filenames are passed
  literally. No shell is used.
- Missing executables, compile errors, invalid JSON, mismatched request/status,
  unknown schema versions, timeouts, and excessive output cannot become successful
  policy results. Timeout termination uses SIGKILL.
- Temporary invocation directories are removed after success and failure.
  Unsafe/fractional Numbers, undefined fields, sparse arrays, cycles, non-plain
  objects, oversized inputs, and invalid host limits are rejected.

The output total for quantity `9007199254740993` at unit price `0.01`, including
the fixture's 20% tax, is exactly `108086391056891.916`. Quantity stays `bigint`
in Node state/evidence; decimal values stay strings. Raw JSON has integer tokens
and therefore requires an exact parser when read into JavaScript.

`observations.json` retains full exact observations and source/binary identities;
`tests.log` records the successful test run. `verification.json` records final
artifact identities and checks. No native sources, semantics, approvals, or
captured cases changed. The prior 59 engine build inputs remain identical, so
the full Rust/Python suites were not repeated for this host-only addition.

Reproduce from the repository root using an explicitly selected executable:

```sh
GWT_NATIVE_PATH=/absolute/path/to/gwt-native GWT_NODE_EVIDENCE=/tmp/gwt-node-evidence node --test tests/native_node_host.test.mjs
node examples/native_node_host/quote.mjs /absolute/path/to/gwt-native
```

CI now runs the Node tests after native package qualification in each existing
toolchain/profile/target job. This is configured coverage, not a claimed hosted
CI result. The local checkpoint qualifies the stated Node/OS/binary combination;
other Node versions and operating systems remain unqualified here.

This process boundary recompiles source on each call. It does not demonstrate
production throughput, persistent-worker behavior, browser execution, an external
pilot, or human comprehension benefit. Keep immutable source deployments and
application effects under host control. Broader deployment and the full project
goal remain unfinished.
