# Deployable API Example

This example shows how a named GWT `REQUEST` can be projected into an OpenAPI
contract.

The rules file defines one public request:

```gwt
REQUEST triage ticket
  GIVEN ticket is TicketRequest
  WHEN triage ticket into decision
  OUTPUT decision is TicketDecision
```

Run the executable scenario:

```sh
python -m gwtlang test examples/deployable_api/rules.gwt
```

Generate OpenAPI:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt --json
```

Or write the document to a file for Swagger UI, Redoc, Postman, OpenAPI
Generator, or contract-test tooling:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt \
  --output /tmp/gwt-openapi.json
python -m json.tool /tmp/gwt-openapi.json >/dev/null
```

The generated API surface is:

```text
POST /requests/triage-ticket
  request body:  TriageTicketRequest
  response body: TriageTicketOutput
  GWT request:   triage ticket
```

The OpenAPI response body is the declared `OUTPUT` object. It is intentionally
not the `gwt run --json` execution envelope, which remains the CLI/debug payload
with final state and print output.

See [`../../docs/http-service-design.md`](../../docs/http-service-design.md)
for the proposed experimental `gwt serve` direction.
