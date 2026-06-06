# MiniLang 2 Bytecode VM Executable Spec

This example turns the "MiniLang 2" pressure test into an executable GWT
fixture. It is not a full self-hosted language implementation; tokens, AST
nodes, resolver symbols, and bytecode are supplied as fixtures so the GWT
program can focus on behavior over structured state:

```txt
source fixture
  -> token and AST checks
  -> resolver / captured-variable checks
  -> bytecode shape checks
  -> VM state transitions
  -> standard library call
  -> debugger snapshot
  -> REPL continuation
  -> runtime error stack trace
```

The MiniLang program being specified is the closure counter sample:

```txt
import math

fn make_counter(start) {
    let n = start

    return fn() {
        n = n + 1
        return n
    }
}

let counter = make_counter(10)
let total = 0

for item in [1, 2, 3, 4] {
    total = total + item
}

print(counter())
print(counter())
print(math.sqrt(total))
```

The VM fixture models globals, arrays, modules, closure cells, closures, value
kinds, stack frames, debugger snapshots, and REPL history. The successful
scenario produces:

```txt
vm.outputs == [11, 12, 3.162277660168379]
repl.outputs == [13, 10]
debugger.snapshots[1].label == "after_loop"
debugger.snapshots[1].total_value == 10
debugger.snapshots[1].captured_n == 10
```

The second embedded scenario executes bytecode that reads an undefined global.
It verifies explicit runtime failure and stack-frame recording:

```txt
vm.status == "failed"
vm.errors == ["undefined_global_missing"]
```

## Commands

Static check only:

```sh
python -m gwtlang check examples/minilang2_vm/rules.gwt
```

Run embedded scenarios:

```sh
python -m gwtlang test examples/minilang2_vm/rules.gwt
```

Run with production-style JSON input:

```sh
python -m gwtlang run examples/minilang2_vm/rules.gwt \
  --json-input examples/minilang2_vm/request.json \
  --request "execute mini2 source" \
  --json
```

## What This Stresses

- one-of records for AST nodes and bytecode instructions
- resolver state and captured-variable metadata
- mutable closure cells that outlive the factory call
- module loading and a native `math.sqrt` standard library call
- array processing through explicit VM instructions
- value-category coverage for number, string, boolean, null, array, map,
  function, and closure values
- debugger snapshots over VM state
- runtime errors with structured stack frames
- REPL commands continuing from the post-program VM state
