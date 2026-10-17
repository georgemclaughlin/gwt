# GWT Project Goal

Evolve GWT into a language and toolchain that makes software behavior easy for
humans to understand, verify, and change in collaboration with AI, supported by
a deliberately designed Rust foundation.

GWT should let people express domain policies as readable, executable
specifications. The same source should define behavior, illustrate its intent
through examples, explain individual decisions, and reveal the consequences of
proposed changes. AI should help author and maintain these specifications,
while people retain a practical ability to understand and approve what they do.

## Objectives

### 1. Make human understanding the primary design criterion

Evaluate syntax and tooling by how well people can explain a rule, identify
ambiguity, recognize mistakes, and assess a change. Favor domain vocabulary,
explicit decisions, focused behaviors, and concrete examples.

### 2. Define GWT's semantics independently of its implementation

Review the existing language and distinguish intentional design from
Python-driven convenience. Specify types, numbers, missing values, state
changes, evaluation order, contracts, and failures explicitly. Revise awkward
behavior where doing so makes GWT clearer, recording deliberate
incompatibilities and migration examples.

### 3. Build a coherent Rust foundation

Develop a parser, checker, and execution engine around a shared program
representation that retains source locations and resolved meaning. Make
diagnostics and execution evidence part of that foundation. Use the Python
implementation as a source of lessons and comparison cases wherever its
behavior remains intentional.

Distinguish implementing GWT in Rust from compiling GWT programs into Rust.
Build the native foundation first; assess generated Rust or other compilation
targets when a concrete deployment need justifies them. Preserve GWT's readable
domain language regardless of the implementation or compilation target.

### 4. Make behavioral review a complete workflow

Connect specification editing, scenario validation, representative input
capture, decision explanation, revision comparison, and human review.
Reviewers should be able to establish what changed, which cases it affects,
why outcomes differ, and what remains uncertain.

### 5. Support practical adoption and deployment

Provide clear host-language boundaries, useful editor support, reproducible
execution, and straightforward packaging. Assess native libraries, standalone
executables, and browser execution against concrete integration needs. Keep
external systems responsible for persistence, networking, and other effects
around the domain rules.

### 6. Demonstrate the value with evidence

Test unrelated domains, substantial maintenance tasks, and AI-authored changes.
Compare human comprehension, review time, detected mistakes, and maintenance
effort against ordinary code. Measure runtime performance separately. Use
findings to guide language changes and product investment.

## Agreed Scope

- Retain the GWT name for now and use the MIT license.
- Preserve the executable `GIVEN / WHEN / THEN` identity while allowing deliberate
  language redesign where it improves understanding and correctness.
- Treat compatibility with Python-driven conventions as a design decision,
  rather than an automatic requirement.
- Keep external pilots pending until a workflow and participating maintainer
  are chosen. Local validation does not establish a benefit for human reviewers.

This document describes the intended destination. Implementation status and
remaining evidence are tracked in [project-goal-progress.md](project-goal-progress.md).

## Completion Criteria

Completion should mean more than having a Rust implementation:

- GWT has a documented, intentional execution model.
- Its implementation passes independent conformance tests.
- Its explanations accurately reflect execution.
- Representative users can understand and review meaningful policy changes
  with demonstrated benefit.

## Central Promise

People can understand the behavior they are putting into production, even when
AI writes most of it.
