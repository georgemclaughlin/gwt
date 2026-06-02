# MiniLang Executable Spec

This example uses GWT to drive a tiny scripting-language pipeline. It is not a
full self-hosted interpreter; the source has fixture-provided tokens and AST
records so GWT can focus on executable specification:

```txt
source fixture
  -> token checks
  -> AST shape checks
  -> evaluator state transitions
  -> diagnostics
  -> JSON/CLI output
```

The MiniLang sample being specified is:

```txt
let x = 10
let y = 20

fn add(a, b) {
    return a + b
}

if add(x, y) > 25 {
    print("large")
} else {
    print("small")
}

let nums = [1, 2, 3, 4]
print(map(nums, fn(n) { return n * 2 }))
```

`rules.gwt` models tokens, one-of AST statements, list literals, runtime
bindings, outputs, and errors as records. The evaluator handles the sample's
specific statement kinds, mutates bindings, and produces:

```txt
runtime.outputs == ["large"]
runtime.mapped_numbers == [2, 4, 6, 8]
runtime.status == "passed"
```

The second embedded scenario intentionally omits the `print_map_double` AST
node. That keeps parser/front-end failure explicit:

```txt
front_end.errors == ["missing_print_map_double", "unexpected_statement_count"]
runtime.errors == ["parse_failed"]
```

## Commands

Static check only:

```sh
python -m gwtlang check examples/minilang_spec/rules.gwt
```

Run embedded scenarios:

```sh
python -m gwtlang test examples/minilang_spec/rules.gwt
```

Run with production-style JSON input:

```sh
python -m gwtlang run examples/minilang_spec/rules.gwt \
  --json-input examples/minilang_spec/request.json \
  --entry "run source through front_end into runtime" \
  --json
```

## What This Stresses

- records as token, AST, runtime, and diagnostic models
- one-of records for lightweight tagged statement data
- keyed lookup and mutation with `FIND`
- explicit no-op success branches with `PASS`
- ordered evaluation over AST records
- explicit front-end and runtime errors
- JSON host input and output contracts
- current lack of source-text string scanning inside GWT itself

The one-of statement shape is captured in
[`../../docs/variant-match-design.md`](../../docs/variant-match-design.md).
