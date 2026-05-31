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

Run an example:

```sh
python -m gwtlang examples/bank.gwt
```

Run multiple scenarios:

```sh
python -m gwtlang examples/scenarios.gwt --json
```

Run the record example:

```sh
python -m gwtlang examples/records.gwt --json
```

Run the local binding example:

```sh
python -m gwtlang examples/let.gwt --json
```

Run the control-flow example:

```sh
python -m gwtlang examples/control_flow.gwt --json
```

Run the return-value example:

```sh
python -m gwtlang examples/return_values.gwt --json
```

Run the examples-table scenario:

```sh
python -m gwtlang examples/examples_table.gwt --json
```

Run an imported module example:

```sh
python -m gwtlang examples/use_import.gwt --json
```

Run the collections example:

```sh
python -m gwtlang examples/collections.gwt --json
```

Run a reusable workflow with a GWT-shaped request file:

```sh
python -m gwtlang examples/checkout_app.gwt --input examples/requests/checkout_request.gwt --json
```

Run checkout regression scenarios:

```sh
python -m gwtlang examples/checkout_scenarios.gwt --json
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
