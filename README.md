# GWT

GWT is a small experimental programming language built around executable
`GIVEN / WHEN / THEN` programs.

```gwt
PROGRAM bank

GIVEN account.balance is 100
AND account.status is "open"

WHEN withdraw amount from account
  REQUIRE account.status is "open"
  AND account.balance is at least amount
  subtract amount from account.balance

WHEN withdraw 30 from account

THEN account.balance is 70
AND account.status is "open"
```

Records can group related state:

```gwt
GIVEN account is
  balance: 100
  status: "open"

THEN account is
  balance: 70
  status: "open"
```

In this first version:

- `GIVEN` initializes program state.
- `AND` continues the previous `GIVEN`, `WHEN`, `THEN`, or behavior statement.
- Block-form `WHEN` defines reusable behavior.
- Single-line `WHEN` executes behavior or statements.
- `THEN` asserts the final observable state.
- `REQUIRE` guards behavior execution.
- `LET`, `RETURN`, `IF`/`ELSE`, and `FOR` make behavior programmable.
- `SCENARIO`, `BACKGROUND`, and `EXAMPLES` support BDD-style runs.
- `USE` imports reusable behavior from another GWT file.
- `DTO` declares header-like contracts for request/state records.
- Behavior contracts type parameters and return values with `GIVEN` and
  `THEN returns`.

Run an example:

```sh
python -m gwtlang run examples/bank.gwt
```

Run multiple scenarios:

```sh
python -m gwtlang test examples/scenarios.gwt
```

Run the record example:

```sh
python -m gwtlang run examples/records.gwt --json
```

Run the local binding example:

```sh
python -m gwtlang run examples/let.gwt --json
```

Run the control-flow example:

```sh
python -m gwtlang run examples/control_flow.gwt --json
```

Run the return-value example:

```sh
python -m gwtlang run examples/return_values.gwt --json
```

Run the examples-table scenario:

```sh
python -m gwtlang test examples/examples_table.gwt
```

Run an imported module example:

```sh
python -m gwtlang run examples/use_import.gwt --json
```

Run the collections example:

```sh
python -m gwtlang run examples/collections.gwt --json
```

Run the DTO contract example:

```sh
python -m gwtlang run examples/dto_contracts.gwt --json
```

Run the typed behavior contract example:

```sh
python -m gwtlang run examples/typed_contracts.gwt --json
```

Run a reusable workflow with a GWT-shaped request file:

```sh
python -m gwtlang run examples/checkout_app.gwt --input examples/requests/checkout_request.gwt --json
```

Run checkout regression scenarios:

```sh
python -m gwtlang test examples/checkout_scenarios.gwt
```

Install a local `gwt` command:

```sh
python -m pip install -e .
gwt run examples/bank.gwt
gwt test examples/checkout_scenarios.gwt
gwt check examples/checkout_app.gwt
gwt lsp
```

`gwt check` parses a program and runs semantic checks without executing
scenarios. It reports problems such as unmatched behavior calls, duplicate
behavior signatures, invalid built-in statement shapes, and `LET`/`RETURN`
misuse. JSON output includes diagnostic codes, source ranges, and symbols for
future editor tooling.

`gwt lsp` starts a minimal Language Server Protocol server over stdio. It
publishes diagnostics and supports document symbols, hover, go-to-definition for
behavior calls, and completions for known language symbols.

The same analysis layer is available from Python:

```python
from gwtlang import analyze_source

analysis = analyze_source(source, "example.gwt")
print(analysis.diagnostics)
print(analysis.symbols)
```

Expression example:

```gwt
GIVEN account.balance is 100
AND fee is 3

WHEN withdraw amount from account
  LET total be amount + fee
  REQUIRE account.balance >= total
  subtract total from account.balance

WHEN withdraw 30 from account

THEN account.balance == 67
```

Run tests:

```sh
python -m unittest discover
```

See [docs/language.md](docs/language.md) for the language draft.
