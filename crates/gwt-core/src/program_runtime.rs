use serde::{Deserialize, Serialize};
use serde_json::{Value as Json, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
};

use crate::evaluation::{Context, Event, Limits};
use crate::program::{
    Argument, Behavior, Binding, BoundExpression, Change, CompiledProgram, Initializer, Iteration,
    Place, ProofGuard, Request, Scenario, Statement, StatementKind,
};
use crate::source::{Diagnostic, Result, Span};
use crate::value::{Type, Value, checked_numeric, normalize};
use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::Zero;

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProgramLimits {
    pub execution: Limits,
    /// Combined call/branch nesting allowance, with a hard ceiling of 64.
    pub call_depth: usize,
}
impl Default for ProgramLimits {
    fn default() -> Self {
        Self {
            execution: Limits {
                steps: 100_000,
                ..Limits::default()
            },
            call_depth: 64,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProgramExecution {
    pub kind: &'static str,
    pub schema_version: u32,
    pub file: String,
    pub program_identity: Option<crate::bundle::ProgramIdentity>,
    pub program: Option<String>,
    pub request: Option<String>,
    pub ok: bool,
    pub state: Json,
    pub result: Option<Json>,
    pub output: Vec<Json>,
    pub diagnostic: Option<Diagnostic>,
    pub steps: usize,
    pub events: Vec<Event>,
}
#[derive(Debug, Serialize)]
pub struct ScenarioExecution {
    pub name: String,
    pub execution: ProgramExecution,
}

#[derive(Clone, PartialEq, Eq)]
enum Segment {
    Field(String),
    Index(usize),
}

#[derive(Clone)]
struct Address {
    cell: Rc<RefCell<Option<Value>>>,
    fields: Vec<Segment>,
    label: String,
}
impl Address {
    fn read(&self, span: &Span) -> Result<Value> {
        self.read_fields(&[], span)
    }
    fn read_fields(&self, fields: &[String], span: &Span) -> Result<Value> {
        let borrowed = self.cell.borrow();
        let mut current = borrowed.as_ref().ok_or_else(|| {
            Diagnostic::new(
                "uninitialized_state",
                format!("'{}' is not initialized", self.label),
                span,
            )
        })?;
        for field in &self.fields {
            current = match (field, current) {
                (Segment::Field(field), Value::Record(record)) => record.get(field),
                (Segment::Index(index), Value::List(items)) => items.get(*index),
                _ => None,
            }
            .ok_or_else(|| {
                Diagnostic::new(
                    "internal_invariant",
                    "checked state location is missing",
                    span,
                )
            })?;
        }
        crate::evaluation::read_fields(current, fields, span)
    }
    fn write(&self, value: Value, span: &Span) -> Result<()> {
        let mut borrowed = self.cell.borrow_mut();
        if self.fields.is_empty() {
            *borrowed = Some(value);
            return Ok(());
        }
        let mut current = borrowed.as_mut().ok_or_else(|| {
            Diagnostic::new(
                "internal_invariant",
                "mutation target is not initialized",
                span,
            )
        })?;
        for field in &self.fields {
            current = match (field, current) {
                (Segment::Field(field), Value::Record(record)) => record.get_mut(field),
                (Segment::Index(index), Value::List(items)) => items.get_mut(*index),
                _ => None,
            }
            .ok_or_else(|| {
                Diagnostic::new("internal_invariant", "mutation location is missing", span)
            })?;
        }
        *current = value;
        Ok(())
    }
}
struct Frame {
    slots: Vec<Address>,
}
impl Frame {
    fn new(count: usize) -> Self {
        Self {
            slots: (0..count)
                .map(|index| Address {
                    cell: Rc::new(RefCell::new(None)),
                    fields: Vec::new(),
                    label: format!("local:{index}"),
                })
                .collect(),
        }
    }
    fn place(&self, place: &Place) -> Address {
        let mut address = self.slots[place.slot].clone();
        address
            .fields
            .extend(place.fields.iter().cloned().map(Segment::Field));
        if !place.fields.is_empty() {
            address.label.push('.');
            address.label.push_str(&place.fields.join("."));
        }
        address
    }
    fn state(&self, bindings: &BTreeMap<String, Binding>, span: &Span) -> Json {
        Json::Object(
            bindings
                .iter()
                .filter_map(|(name, binding)| {
                    self.slots[binding.slot]
                        .read(span)
                        .ok()
                        .map(|value| (name.clone(), value.json()))
                })
                .collect(),
        )
    }
}
struct Returned {
    value: Value,
    event: usize,
}

struct Runtime<'a> {
    program: &'a CompiledProgram,
    context: Context,
    limits: ProgramLimits,
    output: Vec<Json>,
    traversals: Vec<Address>,
    narrowed: Vec<(Address, BTreeSet<String>)>,
    present: Vec<Address>,
}

impl CompiledProgram {
    pub fn run_request(&self, name: &str, input: &Json, limits: ProgramLimits) -> ProgramExecution {
        let mut runtime = Runtime::new(self, limits);
        let Some(request) = self.requests.iter().find(|request| request.name == name) else {
            return runtime.finish(
                Some(name.into()),
                json!({}),
                Err(Diagnostic::new(
                    "unknown_request",
                    format!("unknown request '{name}'"),
                    &self.span,
                )),
            );
        };
        let mut frame = Frame::new(request.slots);
        let result = (|| {
            crate::validate_input_shape(input, &request.span)?;
            if serde_json::to_vec(input).expect("JSON input").len() > 1_048_576 {
                return Err(Diagnostic::new(
                    "input_limit",
                    "input JSON exceeds one MiB",
                    &request.span,
                ));
            }
            let contract = Type::Record(
                request
                    .inputs
                    .iter()
                    .map(|(parameter, _)| (parameter.name.clone(), parameter.ty.clone()))
                    .collect(),
            );
            let Value::Record(mut values) = normalize(&contract, Some(input), &request.span)?
            else {
                unreachable!("record contract")
            };
            for (parameter, slot) in &request.inputs {
                frame.slots[*slot].label = parameter.name.clone();
                frame.slots[*slot].write(
                    values.remove(&parameter.name).expect("normalized input"),
                    &parameter.span,
                )?;
            }
            runtime.request(request, &mut frame, &request.span, 0)
        })();
        let state = frame.state(&request.bindings, &request.span);
        runtime.finish(Some(name.into()), state, result)
    }

    /// Execute exactly one checked scenario (including one expanded example row).
    /// Other scenarios are checked during compilation but are not executed here.
    pub fn run_scenario(&self, name: &str, limits: ProgramLimits) -> ProgramExecution {
        match self.scenarios.iter().find(|scenario| scenario.name == name) {
            Some(scenario) => self.execute_scenario(scenario, limits),
            None => Runtime::new(self, limits).finish(
                None,
                json!({}),
                Err(Diagnostic::new(
                    "unknown_scenario",
                    format!("unknown scenario '{name}'"),
                    &self.span,
                )),
            ),
        }
    }

    pub fn test_scenarios(&self, limits: ProgramLimits) -> Vec<ScenarioExecution> {
        self.scenarios
            .iter()
            .map(|scenario| ScenarioExecution {
                name: scenario.name.clone(),
                execution: self.execute_scenario(scenario, limits),
            })
            .collect()
    }

    fn execute_scenario(&self, scenario: &Scenario, limits: ProgramLimits) -> ProgramExecution {
        let mut runtime = Runtime::new(self, limits);
        let mut frame = Frame::new(scenario.slots);
        let result = (|| {
            if let Some(example) = &scenario.example {
                let values: BTreeMap<_, _> = example
                    .cells
                    .iter()
                    .map(|(name, cell)| (name.as_ref(), &cell.text))
                    .collect();
                runtime.context.record(
                    &example.span,
                    "example row".into(),
                    Vec::new(),
                    json!({"scenario": scenario.name, "row": example.index, "values": values}),
                    None,
                )?;
            }
            runtime.body(&scenario.body, &mut frame, 0)?;
            Ok(frame.state(&scenario.bindings, &scenario.span))
        })();
        let state = frame.state(&scenario.bindings, &scenario.span);
        runtime.finish(None, state, result)
    }
}

impl<'a> Runtime<'a> {
    fn new(program: &'a CompiledProgram, limits: ProgramLimits) -> Self {
        Self {
            program,
            limits,
            context: Context::new(limits.execution),
            output: Vec::new(),
            traversals: Vec::new(),
            narrowed: Vec::new(),
            present: Vec::new(),
        }
    }
    fn finish(
        self,
        request: Option<String>,
        state: Json,
        result: Result<Json>,
    ) -> ProgramExecution {
        let (result, diagnostic) = match result {
            Ok(result) => (Some(result), None),
            Err(error) => (None, Some(error)),
        };
        ProgramExecution {
            kind: "gwt.native-run",
            schema_version: 1,
            file: self.program.file.clone(),
            program_identity: self.program.identity.clone(),
            program: self.program.name.clone(),
            request,
            ok: diagnostic.is_none(),
            state,
            result,
            output: self.output,
            diagnostic,
            steps: self.context.steps,
            events: self.context.events,
        }
    }
    fn expression(
        &mut self,
        expression: &BoundExpression,
        frame: &Frame,
    ) -> Result<(Value, usize)> {
        // Binding slots are resolved at compile time. Read only the path reached
        // by evaluation, including short-circuiting, and clone only its value.
        self.context
            .eval(&expression.expression, &|slot, fields, span| {
                frame.slots[expression.slots[slot]].read_fields(fields, span)
            })
    }
    fn initializer(&mut self, value: &Initializer, frame: &Frame) -> Result<(Value, Vec<usize>)> {
        match value {
            Initializer::Table { item_type, rows } => {
                let mut values = Vec::new();
                let mut events = Vec::new();
                let mut budget = crate::value::ValueBudget::new();
                for (span, row) in rows {
                    self.context.charge(span)?;
                    let (value, inputs) = self.initializer(row, frame)?;
                    let value = normalize(item_type, Some(&value.json()), span)?;
                    budget.include(&value, None, span)?;
                    events.push(self.context.record(
                        span,
                        "table row".into(),
                        inputs,
                        value.json(),
                        None,
                    )?);
                    values.push(value);
                }
                Ok((Value::List(values), events))
            }
            Initializer::Absent => Ok((Value::Absent, Vec::new())),
            Initializer::Expression(expression) => {
                let (value, event) = self.expression(expression, frame)?;
                Ok((value, vec![event]))
            }
            Initializer::Record(fields) => {
                let mut values = BTreeMap::new();
                let mut events = Vec::new();
                let mut budget = crate::value::ValueBudget::new();
                for (name, initializer) in fields {
                    let (value, ids) = self.initializer(initializer, frame)?;
                    budget.include(&value, Some(name), &self.program.span)?;
                    values.insert(name.clone(), value);
                    events.extend(ids);
                }
                Ok((Value::Record(values), events))
            }
        }
    }
    fn request(
        &mut self,
        request: &Request,
        frame: &mut Frame,
        call_span: &Span,
        depth: usize,
    ) -> Result<Json> {
        self.depth(depth, call_span)?;
        self.context.record(
            call_span,
            "enter request".into(),
            Vec::new(),
            json!({"name":request.name,"definition":request.span}),
            None,
        )?;
        self.body(&request.body, frame, depth + 1)?;
        let mut result = serde_json::Map::new();
        for (parameter, slot) in &request.outputs {
            let value = frame.slots[*slot].read(&parameter.span)?;
            let value = normalize(&parameter.ty, Some(&value.json()), &parameter.span)?;
            self.context.record(
                &parameter.span,
                "output contract".into(),
                Vec::new(),
                json!({"path":parameter.name,"value":value.json()}),
                None,
            )?;
            result.insert(parameter.name.clone(), value.json());
        }
        self.body(&request.postconditions, frame, depth + 1)?;
        self.context.record(
            call_span,
            "leave request".into(),
            Vec::new(),
            json!({"name":request.name}),
            None,
        )?;
        Ok(Json::Object(result))
    }
    fn depth(&self, depth: usize, span: &Span) -> Result<()> {
        if depth >= self.limits.call_depth.min(64) {
            Err(Diagnostic::new(
                "call_depth",
                "execution nesting limit exceeded (calls and branch bodies)",
                span,
            ))
        } else {
            Ok(())
        }
    }
    fn check_mutation(&self, target: &Address, span: &Span) -> Result<()> {
        if self.traversals.iter().any(|source| {
            Rc::ptr_eq(&source.cell, &target.cell) && source.fields.starts_with(&target.fields)
        }) {
            return Err(Diagnostic::new(
                "collection_mutation",
                "cannot replace or append to an active traversal's source collection or its ancestor",
                span,
            ));
        }
        Ok(())
    }
    fn mutate(
        &mut self,
        target: &Address,
        place: &Place,
        value: Value,
        inputs: Vec<usize>,
        operation: &str,
        span: &Span,
    ) -> Result<()> {
        self.check_mutation(target, span)?;
        crate::value::value_size(&value, 0, span)?;
        let value = normalize(&place.ty, Some(&value.json()), span)?;
        for locked in &self.present {
            if !Rc::ptr_eq(&locked.cell, &target.cell) || !locked.fields.starts_with(&target.fields)
            {
                continue;
            }
            let mut selected = Some(&value);
            for segment in &locked.fields[target.fields.len()..] {
                selected = match (segment, selected) {
                    (Segment::Field(name), Some(Value::Record(fields))) => fields.get(name),
                    (Segment::Index(index), Some(Value::List(items))) => items.get(*index),
                    _ => None,
                };
            }
            if matches!(selected, None | Some(Value::Absent)) {
                return Err(Diagnostic::new(
                    "presence_mutation",
                    format!(
                        "cannot clear active present value '{}', including through an alias or ancestor",
                        locked.label
                    ),
                    span,
                ));
            }
        }
        for (locked, kinds) in &self.narrowed {
            if !Rc::ptr_eq(&locked.cell, &target.cell) || !locked.fields.starts_with(&target.fields)
            {
                continue;
            }
            let mut selected = Some(&value);
            for segment in &locked.fields[target.fields.len()..] {
                selected = match (segment, selected) {
                    (Segment::Field(name), Some(Value::Record(fields))) => fields.get(name),
                    (Segment::Index(index), Some(Value::List(items))) => items.get(*index),
                    _ => None,
                };
            }
            if !matches!(selected, Some(Value::Record(fields)) if matches!(fields.get("kind"), Some(Value::Text(actual)) if kinds.contains(actual)))
            {
                return Err(Diagnostic::new(
                    "kind_mutation",
                    "cannot invalidate an active kind proof, including through an alias or ancestor",
                    span,
                ));
            }
        }
        let before = target.read(&place.span)?;
        let (operation, evidence) = if operation == "append" {
            let (Value::List(previous), Value::List(next)) = (&before, &value) else {
                return Err(Diagnostic::new(
                    "internal_invariant",
                    "append requires list state",
                    span,
                ));
            };
            let Some((item, prefix)) = next.split_last() else {
                return Err(Diagnostic::new(
                    "internal_invariant",
                    "append must add one item",
                    span,
                ));
            };
            if prefix != previous.as_slice() {
                return Err(Diagnostic::new(
                    "internal_invariant",
                    "append must preserve existing items",
                    span,
                ));
            }
            (
                "append item",
                json!({"path":target.label,"sourcePath":place.spelling,"index":previous.len(),"item":item.json()}),
            )
        } else {
            (
                operation,
                json!({"path":target.label,"sourcePath":place.spelling,"before":before.json(),"after":value.json()}),
            )
        };
        self.context
            .record(span, operation.into(), inputs, evidence, None)?;
        target.write(value, &place.span)
    }
    fn depending(
        &mut self,
        statement: &Statement,
        frame: &mut Frame,
        depth: usize,
    ) -> Result<Option<Returned>> {
        let StatementKind::Depending {
            subject,
            location,
            arms,
            otherwise,
        } = &statement.kind
        else {
            unreachable!("kind dispatch statement")
        };
        let (value, input) = self.expression(subject, frame)?;
        let Value::Record(fields) = value else {
            unreachable!("checked one-of subject")
        };
        let Value::Text(kind) = &fields["kind"] else {
            unreachable!("validated kind")
        };
        let selected = arms.iter().position(|(candidate, _, _)| candidate == kind);
        for (index, (candidate, span, _)) in arms.iter().enumerate() {
            self.context.charge(span)?;
            self.context.record(
                span,
                "kind branch".into(),
                vec![input],
                json!({"kind":kind,"candidate":candidate,"selected":selected == Some(index)}),
                None,
            )?;
        }
        let body = if let Some(index) = selected {
            if let Some((span, _)) = otherwise {
                self.context.record(
                    span,
                    "branch skipped".into(),
                    vec![input],
                    Json::Null,
                    Some(span.clone()),
                )?;
            }
            &arms[index].2
        } else {
            let (span, body) = otherwise.as_ref().expect("exhaustive kind branches");
            self.context.record(
                span,
                "else selected".into(),
                vec![input],
                Json::Bool(true),
                None,
            )?;
            body
        };
        let previous = self.narrowed.len();
        self.narrowed
            .push((frame.place(location), BTreeSet::from([kind.clone()])));
        let result = self.body(body, frame, depth + 1);
        self.narrowed.truncate(previous);
        result
    }

    fn depending_value(
        &mut self,
        statement: &Statement,
        frame: &mut Frame,
        depth: usize,
    ) -> Result<Option<Returned>> {
        let StatementKind::ValueDepending {
            subject,
            arms,
            otherwise,
        } = &statement.kind
        else {
            unreachable!("value dispatch statement")
        };
        // Snapshot once. Mutations in the chosen body cannot select another arm.
        // Unlike kind dispatch, value dispatch establishes no type refinement.
        let (value, input) = self.expression(subject, frame)?;
        let mut selected = None;
        for (index, (candidate, span, _)) in arms.iter().enumerate() {
            self.context.charge(span)?;
            let matched = crate::evaluation::equal(&value, candidate);
            self.context.record(
                span,
                "value branch".into(),
                vec![input],
                json!({"actual":value.json(),"candidate":candidate.json(),"selected":matched}),
                None,
            )?;
            if matched {
                selected = Some(index);
            }
        }
        let body = if let Some(index) = selected {
            if let Some((span, _)) = otherwise {
                self.context.record(
                    span,
                    "branch skipped".into(),
                    vec![input],
                    Json::Null,
                    Some(span.clone()),
                )?;
            }
            &arms[index].2
        } else {
            let (span, body) = otherwise.as_ref().expect("exhaustive value branches");
            self.context.record(
                span,
                "else selected".into(),
                vec![input],
                Json::Bool(true),
                None,
            )?;
            body
        };
        self.body(body, frame, depth + 1)
    }

    fn traverse(
        &mut self,
        iteration: &Iteration,
        body: &[Statement],
        otherwise: Option<&(Span, Vec<Statement>)>,
        frame: &mut Frame,
        span: &Span,
        depth: usize,
    ) -> Result<Option<Returned>> {
        let (value, source_event) = self.expression(&iteration.source, frame)?;
        let Value::List(items) = value else {
            unreachable!("checked list")
        };
        let location = iteration.location.as_ref().map(|place| frame.place(place));
        self.context.record(span, "enter collection".into(), vec![source_event], json!({"binding":iteration.name,"sourcePath":location.as_ref().map(|address| &address.label),"length":items.len(),"mode":if otherwise.is_some(){"FIND"}else{"FOR"}}), None)?;
        let previous_locks = self.traversals.len();
        if let Some(location) = &location {
            self.traversals.push(location.clone());
        }
        let outcome = (|| -> Result<(bool, Option<Returned>)> {
            let mut found = false;
            for (index, item) in items.into_iter().enumerate() {
                self.context.charge(span)?;
                let address = if let Some(location) = &location {
                    let mut address = location.clone();
                    address.fields.push(Segment::Index(index));
                    address.label.push_str(&format!("[{index}]"));
                    address
                } else {
                    Address {
                        cell: Rc::new(RefCell::new(Some(item))),
                        fields: Vec::new(),
                        label: format!("{}[{index}]", iteration.name),
                    }
                };
                let item_event = self.context.record(span, "collection item".into(), vec![source_event], json!({"index":index,"binding":iteration.name,"path":address.label,"value":address.read(span)?.json()}), None)?;
                frame.slots[iteration.slot] = address;
                let (selected, input) = if let Some(condition) = &iteration.condition {
                    let (value, event) = self.expression(condition, frame)?;
                    let Value::Boolean(selected) = value else {
                        unreachable!("checked condition")
                    };
                    (selected, event)
                } else {
                    (true, item_event)
                };
                self.context.record(
                    iteration
                        .condition
                        .as_ref()
                        .map_or(span, |condition| &condition.expression.span),
                    "collection selection".into(),
                    vec![input],
                    json!({"index":index,"selected":selected}),
                    None,
                )?;
                if selected {
                    if let Some(returned) =
                        self.guarded_body(body, &iteration.guards, frame, depth + 1)?
                    {
                        return Ok((true, Some(returned)));
                    }
                    found = true;
                    if otherwise.is_some() {
                        break;
                    }
                }
            }
            Ok((found, None))
        })();
        self.traversals.truncate(previous_locks);
        let (found, returned) = outcome?;
        let mut exit = json!({"matched":found});
        if returned.is_some() {
            exit["exit"] = json!("return");
        }
        self.context.record(
            span,
            "leave collection".into(),
            returned
                .as_ref()
                .map_or_else(Vec::new, |returned| vec![returned.event]),
            exit,
            None,
        )?;
        if let Some((else_span, otherwise)) = otherwise {
            if !found {
                self.context.record(
                    else_span,
                    "else selected".into(),
                    Vec::new(),
                    Json::Bool(true),
                    None,
                )?;
                return self.body(otherwise, frame, depth + 1);
            } else {
                self.context.record(
                    else_span,
                    "branch skipped".into(),
                    Vec::new(),
                    Json::Null,
                    Some(else_span.clone()),
                )?;
            }
        }
        Ok(returned)
    }

    // Evaluate value arguments before entering the callee, using a separate
    // frame so argument construction does not enlarge every recursive body frame.
    fn prepare_call(
        &mut self,
        behavior: &Behavior,
        arguments: &[Argument],
        caller: &Frame,
        span: &Span,
    ) -> Result<Frame> {
        let mut callee = Frame::new(behavior.slots);
        let mut bindings = BTreeMap::new();
        let mut values = BTreeMap::new();
        let mut inputs = Vec::new();
        for (slot, (argument, parameter)) in arguments.iter().zip(&behavior.parameters).enumerate()
        {
            match argument {
                Argument::Alias(place) => {
                    callee.slots[slot] = caller.place(place);
                    bindings.insert(parameter.name.clone(), callee.slots[slot].label.clone());
                }
                Argument::Value(expression) => {
                    let (value, input) = self.expression(expression, caller)?;
                    let value = normalize(
                        &parameter.ty,
                        Some(&value.json()),
                        &expression.expression.span,
                    )?;
                    let event = self.context.record(
                        &expression.expression.span,
                        "argument value".into(),
                        vec![input],
                        json!({"parameter":parameter.name,"value":value.json()}),
                        None,
                    )?;
                    inputs.push(event);
                    values.insert(parameter.name.clone(), event);
                    callee.slots[slot].label = format!("{} (value)", parameter.name);
                    callee.slots[slot].write(value, &expression.expression.span)?;
                }
            }
        }
        let mut entered = json!({"signature":behavior.signature.join(" "),"definition":behavior.span,"bindings":bindings});
        if !values.is_empty() {
            entered["valueArguments"] = json!(values);
        }
        self.context
            .record(span, "enter behavior".into(), inputs, entered, None)?;
        Ok(callee)
    }

    fn protect(&mut self, guards: &[ProofGuard], frame: &Frame) {
        for guard in guards {
            match guard {
                ProofGuard::Present(place) => self.present.push(frame.place(place)),
                ProofGuard::Kinds(place, kinds) => {
                    self.narrowed.push((frame.place(place), kinds.clone()))
                }
            }
        }
    }

    fn guarded_body(
        &mut self,
        statements: &[Statement],
        guards: &[ProofGuard],
        frame: &mut Frame,
        depth: usize,
    ) -> Result<Option<Returned>> {
        let previous = self.present.len();
        let previous_kinds = self.narrowed.len();
        self.protect(guards, frame);
        let result = self.body(statements, frame, depth);
        self.present.truncate(previous);
        self.narrowed.truncate(previous_kinds);
        result
    }

    fn body(
        &mut self,
        statements: &[Statement],
        frame: &mut Frame,
        depth: usize,
    ) -> Result<Option<Returned>> {
        // Proofs established by REQUIRE last until this lexical body exits.
        // Always release them on errors and RETURN as well as normal completion;
        // guards owned by a caller or surrounding branch remain active.
        let previous = self.present.len();
        let previous_kinds = self.narrowed.len();
        let outcome = (|| {
            for statement in statements {
                self.depth(depth, &statement.span)?;
                if !matches!(statement.kind, StatementKind::ExpectFailure { .. }) {
                    self.context.charge(&statement.span)?;
                }
                match &statement.kind {
                    StatementKind::ExpectFailure { action, code } => {
                        self.expect_failure(action, code, &statement.span, frame, depth)?;
                    }
                    StatementKind::Traverse {
                        iteration,
                        body,
                        otherwise,
                    } => {
                        if let Some(returned) = self.traverse(
                            iteration,
                            body,
                            otherwise.as_ref(),
                            frame,
                            &statement.span,
                            depth,
                        )? {
                            return Ok(Some(returned));
                        }
                    }
                    StatementKind::Return { value, ty } => {
                        let (value, input) = self.expression(value, frame)?;
                        let value = normalize(ty, Some(&value.json()), &statement.span)?;
                        let event = self.context.record(
                            &statement.span,
                            "return".into(),
                            vec![input],
                            value.json(),
                            None,
                        )?;
                        return Ok(Some(Returned { value, event }));
                    }
                    StatementKind::Depending { .. } => {
                        if let Some(returned) = self.depending(statement, frame, depth)? {
                            return Ok(Some(returned));
                        }
                    }
                    StatementKind::ValueDepending { .. } => {
                        if let Some(returned) = self.depending_value(statement, frame, depth)? {
                            return Ok(Some(returned));
                        }
                    }
                    StatementKind::Branch {
                        arms,
                        otherwise,
                        otherwise_span,
                        otherwise_guards,
                    } => {
                        let mut selected = false;
                        for (index, arm) in arms.iter().enumerate() {
                            let test = &arm.condition;
                            let (value, event) = self.expression(test, frame)?;
                            let Value::Boolean(matches) = value else {
                                unreachable!("checked condition")
                            };
                            self.context.record(
                                &test.expression.span,
                                "branch".into(),
                                vec![event],
                                json!({"selected":matches}),
                                None,
                            )?;
                            if matches {
                                for later in &arms[index + 1..] {
                                    self.context.record(
                                        &later.condition.expression.span,
                                        "branch skipped".into(),
                                        Vec::new(),
                                        Json::Null,
                                        Some(later.condition.expression.span.clone()),
                                    )?;
                                }
                                if let Some(span) = otherwise_span {
                                    self.context.record(
                                        span,
                                        "branch skipped".into(),
                                        Vec::new(),
                                        Json::Null,
                                        Some(span.clone()),
                                    )?;
                                }
                                if let Some(returned) =
                                    self.guarded_body(&arm.body, &arm.guards, frame, depth + 1)?
                                {
                                    return Ok(Some(returned));
                                }
                                selected = true;
                                break;
                            }
                        }
                        if !selected {
                            if let Some(span) = otherwise_span {
                                self.context.record(
                                    span,
                                    "else selected".into(),
                                    Vec::new(),
                                    Json::Bool(true),
                                    None,
                                )?;
                            }
                            if let Some(returned) =
                                self.guarded_body(otherwise, otherwise_guards, frame, depth + 1)?
                            {
                                return Ok(Some(returned));
                            }
                        }
                    }
                    StatementKind::Call {
                        behavior,
                        arguments,
                        destination,
                    } => {
                        self.depth(depth, &statement.span)?;
                        let behavior = &self.program.behaviors[*behavior];
                        let mut callee =
                            self.prepare_call(behavior, arguments, frame, &statement.span)?;
                        let returned = self.body(&behavior.body, &mut callee, depth + 1)?;
                        if behavior.returns.is_some() != returned.is_some() {
                            return Err(Diagnostic::new(
                                "internal_invariant",
                                "checked return contract was not fulfilled",
                                &statement.span,
                            ));
                        }
                        let mut completion = json!({"signature":behavior.signature.join(" ")});
                        if let Some(returned) = &returned {
                            completion["returned"] = returned.value.json();
                        }
                        let event = self.context.record(
                            &statement.span,
                            "leave behavior".into(),
                            returned
                                .as_ref()
                                .map_or_else(Vec::new, |returned| vec![returned.event]),
                            completion,
                            None,
                        )?;
                        if let Some((slot, name)) = destination {
                            let value = returned.expect("checked returning call").value;
                            self.context.record(
                                &statement.span,
                                "initialize".into(),
                                vec![event],
                                json!({"path":name,"after":value.json()}),
                                None,
                            )?;
                            frame.slots[*slot].label = name.clone();
                            frame.slots[*slot].write(value, &statement.span)?;
                        }
                    }
                    StatementKind::Request {
                        request,
                        inputs,
                        outputs,
                    } => {
                        let request = &self.program.requests[*request];
                        let mut callee = Frame::new(request.slots);
                        for (caller_slot, (_, callee_slot)) in inputs.iter().zip(&request.inputs) {
                            callee.slots[*callee_slot] = frame.slots[*caller_slot].clone();
                        }
                        self.request(request, &mut callee, &statement.span, depth)?;
                        for (caller_slot, (parameter, callee_slot)) in
                            outputs.iter().zip(&request.outputs)
                        {
                            let value = callee.slots[*callee_slot].read(&parameter.span)?;
                            frame.slots[*caller_slot].label = parameter.name.clone();
                            frame.slots[*caller_slot].write(value, &parameter.span)?;
                        }
                    }
                    StatementKind::Initialize { .. }
                    | StatementKind::InitializeField { .. }
                    | StatementKind::Set { .. }
                    | StatementKind::Change { .. }
                    | StatementKind::RoundedDivision { .. }
                    | StatementKind::Aggregate { .. }
                    | StatementKind::Assert(_, _)
                    | StatementKind::Print(_)
                    | StatementKind::ExpectPrints(_)
                    | StatementKind::Pass => self.simple_step(statement, frame)?,
                }
                self.protect(&statement.continuation_guards, frame);
            }
            Ok(None)
        })();
        self.present.truncate(previous);
        self.narrowed.truncate(previous_kinds);
        outcome
    }
    // Non-recursive statements have their own stack frame. Keep collection
    // aggregation and value construction out of recursive control-flow frames.
    fn simple_step(&mut self, statement: &Statement, frame: &mut Frame) -> Result<()> {
        match &statement.kind {
            StatementKind::InitializeField { place, value } => {
                let (value, inputs) = self.initializer(value, frame)?;
                self.mutate(
                    &frame.place(place),
                    place,
                    value,
                    inputs,
                    "initialize field",
                    &statement.span,
                )?;
            }
            StatementKind::Initialize {
                slot,
                name,
                ty,
                value,
            } => {
                let (value, inputs) = self.initializer(value, frame)?;
                let value = normalize(ty, Some(&value.json()), &statement.span)?;
                self.context.record(
                    &statement.span,
                    "initialize".into(),
                    inputs,
                    json!({"path":name,"after":value.json()}),
                    None,
                )?;
                frame.slots[*slot].label = name.clone();
                frame.slots[*slot].write(value, &statement.span)?;
            }
            StatementKind::RoundedDivision {
                left,
                right,
                scale,
                mode,
                place,
            } => {
                let (left, left_event) = self.expression(left, frame)?;
                let (right, right_event) = self.expression(right, frame)?;
                let value =
                    crate::rounded_division::divide(&left, &right, *scale, *mode, &statement.span)?;
                let event = self.context.record(
                    &statement.span,
                    "rounded division".into(),
                    vec![left_event, right_event],
                    json!({"scale":scale,"mode":mode.name(),"result":value.json()}),
                    None,
                )?;
                self.mutate(
                    &frame.place(place),
                    place,
                    value,
                    vec![event],
                    "set",
                    &statement.span,
                )?;
            }
            StatementKind::Set { place, value } => {
                let (value, event) = self.expression(value, frame)?;
                let target = frame.place(place);
                self.mutate(&target, place, value, vec![event], "set", &statement.span)?;
            }
            StatementKind::Change {
                operation,
                place,
                value,
            } => {
                let (value, event) = self.expression(value, frame)?;
                let target = frame.place(place);
                self.check_mutation(&target, &statement.span)?;
                let before = target.read(&place.span)?;
                let (after, name) = match operation {
                    Change::Add => (
                        checked_numeric(
                            before.rational().expect("checked number")
                                + value.rational().expect("checked number"),
                            &place.ty,
                            &statement.span,
                        )?,
                        "add",
                    ),
                    Change::Subtract => (
                        checked_numeric(
                            before.rational().expect("checked number")
                                - value.rational().expect("checked number"),
                            &place.ty,
                            &statement.span,
                        )?,
                        "subtract",
                    ),
                    Change::Append => {
                        let Value::List(mut items) = before else {
                            unreachable!("checked list")
                        };
                        let Type::List(item_type) = &place.ty else {
                            unreachable!("checked list")
                        };
                        items.push(normalize(item_type, Some(&value.json()), &statement.span)?);
                        (Value::List(items), "append")
                    }
                };
                self.mutate(&target, place, after, vec![event], name, &statement.span)?;
            }
            StatementKind::Aggregate {
                source,
                projection,
                place,
                sum,
            } => {
                let (value, source_event) = self.expression(source, frame)?;
                let Value::List(items) = value else {
                    unreachable!("checked collection")
                };
                let mut events = vec![source_event];
                let value = if *sum {
                    let mut total = BigRational::zero();
                    for (index, item) in items.into_iter().enumerate() {
                        self.context.charge(&statement.span)?;
                        let mut item_inputs = vec![source_event];
                        let value = if let Some((slot, name, expression)) = projection.as_deref() {
                            frame.slots[*slot] = Address {
                                cell: Rc::new(RefCell::new(Some(item))),
                                fields: Vec::new(),
                                label: format!("{name}[{index}]"),
                            };
                            let (value, event) = self.expression(expression, frame)?;
                            item_inputs.push(event);
                            value
                        } else {
                            item
                        };
                        total += value.rational().expect("checked numeric projection");
                        let subtotal = checked_numeric(total.clone(), &place.ty, &statement.span)?;
                        events.push(self.context.record(
                            &statement.span,
                            "sum item".into(),
                            item_inputs,
                            json!({"index":index,"value":value.json(),"subtotal":subtotal.json()}),
                            None,
                        )?);
                    }
                    checked_numeric(total, &place.ty, &statement.span)?
                } else {
                    Value::Integer(BigInt::from(items.len()))
                };
                self.mutate(
                    &frame.place(place),
                    place,
                    value,
                    events,
                    if *sum { "sum" } else { "count" },
                    &statement.span,
                )?;
            }
            StatementKind::Assert(test, guards) => {
                let (value, event) = self.expression(test, frame)?;
                let Value::Boolean(success) = value else {
                    unreachable!("checked condition")
                };
                self.context.record(
                    &statement.span,
                    "assert".into(),
                    vec![event],
                    Json::Bool(success),
                    None,
                )?;
                if !success {
                    return Err(Diagnostic::new(
                        "assertion_failed",
                        "assertion was false",
                        &statement.span,
                    ));
                }
                self.protect(guards, frame);
            }
            StatementKind::Print(expression) => {
                let (value, event) = self.expression(expression, frame)?;
                self.context.record(
                    &statement.span,
                    "print".into(),
                    vec![event],
                    value.json(),
                    None,
                )?;
                self.output.push(value.json());
            }
            StatementKind::ExpectPrints(expected) => {
                let matched = &self.output == expected;
                let inputs = self
                    .context
                    .events
                    .iter()
                    .filter(|event| event.operation == "print")
                    .map(|event| event.sequence)
                    .collect();
                self.context.record(
                    &statement.span,
                    "assert prints".into(),
                    inputs,
                    json!({"matched":matched,"expected":expected,"actual":self.output}),
                    None,
                )?;
                if !matched {
                    return Err(Diagnostic::new(
                        "print_assertion_failed",
                        "captured output did not match the expected sequence",
                        &statement.span,
                    ));
                }
            }
            StatementKind::Pass => {
                self.context.record(
                    &statement.span,
                    "pass".into(),
                    Vec::new(),
                    Json::Null,
                    None,
                )?;
            }
            StatementKind::Return { .. }
            | StatementKind::ExpectFailure { .. }
            | StatementKind::Traverse { .. }
            | StatementKind::Branch { .. }
            | StatementKind::Depending { .. }
            | StatementKind::ValueDepending { .. }
            | StatementKind::Call { .. }
            | StatementKind::Request { .. } => unreachable!("control flow is handled by body"),
        }
        Ok(())
    }

    fn expect_failure(
        &mut self,
        action: &Statement,
        code: &str,
        span: &Span,
        frame: &mut Frame,
        depth: usize,
    ) -> Result<()> {
        let start = self.context.events.len();
        let outcome = self.body(std::slice::from_ref(action), frame, depth);
        let actual = match outcome {
            Err(error) if !crate::failure_expectation::supported(&error.code) => return Err(error),
            Err(error) => Some(error),
            Ok(_) => None,
        };
        // The annotation is checked after the action, with no rollback or budget reset.
        self.context.charge(span)?;
        let matched = actual.as_ref().is_some_and(|error| error.code == code);
        let inputs = self.context.events[start..]
            .iter()
            .map(|event| event.sequence)
            .collect();
        self.context.record(
            span,
            "assert failure".into(),
            inputs,
            json!({"matched":matched,"expectedCode":code,"actual":actual,"action":action.span}),
            None,
        )?;
        if !matched {
            return Err(Diagnostic::new(
                "failure_assertion_failed",
                format!(
                    "expected {code}, observed {}",
                    actual
                        .as_ref()
                        .map_or("successful completion", |error| error.code.as_str())
                ),
                span,
            ));
        }
        Ok(())
    }
}
