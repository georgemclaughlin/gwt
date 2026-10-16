"""Independent typed-boundary expectations and explicit legacy differences."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from gwtlang import GwtError
from gwtlang.runtime import Runtime, parse_program


SOURCE = Path("examples/input_normalization/rules.gwt")
REQUEST = "normalize contact profile"
OMITTED = object()


def probes():
    for index, (name, email, state, middle) in enumerate(itertools.product(
            ("", "Ada"), ("", "ada@example.com"),
            ("provided", "missing", "not_applicable", "unrecognized"),
            (OMITTED, None, "", "Lovelace"))):
        raw = {"name": name, "email": email, "middle_name_state": state}
        if middle is not OMITTED:
            raw["middle_name"] = middle
        yield f"valid-shape-{index:02d}", {"raw": raw}
    baseline = {"raw": {"name": "Ada", "email": "ada@example.com", "middle_name_state": "missing"}}
    for field in ("name", "email", "middle_name_state"):
        for index, value in enumerate((OMITTED, None, True, 0, [], {})):
            case = deepcopy(baseline)
            if value is OMITTED:
                del case["raw"][field]
            else:
                case["raw"][field] = value
            yield f"bad-{field}-{index}", case
    for index, value in enumerate((True, 0, [], {})):
        case = deepcopy(baseline)
        case["raw"]["middle_name"] = value
        yield f"unused-wrong-middle-{index}", case
    yield "extra-root", {**deepcopy(baseline), "metadata": "outside the request"}
    case = deepcopy(baseline)
    case["raw"]["metadata"] = "outside the raw contract"
    yield "extra-raw", case
    for index, value in enumerate((None, [], "raw", 0, True)):
        yield f"raw-wrong-kind-{index}", {"raw": value}
    yield "missing-raw", {}


def expected(value):
    """Closed native boundary, then the existing contact policy, independently specified."""
    if set(value) != {"raw"} or not isinstance(value["raw"], dict):
        return {"kind": "boundary_rejected"}
    raw = value["raw"]
    required = {"name", "email", "middle_name_state"}
    if not required <= set(raw) <= required | {"middle_name"}:
        return {"kind": "boundary_rejected"}
    if any(type(raw[key]) is not str for key in required):
        return {"kind": "boundary_rejected"}
    if raw.get("middle_name") is not None and type(raw["middle_name"]) is not str:
        return {"kind": "boundary_rejected"}
    state = raw["middle_name_state"]
    if state == "provided" and raw.get("middle_name") is None:
        return {"kind": "behavior_rejected", "code": "assertion_failed"}
    errors = [code for field, code in (("name", "missing_name"), ("email", "missing_email")) if raw[field] == ""]
    if state not in ("provided", "missing", "not_applicable"):
        errors.append("invalid_middle_name_state")
    profile = {"name": raw["name"], "email": raw["email"],
               "middle_name_status": state if state in ("provided", "not_applicable") else "missing",
               "middle_name": raw["middle_name"] if state == "provided" else "",
               "errors": errors, "error_count": len(errors), "status": "invalid" if errors else "normalized"}
    return {"kind": "result", "profile": profile}


def observe_python(runtime, value):
    try:
        profile = runtime.run_json(deepcopy(value), REQUEST).scenarios[0].returned_state["profile"]
        return {"kind": "result", "profile": profile}
    except GwtError as error:
        return {"kind": "rejected", "message": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    before, after = args.before.read_text(), SOURCE.read_text()
    old = Runtime(parse_program(before, filename=str(args.before)))
    new = Runtime(parse_program(after, filename=str(SOURCE)))
    rows = []
    with tempfile.TemporaryDirectory(prefix="gwt-typed-input-") as work:
        path = Path(work) / "input.json"
        for name, value in probes():
            oracle = expected(value)
            old_result, new_result = observe_python(old, value), observe_python(new, value)
            if name.startswith("valid-shape"):
                if oracle["kind"] == "result":
                    assert old_result == oracle and new_result == oracle, (name, oracle, old_result, new_result)
                else:
                    assert old_result["kind"] == new_result["kind"] == "rejected", name
            path.write_text(json.dumps(value))
            process = subprocess.run([str(native), "run", str(SOURCE), "--request", REQUEST,
                                      "--input", str(path)], capture_output=True, text=True, timeout=15)
            assert process.returncode in (0, 1), process.stderr
            actual = json.loads(process.stdout)
            if oracle["kind"] == "result":
                profile = {**oracle["profile"], "error_count": str(oracle["profile"]["error_count"])}
                assert actual["ok"] and actual["result"] == {"profile": profile}, name
            else:
                assert not actual["ok"] and actual["result"] is None, name
                if oracle["kind"] == "boundary_rejected":
                    assert actual["state"] == {} and actual["events"] == [], name
                else:
                    assert actual["diagnostic"]["code"] == oracle["code"], name
                    assert actual["state"]["profile"]["middle_name_status"] == "missing", name
            rows.append({"id": name, "input": value, "expectedNative": oracle,
                         "pythonBefore": old_result, "pythonAfter": new_result, "native": actual})
    assert len(rows) == 94
    report = {"cases": len(rows), "executions": len(rows) * 3,
              "expectedNative": dict(Counter(r["expectedNative"]["kind"] for r in rows)),
              "pythonBefore": dict(Counter(r["pythonBefore"]["kind"] for r in rows)),
              "pythonAfter": dict(Counter(r["pythonAfter"]["kind"] for r in rows)),
              "pythonAcceptanceChanges": [r["id"] for r in rows if r["pythonBefore"]["kind"] != r["pythonAfter"]["kind"]],
              "nativePythonAcceptanceDifferences": [r["id"] for r in rows if r["native"]["ok"] != (r["pythonAfter"]["kind"] == "result")],
              "beforeSha256": hashlib.sha256(before.encode()).hexdigest(),
              "afterSha256": hashlib.sha256(after.encode()).hexdigest(),
              "nativeExecutable": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
              "pythonRuntimeSha256": hashlib.sha256(Path("gwtlang/runtime.py").read_bytes()).hexdigest(),
              "humanParticipants": 0}
    (args.output / "observations.json").write_text(json.dumps(rows, indent=2) + "\n")
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
