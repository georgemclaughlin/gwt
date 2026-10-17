//! Reproducible development measurements, not a throughput or production claim.
//! See evaluations/native_performance/README.md for scope and interpretation.
use gwt_core::{ProgramLimits, compile_program, engine_identity};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{hint::black_box, time::Instant};

struct Workload {
    name: String,
    source: String,
    request: &'static str,
    input: Value,
    expected: Value,
}

fn scalar_workload(count: usize, same_record: bool) -> Workload {
    let payload_type = if same_record {
        "  payload: list<integer>\n"
    } else {
        ""
    };
    let extra_type = if same_record {
        ""
    } else {
        "RECORD Archive\n  payload: list<integer>\n\n"
    };
    let extra_input = if same_record {
        ""
    } else {
        "  GIVEN archive is Archive\n"
    };
    let extra_argument = if same_record { "" } else { " with archive" };
    let extra_parameter = if same_record { "" } else { " with <archive>" };
    let extra_contract = if same_record {
        ""
    } else {
        "  AND archive is Archive\n"
    };
    let source = format!(
        "PROGRAM scalar reads

RECORD Facts
  increment: integer
{payload_type}
{extra_type}RECORD Decision
  total: integer

REQUEST accumulate
  GIVEN facts is Facts
{extra_input}  GIVEN decision is Decision
    total: 0
  WHEN accumulate facts{extra_argument} into decision
  OUTPUT decision is Decision

WHEN accumulate <facts>{extra_parameter} into <decision>
  GIVEN facts is Facts
  AND decision is Decision
{extra_contract}{}",
        "  add facts.increment to decision.total\n".repeat(64)
    );
    let payload = json!((0..count).collect::<Vec<_>>());
    let input = if same_record {
        json!({"facts":{"increment":3,"payload":payload}})
    } else {
        json!({"facts":{"increment":3},"archive":{"payload":payload}})
    };
    Workload {
        name: format!(
            "scalar_{}_{count}",
            if same_record { "field" } else { "unrelated" }
        ),
        source,
        request: "accumulate",
        input,
        expected: json!({"decision":{"total":192}}),
    }
}

fn workloads() -> Vec<Workload> {
    let mut result = vec![
        Workload {
            name: "delivery".into(),
            source: include_str!("../../../examples/native_delivery/rules.gwt").into(),
            request: "quote delivery",
            input: json!({"parcel":{"weight_grams":1001,"member":false}}),
            expected: json!({"quote":{"status":"standard","fee":9}}),
        },
        Workload {
            name: "invoice".into(),
            source: include_str!("../tests/fixtures/invoice.gwt").into(),
            request: "price invoice",
            input: json!({"invoice":{"unit_price":"19.95","quantity":2}}),
            expected: json!({"decision":{"status":"priced","total":"47.88"}}),
        },
        Workload {
            name: "reservation".into(),
            source: include_str!("../../../examples/native_reservation/rules.gwt").into(),
            request: "reserve order",
            input: serde_json::from_str(include_str!(
                "../../../examples/native_reservation/input.json"
            ))
            .unwrap(),
            expected: json!({
                "decision":{"line_count":3,"requested":9,"reserved":3,"remaining":4,
                    "missing":["unknown"],"shortages":["gadget"]},
                "inventory":{"items":[{"sku":"widget","available":2},{"sku":"gadget","available":2}]}
            }),
        },
    ];
    for count in [0, 100, 4000] {
        for same_record in [false, true] {
            result.push(scalar_workload(count, same_record));
        }
    }
    result
}

fn measure(mut action: impl FnMut(), iterations: usize, batches: usize) -> Vec<f64> {
    for _ in 0..3 {
        action();
    }
    (0..batches)
        .map(|_| {
            let start = Instant::now();
            for _ in 0..iterations {
                action();
            }
            start.elapsed().as_nanos() as f64 / iterations as f64
        })
        .collect()
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    assert!(
        args.len() <= 2,
        "usage: profile_requests [iterations=100] [batches=7]"
    );
    let iterations: usize = args.first().map_or(100, |v| v.parse().expect("iterations"));
    let batches: usize = args.get(1).map_or(7, |v| v.parse().expect("batches"));
    assert!(iterations > 0 && batches > 0);
    let mut rows = Vec::new();
    for work in workloads() {
        let file = format!("{}.gwt", work.name);
        let program = compile_program(&work.source, &file).unwrap();
        let limits = ProgramLimits::default();
        let execution = program.run_request(work.request, &work.input, limits);
        assert!(execution.ok, "{}: {:?}", work.name, execution.diagnostic);
        assert_eq!(
            execution.result.as_ref(),
            Some(&work.expected),
            "{}",
            work.name
        );
        let serialized = serde_json::to_vec(&execution).unwrap();
        let compile = measure(
            || {
                black_box(compile_program(black_box(&work.source), black_box(&file)).unwrap());
            },
            iterations,
            batches,
        );
        let run = measure(
            || {
                black_box(program.run_request(
                    black_box(work.request),
                    black_box(&work.input),
                    limits,
                ));
            },
            iterations,
            batches,
        );
        let serialize = measure(
            || {
                black_box(serde_json::to_vec(black_box(&execution)).unwrap());
            },
            iterations,
            batches,
        );

        // Compare full successful and budget-failure observations across engines.
        // These hashes are regression evidence, not independent policy oracles.
        let mut budget_observations = Vec::new();
        for steps in [0, 1, 10, 100, 100_000] {
            for evidence_bytes in [0, 250, 5000, 1_048_576] {
                let mut limits = limits;
                limits.execution.steps = steps;
                limits.execution.evidence_bytes = evidence_bytes;
                let run = program.run_request(work.request, &work.input, limits);
                budget_observations.push(json!({
                    "steps":steps,"evidenceBytes":evidence_bytes,"ok":run.ok,
                    "sha256":hash(&serde_json::to_vec(&run).unwrap())
                }));
            }
        }
        rows.push(json!({
            "name":work.name,"source":work.source,"request":work.request,
            "input":work.input,"expected":work.expected,
            "inputBytes":serde_json::to_vec(&work.input).unwrap().len(),
            "executionBytes":serialized.len(),"steps":execution.steps,"events":execution.events.len(),
            "executionSha256":hash(&serialized),"budgetObservations":budget_observations,
            "nsPerOperation":{"compile":compile,"run":run,"serialize":serialize}
        }));
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "kind":"gwt.development-performance","schemaVersion":1,
            "engine":engine_identity(),"iterations":iterations,"batches":batches,
            "workloads":rows
        }))
        .unwrap()
    );
}
