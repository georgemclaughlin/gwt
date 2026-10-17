# Python maintenance contract

Return one complete Python 3.11+ source file defining `decide(state: dict) -> dict`.
The input and output JSON shapes are given by the starter and public examples.
Keep the function deterministic. The host supplies normalized facts; no network,
filesystem, clock, or third-party package is needed. Return the decision object,
not a CLI envelope. You may include ordinary assertions or a `__main__` test
block; the scorer independently calls `decide` over held-out inputs.

For example, a different domain might expose:

```python
def decide(state: dict) -> dict:
    order = state["order"]
    return {"shipping": {"free": order["subtotal"] >= 100}}
```

Ask about missing business policy instead of silently inventing an exception.
