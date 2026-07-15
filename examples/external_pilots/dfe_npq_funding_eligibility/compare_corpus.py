from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from gwtlang import GwtClient


RULES = Path(__file__).with_name("rules.gwt")
REQUEST_NAME = "assess funding eligibility"

COURSES = {
    "early headship coaching offer": "npq_early_headship_coaching_offer",
    "early years leadership": "npq_early_years_leadership",
    "executive leadership": "npq_executive_leadership",
    "headship": "npq_headship",
    "leading behaviour and culture": "npq_leading_behaviour_culture",
    "leading literacy": "npq_leading_literacy",
    "leading primary mathematics": "npq_leading_primary_mathematics",
    "leading teaching": "npq_leading_teaching",
    "leading teacher development": "npq_leading_teaching_development",
    "senior leadership": "npq_senior_leadership",
    "special educational needs co-ordinator (senco)": "npq_senco",
}

ANOTHER_SETTING_EMPLOYMENT = {
    "another setting - independent hospital education organisation": "hospital_school",
    "another setting - lead mentor for an accredited ITT provider": "lead_mentor_for_accredited_itt_provider",
    "another setting - teacher employer by an LA to teach in more than one school": "local_authority_supply_teacher",
    "another setting - virtual school": "local_authority_virtual_school",
    "another setting - young offender institution": "young_offender_institution",
}

REQUIRED_COLUMNS = {
    "Cohort",
    "Works in England",
    "Work setting",
    "NPQ",
    "Already registered for this course",
    "RISE list?",
    "PP50",
    "Expected eligibility value",
}


def value(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def normalize(row: dict[str, str]) -> dict[str, Any]:
    """Translate fixture/UI vocabulary into model-independent decision facts."""
    setting = value(row, "Work setting")
    course = COURSES[value(row, "NPQ")]

    if setting in {"school", "academy trust", "16 - 19 education setting"}:
        work_policy = "school"
    elif setting.startswith("early years or childcare - "):
        work_policy = "childcare"
    elif setting.startswith("another setting - "):
        work_policy = "another_setting"
    elif setting.startswith("other - "):
        work_policy = "other"
    else:
        raise ValueError(f"unknown work setting: {setting!r}")

    is_lead_mentor_case = (
        setting == "another setting - lead mentor for an accredited ITT provider"
        and course == "npq_leading_teaching_development"
    )

    return {
        "facts": {
            "approved_itt_provider": is_lead_mentor_case,
            "childminder": setting == "early years or childcare - childminder",
            "childminder_entitled": False,
            "cohort_funded": value(row, "Cohort") == "2026 autumn",
            "course": course,
            "employment_kind": ANOTHER_SETTING_EMPLOYMENT.get(setting, "none"),
            "inside_catchment": value(row, "Works in England") == "yes",
            "institution_eligible": work_policy == "school"
            or setting == "early years or childcare - local authority maintained nursery",
            "institution_pp50": value(row, "PP50") == "yes",
            "institution_rise": value(row, "RISE list?") == "yes",
            "local_authority_nursery": setting
            == "early years or childcare - local authority maintained nursery",
            "new_headteacher": False,
            "preschool_class_as_part_of_school": setting
            == "early years or childcare - pre-school class or nursery that's part of a school",
            "previously_funded": value(row, "Already registered for this course") == "yes",
            "referred_by_return_to_teaching_adviser": setting
            == "other - referred by a RTTA",
            "work_policy": work_policy,
        }
    }


def expected_outcome(row: dict[str, str]) -> str:
    expected = value(row, "Expected eligibility value")
    if expected in {"yes", "yes (if on ITT provider list)"}:
        return "funded"
    if expected == "subject to review":
        return "subject_to_review"
    if expected == "no":
        return "not_funded"
    raise ValueError(f"unknown expected eligibility value: {expected!r}")


def compare(csv_path: Path) -> dict[str, Any]:
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing_columns = REQUIRED_COLUMNS.difference(reader.fieldnames or ())
        if missing_columns:
            raise ValueError(f"fixture is missing columns: {sorted(missing_columns)}")
        rows = list(reader)

    compiled = GwtClient(RULES).compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    expected_counts: Counter[str] = Counter()
    actual_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    mismatches: list[dict[str, Any]] = []

    for fixture_row, row in enumerate(rows, start=2):
        expected = expected_outcome(row)
        execution = compiled.run_json(normalize(row), request=REQUEST_NAME)
        decision = execution.as_payload()["result"]["decision"]
        actual = decision["outcome"]

        expected_counts[expected] += 1
        actual_counts[actual] += 1
        status_counts[decision["status_code"]] += 1
        if actual != expected:
            mismatches.append(
                {
                    "actual": actual,
                    "expected": expected,
                    "fixture_row": fixture_row,
                    "status_code": decision["status_code"],
                    "summary": {
                        key: value(row, key)
                        for key in (
                            "Cohort",
                            "Works in England",
                            "Work setting",
                            "NPQ",
                            "Already registered for this course",
                            "RISE list?",
                            "PP50",
                            "Expected eligibility value",
                        )
                    },
                }
            )

    return {
        "actual_outcomes": dict(sorted(actual_counts.items())),
        "corpus_rows": len(rows),
        "expected_outcomes": dict(sorted(expected_counts.items())),
        "matched": len(rows) - len(mismatches),
        "mismatched": len(mismatches),
        "mismatches": mismatches,
        "modeled_status_codes": dict(sorted(status_counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the GWT pilot with the upstream NPQ eligibility CSV",
    )
    parser.add_argument(
        "csv_path",
        type=Path,
        help="explicit path to eligibility_testing_scenarios.csv in a local upstream checkout",
    )
    parser.add_argument("--json", action="store_true", help="print the full machine-readable report")
    args = parser.parse_args()

    try:
        report = compare(args.csv_path)
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"corpus rows: {report['corpus_rows']}")
        print(f"coarse outcome parity: {report['matched']}/{report['corpus_rows']}")
        print(f"mismatches: {report['mismatched']}")
        print(f"expected outcomes: {json.dumps(report['expected_outcomes'], sort_keys=True)}")
        print(f"actual outcomes: {json.dumps(report['actual_outcomes'], sort_keys=True)}")
        print(f"modeled status codes: {json.dumps(report['modeled_status_codes'], sort_keys=True)}")
        if report["mismatches"]:
            print("first mismatches:")
            print(json.dumps(report["mismatches"][:10], indent=2, sort_keys=True))

    return 1 if report["mismatched"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
