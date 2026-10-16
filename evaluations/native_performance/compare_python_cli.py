"""Measure fresh Python/Rust CLI invocations on three shared, fixed policies.

This compares the current CLI products, including their different evidence and
JSON envelopes. It does not isolate evaluator speed or normalize those costs.
"""
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKLOADS = [
    dict(name="invoice", source="crates/gwt-core/tests/fixtures/invoice.gwt",
         input="crates/gwt-core/tests/fixtures/invoice-input.json", request="price invoice",
         expected={"decision": {"status": "priced", "total": "47.88"}}),
    dict(name="member-pricing", source="examples/native_return_values/rules.gwt",
         input="examples/native_return_values/input.json", request="quote order",
         expected={"quote": {"total": "35.91"}}),
    dict(name="fulfillment", source="examples/order_fulfillment/rules.gwt",
         input="examples/order_fulfillment/request.json", request="fulfill order",
         expected={"fulfillment": {"backordered_units": "1", "cable_backordered": "0",
                   "cable_reserved": "1", "gadget_backordered": "1", "gadget_reserved": "1",
                   "package_count": "1", "reason": "partial_inventory", "requested_units": "4",
                   "reserved_units": "3", "shipping_fee": "19.5", "status": "partial",
                   "unknown_sku_count": "0", "widget_backordered": "0", "widget_reserved": "1"},
                   "inventory": {"cable_available": "4", "cable_reserved": "1",
                   "gadget_available": "0", "gadget_reserved": "1",
                   "widget_available": "4", "widget_reserved": "1"}}),
]


def normalize_result(name, result):
    """Normalize only declared numeric output fields, never arbitrary text."""
    normalized = json.loads(json.dumps(result))
    for record in normalized.values():
        for field, value in record.items():
            numeric = field == "total" if name != "fulfillment" else field not in ("reason", "status")
            if numeric:
                assert not isinstance(value, bool)
                record[field] = str(Decimal(str(value)).normalize())
    return normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True, help="Optimized Rust executable")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30, help="Samples per engine/workload/pass")
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("at least three samples are required")
    native = args.native.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    source_hashes = {}
    for directory in [ROOT / "gwtlang", ROOT / "crates/gwt-core/src"]:
        for file in sorted(directory.rglob("*")):
            if file.is_file() and file.suffix in (".py", ".rs", ".html"):
                source_hashes[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    for row in WORKLOADS:
        for field in ("source", "input"):
            file = ROOT / row[field]
            source_hashes[row[field]] = hashlib.sha256(file.read_bytes()).hexdigest()
        assert "USE " not in (ROOT / row["source"]).read_text(), "Snapshot imported source too"
    metadata = {"python": sys.version, "platform": platform.platform(),
                "native": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                "nativeVersion": json.loads(subprocess.check_output([str(native), "version"])),
                "rustCompiler": subprocess.check_output(["rustc", "+1.96.0", "-Vv"], text=True),
                "sourceSha256": source_hashes, "workloads": WORKLOADS,
                "samplesPerPass": args.samples, "passes": 2, "warmupsPerEngineWorkload": 3,
                "scope": "fresh CLI process; Python default JSON versus Rust full execution evidence"}
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    observations, commands, samples, baseline_bytes = {}, {}, [], {}

    def run(row, engine):
        key = row["name"] + "/" + engine
        command = ([str(native), "run", row["source"], "--request", row["request"], "--input", row["input"]]
                   if engine == "rust" else [sys.executable, "-m", "gwtlang", "run", row["source"],
                                             "--request", row["request"], "--json-input", row["input"], "--json"])
        started = time.perf_counter_ns()
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=15)
        elapsed = (time.perf_counter_ns() - started) / 1e6
        assert completed.returncode == 0, completed.stderr.decode()
        payload = json.loads(completed.stdout)
        assert payload["ok"] is True
        assert normalize_result(row["name"], payload["result"]) == row["expected"]
        if key in baseline_bytes:
            assert completed.stdout == baseline_bytes[key], "Within-engine observation changed"
        else:
            baseline_bytes[key] = completed.stdout
            observations[key] = payload
            commands[key] = command
        return {"workload": row["name"], "engine": engine, "milliseconds": elapsed,
                "stdoutBytes": len(completed.stdout), "stdoutSha256": hashlib.sha256(completed.stdout).hexdigest()}

    for row in WORKLOADS:
        for _ in range(3):
            for engine in ("python", "rust"):
                run(row, engine)
    with (args.output / "samples.jsonl").open("w") as log:
        for pass_index in range(2):
            for index in range(args.samples):
                for row_index, row in enumerate(WORKLOADS):
                    order = ("python", "rust") if (index + row_index + pass_index) % 2 == 0 else ("rust", "python")
                    for engine in order:
                        sample = {**run(row, engine), "pass": pass_index + 1, "sample": index + 1}
                        log.write(json.dumps(sample) + "\n"); log.flush()
                        samples.append(sample)
    assert hashlib.sha256(native.read_bytes()).hexdigest() == metadata["nativeSha256"]
    for file, digest in source_hashes.items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, file
    summary = []
    for row in WORKLOADS:
        values = {}
        for engine in ("python", "rust"):
            timings = [s["milliseconds"] for s in samples if s["workload"] == row["name"] and s["engine"] == engine]
            values[engine] = {"medianMs": statistics.median(timings), "minimumMs": min(timings),
                              "maximumMs": max(timings), "passMediansMs": [statistics.median(
                                  s["milliseconds"] for s in samples if s["workload"] == row["name"]
                                  and s["engine"] == engine and s["pass"] == p) for p in (1, 2)]}
        summary.append({"workload": row["name"], **values,
                        "pythonOverRustMedianRatio": values["python"]["medianMs"] / values["rust"]["medianMs"]})
    report = {"completed": True, "timedInvocations": len(samples), "summary": summary,
              "allIndependentResultsMatched": True, "withinEngineFullStdoutPreserved": True,
              "observations": observations, "commands": commands}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
