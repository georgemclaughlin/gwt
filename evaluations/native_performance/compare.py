"""Verify matching workloads/observations, then summarize development timings."""

import argparse
import json
import math
import statistics


def load(path):
    with open(path, encoding="utf-8") as source:
        report = json.load(source)
    assert report["kind"] == "gwt.development-performance"
    assert report["schemaVersion"] == 1
    assert report["iterations"] > 0 and report["batches"] > 0
    return report


def summarize(before, after):
    assert before["iterations"] == after["iterations"]
    assert before["batches"] == after["batches"]
    assert len(before["workloads"]) == len(after["workloads"])
    rows = []
    observations = 0
    for old, new in zip(before["workloads"], after["workloads"], strict=True):
        # Every non-timing field must match, including full execution hashes at
        # all tested step/evidence budgets, original source/input, and expected result.
        assert {k: v for k, v in old.items() if k != "nsPerOperation"} == {
            k: v for k, v in new.items() if k != "nsPerOperation"
        }, f"workload or execution changed: {old['name']}"
        observations += 1 + len(old["budgetObservations"])
        timings = {}
        for phase in ["compile", "run", "serialize"]:
            values = []
            for report in [old, new]:
                samples = report["nsPerOperation"][phase]
                assert len(samples) == before["batches"]
                assert all(math.isfinite(v) and v > 0 for v in samples)
                values.append({
                    "medianUs": statistics.median(samples) / 1000,
                    "minUs": min(samples) / 1000,
                    "maxUs": max(samples) / 1000,
                })
            timings[phase] = {
                "before": values[0], "after": values[1],
                "beforeOverAfter": values[0]["medianUs"] / values[1]["medianUs"],
            }
        rows.append({"name": old["name"], "timings": timings})
    return {
        "kind": "gwt.development-performance-comparison",
        "schemaVersion": 1,
        "beforeEngine": before["engine"], "afterEngine": after["engine"],
        "iterations": before["iterations"], "batches": before["batches"],
        "matchingObservations": observations, "workloads": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    print(json.dumps(summarize(load(args.before), load(args.after)), indent=2))


if __name__ == "__main__":
    main()
