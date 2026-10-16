# Python versus native Rust CLI — 2026-10-16

This is a direct comparison of the current Python and optimized Rust command-line
products on three shared GWT programs and identical JSON requests. It measures
fresh-process invocation through stdout capture, including loading, parsing,
checking where performed by that engine, execution, and JSON output. JSON decoding
and verification occur after timing.

| Workload | Python median | Rust release median | Python/Rust ratio |
| --- | ---: | ---: | ---: |
| Taxable invoice | 113.62 ms | 1.66 ms | 68.6× |
| Member pricing | 113.36 ms | 1.80 ms | 62.8× |
| Order fulfillment | 118.00 ms | 3.85 ms | 30.6× |

There are 360 timed invocations: 30 samples per workload/engine in each of two
passes, with alternating engine order. Three warmups per engine/workload precede
timing. Builds and the prior editor qualifications had completed before timing.
The host is shared; CPU frequency, affinity, and background system activity were
not controlled, and filesystem/loader caches were not cleared.

Each result is checked against a fixed independent expected output. Only declared
numeric output fields are normalized for policy comparison: native exact decimal
strings and Python numbers/decimal strings can differ in representation and scale.
All other fields and complete output shapes must match. Full stdout must remain
byte-identical between repetitions within each engine. This does not claim the
two engines' state, evidence, failures, or host contracts are generally equivalent.

The default Python JSON command returns its result/state envelope. Native always
includes execution evidence, producing a larger response. No evidence was stripped
to improve native timing. This measures those actual CLI products, not matched
instrumentation or a controlled language-only evaluator comparison.

The similar Python timings suggest substantial shared startup/import overhead,
but this run does not isolate that overhead. The observed ratio must not be
advertised as general evaluator throughput,
embedded-service latency, a language-wide speedup, or production performance.
There is no new memory measurement or AI/human performance result in this run.

`metadata.json` records exact source/input hashes, independently specified outputs,
Python/compiler/platform versions, native version report and executable hash.
`samples.jsonl` retains every timing and stdout size/hash. `report.json` records
full observations, exact commands, pass medians, ranges, and verified results.

Reproduce from the repository root with a new output directory:

```sh
cargo +1.96.0 build --release --locked -p gwt-core --bin gwt-native
python evaluations/native_performance/compare_python_cli.py \
  --native target/release/gwt-native --output /tmp/gwt-python-native-cli
```

This checkout-built executable has its own engine identity. It is not the
packaged identity checkpoint binary; package manifest normalization intentionally
changes the source fingerprint.
