use gwt_core::{
    Corpus, CorpusEntry, ProgramLimits, SourceBundle, capture_request, compile_bundle,
    explain_execution, render_review_html, replay_case, review_corpus,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = "RECORD Labels\n  values: list<text>\nREQUEST collect labels\n  GIVEN labels is list<text>\n  GIVEN result is Labels\n    values: []\n  WHEN collect labels into result\n  OUTPUT result is Labels\nWHEN collect <labels> into <result>\n  GIVEN labels is list<text>\n  AND result is Labels\n  FOR label in labels\n    append label to result.values\n";

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

#[test]
fn append_deltas_reconstruct_the_list_in_order_without_prefix_snapshots() {
    let p = program(SOURCE);
    let input = json!({"labels":["first","café 😀","first",""]});
    let run = p.run_request("collect labels", &input, Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    let mut reconstructed = Vec::new();
    for event in run
        .events
        .iter()
        .filter(|event| event.operation == "append item")
    {
        assert_eq!(event.value.as_object().unwrap().len(), 4);
        assert_eq!(event.value["index"], json!(reconstructed.len()));
        assert_eq!(event.value["path"], "result.values");
        assert_eq!(event.value["sourcePath"], "result.values");
        assert_eq!(event.inputs.len(), 1);
        reconstructed.push(event.value["item"].clone());
    }
    assert_eq!(Json::Array(reconstructed), input["labels"]);
    assert_eq!(
        run.result,
        Some(json!({"result":{"values":input["labels"]}}))
    );
    let explanation = explain_execution(&run, p.source_bundle().unwrap()).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .filter(|step| step.operation == "append item")
            .all(|step| step.summary.contains("zero-based index")
                && step.source.text.contains("append label"))
    );
}

#[test]
fn inserted_items_use_the_destination_contract_and_alias_path() {
    let source = "RECORD Values\n  numbers: list<decimal>\nREQUEST extend\n  GIVEN state is Values\n    numbers: [0.5]\n  WHEN extend state.numbers with 1\n  OUTPUT state is Values\nWHEN extend <alias> with <item>\n  GIVEN alias is list<decimal>\n  AND item is integer\n  append item to alias\n";
    let run = program(source).run_request("extend", &json!({}), Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    let event = run
        .events
        .iter()
        .find(|e| e.operation == "append item")
        .unwrap();
    assert_eq!(
        event.value,
        json!({"path":"state.numbers","sourcePath":"alias","index":1,"item":"1"})
    );
    assert_eq!(run.result, Some(json!({"state":{"numbers":["0.5","1"]}})));
    let operand = &run.events[event.inputs[0] - 1];
    assert_eq!(operand.value, json!(1));

    let optional = "RECORD Values\n  items: list<optional<integer>>\nREQUEST extend\n  GIVEN item is optional<integer>\n  GIVEN result is Values\n    items: []\n  WHEN append item to result.items\n  OUTPUT result is Values\n";
    let p = program(optional);
    let run = p.run_request("extend", &json!({"item":null}), Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.result, Some(json!({"result":{"items":[null]}})));
    let event = run
        .events
        .iter()
        .find(|e| e.operation == "append item")
        .unwrap();
    assert_eq!(event.value.get("item"), Some(&Json::Null));
    explain_execution(&run, p.source_bundle().unwrap()).unwrap();
}

#[test]
fn evidence_refusal_happens_before_the_append_and_exact_budget_can_install_it() {
    let p = program(SOURCE);
    let input = json!({"labels":["new"]});
    let run = p.run_request("collect labels", &input, Default::default());
    let position = run
        .events
        .iter()
        .position(|e| e.operation == "append item")
        .unwrap();
    let bytes: usize = run.events[..=position]
        .iter()
        .map(|e| serde_json::to_vec(e).unwrap().len())
        .sum();
    for (limit, expected, recorded) in
        [(bytes - 1, json!([]), false), (bytes, json!(["new"]), true)]
    {
        let mut limits = ProgramLimits::default();
        limits.execution.evidence_bytes = limit;
        let result = p.run_request("collect labels", &input, limits);
        assert!(!result.ok);
        assert_eq!(result.diagnostic.unwrap().code, "evidence_limit");
        assert_eq!(result.state["result"]["values"], expected);
        assert_eq!(
            result.events.iter().any(|e| e.operation == "append item"),
            recorded
        );
    }
}

#[test]
fn append_event_bytes_grow_linearly_for_fixed_size_items() {
    let p = program(SOURCE);
    for count in [32, 64, 128] {
        let labels: Vec<_> = (0..count).map(|_| "x".repeat(200)).collect();
        let result = p.run_request(
            "collect labels",
            &json!({"labels":labels}),
            Default::default(),
        );
        assert!(result.ok, "{count}: {:?}", result.diagnostic);
        assert_eq!(result.result, Some(json!({"result":{"values":labels}})));
        let events: Vec<_> = result
            .events
            .iter()
            .filter(|e| e.operation == "append item")
            .collect();
        assert_eq!(events.len(), count);
        assert!(
            events
                .iter()
                .all(|event| serde_json::to_vec(event).unwrap().len() < 500)
        );
        let bytes: usize = events
            .iter()
            .map(|e| serde_json::to_vec(e).unwrap().len())
            .sum();
        assert!(bytes < 500 * count);
    }
}

#[test]
fn append_review_replays_shows_deltas_and_escapes_inserted_text() {
    let p = program(SOURCE);
    let case = capture_request(
        &p,
        "collect labels",
        &json!({"labels":["</script><svg onload=alert(1)>"]}),
        Default::default(),
    )
    .unwrap();
    assert!(replay_case(&case).unwrap().verified);
    let corpus = Corpus::new(vec![CorpusEntry {
        id: "append".into(),
        label: "append".into(),
        case: json!(case),
    }])
    .unwrap();
    let review = review_corpus(&corpus, &p).unwrap();
    let html = render_review_html(&review).unwrap();
    assert!(html.contains("Appended the recorded item at the zero-based index"));
    assert!(html.contains("&lt;/script&gt;&lt;svg onload=alert(1)&gt;"));
    assert!(!html.contains("<svg onload=alert(1)>"));
    let mut visible = 0;
    for (offset, _) in html.match_indices("<strong>append item</strong>") {
        let start = html[..offset].rfind("<li ").unwrap();
        assert!(html[start..offset].contains("class=\"event \""));
        visible += 1;
    }
    assert_eq!(visible, 2); // Baseline and candidate trails, visible without expression details.
    for value in [
        json!({"path":"p","sourcePath":"p","index":-1,"item":0}),
        json!({"path":"p","sourcePath":"p","index":0}),
        json!({"path":"p","sourcePath":"p","index":0,"item":0,"after":[]}),
    ] {
        let mut run = p.run_request(
            "collect labels",
            &json!({"labels":["x"]}),
            Default::default(),
        );
        run.events
            .iter_mut()
            .find(|e| e.operation == "append item")
            .unwrap()
            .value = value;
        assert_eq!(
            explain_execution(&run, p.source_bundle().unwrap())
                .unwrap_err()
                .code,
            "evidence_value"
        );
    }
}
