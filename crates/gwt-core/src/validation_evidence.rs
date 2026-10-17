//! A factual inventory of scenario expectations and recorded call entries.
//! These observations do not measure branch coverage or the quality of an oracle.
use crate::program::{CompiledProgram, Scenario, StatementKind};
use crate::{Event, source::Span};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ExpectationKind {
    Condition,
    PrintedOutput,
    Failure,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ExpectationOutcome {
    Passed,
    Failed,
    NotObserved,
}

#[derive(Debug, Serialize)]
pub struct ExpectationObservation {
    pub kind: ExpectationKind,
    pub span: Span,
    pub outcome: ExpectationOutcome,
    /// One-based event ID within this scenario's execution, not a global ID.
    pub event: Option<usize>,
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExpectationTotals {
    pub declared: usize,
    pub passed: usize,
    pub failed: usize,
    pub not_observed: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum CallableKind {
    Behavior,
    Request,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CallableObservation {
    pub kind: CallableKind,
    pub name: String,
    pub definition: Span,
    pub recorded_entries: usize,
    pub scenarios_with_entries: usize,
}

#[derive(Debug, Serialize)]
pub struct ValidationWarning {
    pub code: &'static str,
    pub message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ValidationEvidence {
    pub scenario_expectations: ExpectationTotals,
    pub scenarios_without_expectations: Vec<String>,
    pub callables: Vec<CallableObservation>,
}

type Site<'a> = (&'a str, usize, usize);
fn site(span: &Span) -> Site<'_> {
    (&span.file, span.start, span.end)
}

pub(crate) fn expectations(scenario: &Scenario, events: &[Event]) -> Vec<ExpectationObservation> {
    let recorded: BTreeMap<_, _> = events
        .iter()
        .filter(|event| {
            matches!(
                event.operation.as_str(),
                "assert" | "assert prints" | "assert failure"
            )
        })
        .map(|event| ((site(&event.span), event.operation.as_str()), event))
        .collect();
    scenario
        .expectations
        .iter()
        .map(|index| {
            let statement = &scenario.body[*index];
            let (kind, operation) = match statement.kind {
                StatementKind::Assert(_, _) => (ExpectationKind::Condition, "assert"),
                StatementKind::ExpectPrints(_) => (ExpectationKind::PrintedOutput, "assert prints"),
                StatementKind::ExpectFailure { .. } => (ExpectationKind::Failure, "assert failure"),
                _ => unreachable!("compiler records only scenario expectations"),
            };
            let event = recorded.get(&(site(&statement.span), operation));
            let outcome = event.and_then(|event| {
                if kind == ExpectationKind::Condition {
                    event.value.as_bool()
                } else {
                    event.value["matched"].as_bool()
                }
            });
            ExpectationObservation {
                kind,
                span: statement.span.clone(),
                outcome: match outcome {
                    Some(true) => ExpectationOutcome::Passed,
                    Some(false) => ExpectationOutcome::Failed,
                    None => ExpectationOutcome::NotObserved,
                },
                event: event.map(|event| event.sequence),
            }
        })
        .collect()
}

pub(crate) struct EvidenceCollector<'a> {
    evidence: ValidationEvidence,
    declarations: BTreeMap<(CallableKind, Site<'a>), usize>,
}

impl<'a> EvidenceCollector<'a> {
    pub fn new(program: &'a CompiledProgram) -> Self {
        let mut callables = Vec::new();
        let mut declarations = BTreeMap::new();
        for (kind, name, definition) in program
            .behaviors
            .iter()
            .map(|item| (CallableKind::Behavior, item.signature.join(" "), &item.span))
            .chain(
                program
                    .requests
                    .iter()
                    .map(|item| (CallableKind::Request, item.name.clone(), &item.span)),
            )
        {
            declarations.insert((kind, site(definition)), callables.len());
            callables.push(CallableObservation {
                kind,
                name,
                definition: definition.clone(),
                recorded_entries: 0,
                scenarios_with_entries: 0,
            });
        }
        Self {
            evidence: ValidationEvidence {
                scenario_expectations: ExpectationTotals::default(),
                scenarios_without_expectations: Vec::new(),
                callables,
            },
            declarations,
        }
    }

    pub fn observe(
        &mut self,
        name: &str,
        expectations: &[ExpectationObservation],
        events: &[Event],
    ) {
        if expectations.is_empty() {
            self.evidence
                .scenarios_without_expectations
                .push(name.into());
        }
        let totals = &mut self.evidence.scenario_expectations;
        totals.declared += expectations.len();
        for observation in expectations {
            match observation.outcome {
                ExpectationOutcome::Passed => totals.passed += 1,
                ExpectationOutcome::Failed => totals.failed += 1,
                ExpectationOutcome::NotObserved => totals.not_observed += 1,
            }
        }
        let mut observed = BTreeSet::new();
        for event in events {
            let kind = match event.operation.as_str() {
                "enter behavior" => CallableKind::Behavior,
                "enter request" => CallableKind::Request,
                _ => continue,
            };
            // Runtime-produced evidence is matched by definition site, never by
            // matching display labels or scanning source text for call names.
            if let Ok(definition) =
                serde_json::from_value::<Span>(event.value["definition"].clone())
            {
                if let Some(index) = self.declarations.get(&(kind, site(&definition))) {
                    self.evidence.callables[*index].recorded_entries += 1;
                    observed.insert(*index);
                }
            }
        }
        for index in observed {
            self.evidence.callables[index].scenarios_with_entries += 1;
        }
    }

    pub fn finish(self) -> (ValidationEvidence, Vec<ValidationWarning>) {
        let mut warnings = Vec::new();
        let missing = self.evidence.scenarios_without_expectations.len();
        if missing > 0 {
            let subject = if missing == 1 {
                "scenario declares"
            } else {
                "scenarios declare"
            };
            warnings.push(ValidationWarning { code: "scenarios_without_expectations", message: format!("{missing} {subject} no scenario or background THEN expectations. A successful action alone does not establish an expected outcome.") });
        }
        let missing = self.evidence.scenario_expectations.not_observed;
        if missing > 0 {
            let subject = if missing == 1 {
                "expectation has"
            } else {
                "expectations have"
            };
            warnings.push(ValidationWarning { code: "unobserved_expectations", message: format!("{missing} scenario {subject} no recorded outcome. Execution may have stopped before or during evaluation.") });
        }
        let missing = self
            .evidence
            .callables
            .iter()
            .filter(|item| item.recorded_entries == 0)
            .count();
        if missing > 0 {
            let subject = if missing == 1 {
                "behavior or request has"
            } else {
                "behavior or request declarations have"
            };
            warnings.push(ValidationWarning { code: "unobserved_callables", message: format!("{missing} {subject} no recorded entry in these scenarios. See the declaration list.") });
        }
        (self.evidence, warnings)
    }
}
