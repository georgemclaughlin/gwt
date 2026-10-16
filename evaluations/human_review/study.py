"""Prepare offline review sessions and score their exported observations.

This is cooperative research tooling, not an authenticated test platform.
Synthetic sessions are explicitly segregated from participant observations.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import re
from statistics import median

from .corpus import DOMAINS, FIXTURES, GUIDES, TASKS, expected

VERSION = 1
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
INSTRUCTIONS = (
    "Review each proposed implementation against the existing policy and requested change. "
    "Predict what the proposed code actually returns for both inputs, then recommend approval, "
    "request changes, or say you are unsure. Explain your reasoning and any suspected mistake. "
    "Assume valid inputs matching the shared schema. Review source only: do not execute code, "
    "use AI, or consult outside help. A short language guide remains available. "
    "You may skip a task or stop at any time. Use Pause for interruptions. Time spent in a "
    "hidden tab is excluded from active time, but retained in wall time. Download a partial "
    "record before closing this page. Reopen this same session and load the downloaded record "
    "to continue; work since the download is not recovered. Resumed tasks are marked as "
    "interrupted and excluded from timing medians. There is no server or autosave. "
    "Advancing freezes a task's answers. The page gives no correctness feedback."
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def assignments(group):
    if type(group) is not int or not 0 <= group < 16:
        raise ValueError("group must be an integer from 0 through 15")
    order, flips = divmod(group, 4)
    language_flip, validity_flip = divmod(flips, 2)
    return [(DOMAINS[d], ("gwt", "python")[(slot + language_flip) % 2],
             "correct" if ((slot // 2 + validity_flip) % 2 == 0) else "faulty")
            for slot, d in enumerate(ORDERS[order])]


def prepare(group, assignment_id, purpose="rehearsal"):
    if purpose not in ("rehearsal", "participant"):
        raise ValueError("purpose must be rehearsal or participant")
    if not isinstance(assignment_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", assignment_id):
        raise ValueError("use an opaque assignment ID of 1–64 letters, digits, underscores or hyphens")
    tasks, answers = [], []
    for slot, (domain, language, revision) in enumerate(assignments(group)):
        spec = TASKS[domain]
        extension = "gwt" if language == "gwt" else "py"
        sources = {label: (FIXTURES / domain / f"{rev}.{extension}").read_text()
                   for label, rev in (("baseline", "baseline"), ("proposed", revision))}
        task_id = f"task-{slot + 1}"
        task = {"id": task_id, "domain": domain, "language": language,
                **{k: spec[k] for k in ("title", "policy", "change", "schema")},
                "guide": GUIDES[language], "sources": sources,
                "sourceDigests": {label: hashlib.sha256(source.encode()).hexdigest()
                                  for label, source in sources.items()}, "questions": []}
        key = {"id": task_id, "revision": revision, "predictions": {},
               "recommendation": "approve" if revision == "correct" else "request_changes",
               "rationaleRubric": "No defect: requested and preserved rules hold." if revision == "correct"
               else spec["defect"]}
        for index, (facts, options) in enumerate(zip(spec["inputs"], spec["options"]), 1):
            values = deepcopy(options)
            random.Random(digest([assignment_id, group, slot, index])).shuffle(values)
            choices = [{"id": f"c{i}", "value": {"decision": value}} for i, value in enumerate(values)]
            correct = expected(domain, revision, facts)
            matches = [choice["id"] for choice in choices if canonical(choice["value"]) == canonical(correct)]
            if len(matches) != 1:
                raise ValueError("prediction needs exactly one matching choice")
            question_id = f"q{index}"
            task["questions"].append({"id": question_id, "input": {"facts": facts}, "choices": choices})
            task["questions"][-1]["choices"].append({"id": "unsure", "value": None, "label": "I am not sure"})
            key["predictions"][question_id] = matches[0]
        tasks.append(task)
        answers.append(key)
    packet = {"schemaVersion": VERSION, "assignmentId": assignment_id, "group": group,
              "purpose": purpose, "instructions": INSTRUCTIONS, "tasks": tasks,
              "responseSchemaVersion": 2}
    packet["packetId"] = digest(packet)
    return packet, {"schemaVersion": VERSION, "packet": deepcopy(packet), "answers": answers}


def render(packet):
    template = Path(__file__).with_name("session.html").read_text()
    # Even arbitrary source strings cannot terminate the JSON script element.
    recovery = Path(__file__).with_name("session-recovery.js").read_text()
    return template.replace("__RECOVERY_JS__", recovery).replace(
        "__PACKET_JSON__", canonical(packet).replace("<", "\\u003c"))


def write_json(path, value):
    with Path(path).open("x") as file:
        file.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def validate_key(key):
    if not isinstance(key, dict) or key.get("schemaVersion") != VERSION:
        raise ValueError("unsupported key")
    packet = key["packet"]
    payload = {k: v for k, v in packet.items() if k != "packetId"}
    if packet["packetId"] != digest(payload):
        raise ValueError("packet checksum mismatch")
    if packet["schemaVersion"] != VERSION or packet["purpose"] not in ("rehearsal", "participant"):
        raise ValueError("invalid packet version or purpose")
    response_version = packet.get("responseSchemaVersion", 1)
    if type(response_version) is not int or response_version not in (1, 2):
        raise ValueError("unsupported response protocol")
    expected_assignment = assignments(packet["group"])
    if len(packet["tasks"]) != 4 or len(key["answers"]) != 4:
        raise ValueError("expected four planned tasks")
    for i, (task, answer, (domain, language, revision)) in enumerate(
            zip(packet["tasks"], key["answers"], expected_assignment), 1):
        if (task["id"], answer["id"], task["domain"], task["language"], answer["revision"]) != (
                f"task-{i}", f"task-{i}", domain, language, revision):
            raise ValueError("invalid assignment")
        for label, source in task["sources"].items():
            if hashlib.sha256(source.encode()).hexdigest() != task["sourceDigests"][label]:
                raise ValueError("source checksum mismatch")
        if answer["recommendation"] != ("approve" if revision == "correct" else "request_changes"):
            raise ValueError("invalid recommendation key")
        if [q["id"] for q in task["questions"]] != ["q1", "q2"]:
            raise ValueError("invalid questions")
        for question in task["questions"]:
            ids = [choice["id"] for choice in question["choices"]]
            if len(set(ids)) != len(ids) or answer["predictions"][question["id"]] not in ids:
                raise ValueError("invalid prediction key")
    return packet


def validate_response(packet, response):
    version = packet.get("responseSchemaVersion", 1)
    if (not isinstance(response, dict) or type(response.get("schemaVersion")) is not int
            or response["schemaVersion"] != version):
        raise ValueError("unsupported response")
    for field in ("packetId", "assignmentId", "purpose"):
        if response.get(field) != packet[field]:
            raise ValueError(f"response {field} mismatch")
    if not isinstance(response.get("responseId"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", response["responseId"]):
        raise ValueError("invalid response ID")
    profile = response.get("profile", {})
    if not isinstance(profile, dict):
        raise ValueError("invalid profile")
    if profile.get("role") not in ("developer", "domain_specialist", "other"):
        raise ValueError("missing reviewer role")
    if profile.get("priorExposure") not in ("yes", "no", "unsure"):
        raise ValueError("missing prior exposure")
    for field in ("gwtFamiliarity", "pythonFamiliarity"):
        if type(profile.get(field)) is not int or not 0 <= profile[field] <= 3:
            raise ValueError("invalid familiarity")
    rows = response.get("tasks")
    if not isinstance(rows, list) or len(rows) != len(packet["tasks"]):
        raise ValueError("all planned tasks must be present, including unseen tasks")
    pending = False
    drafts = 0
    for task, row in zip(packet["tasks"], rows):
        if not isinstance(row, dict):
            raise ValueError("invalid task response")
        if row.get("id") != task["id"] or row.get("sourceDigests") != task["sourceDigests"]:
            raise ValueError("task order or source identity mismatch")
        status = row.get("status")
        if status not in ("unseen", "draft", "submitted", "skipped"):
            raise ValueError("invalid task status")
        if pending and status != "unseen":
            raise ValueError("tasks must be completed in assigned order")
        if status in ("unseen", "draft"):
            pending = True
        drafts += status == "draft"
        if version == 2:
            resumes = row.get("resumeCount")
            if type(resumes) is not int or not 0 <= resumes <= 1_000_000:
                raise ValueError("invalid resume count")
            if status == "unseen" and resumes:
                raise ValueError("unseen tasks cannot have been resumed")
        elif "resumeCount" in row:
            raise ValueError("legacy responses cannot carry recovery metadata")
        for name in ("activeMs", "wallMs"):
            value = row.get(name)
            if status == "unseen":
                if value is not None:
                    raise ValueError("unseen tasks have no timing")
            elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid task timing")
        if status != "unseen" and row["activeMs"] > row["wallMs"]:
            raise ValueError("active time exceeds wall time")
        predictions = row.get("predictions", {})
        if not isinstance(predictions, dict) or set(predictions) != {q["id"] for q in task["questions"]}:
            raise ValueError("invalid prediction question IDs")
        for question in task["questions"]:
            value = predictions[question["id"]]
            if value is not None and value not in [c["id"] for c in question["choices"]]:
                raise ValueError("unknown prediction choice")
        if row.get("recommendation") not in (None, "approve", "request_changes", "unsure"):
            raise ValueError("invalid recommendation")
        confidence = row.get("confidence")
        if confidence is not None and (type(confidence) is not int or not 1 <= confidence <= 5):
            raise ValueError("invalid confidence")
        if not isinstance(row.get("rationale"), str) or len(row["rationale"]) > 10_000:
            raise ValueError("invalid rationale")
        if status == "unseen" and (any(v is not None for v in predictions.values())
                                 or row["recommendation"] is not None or confidence is not None or row["rationale"]):
            raise ValueError("unseen tasks cannot contain answers")
        if status == "submitted" and (any(v is None for v in predictions.values())
                                     or row["recommendation"] is None or confidence is None or not row["rationale"].strip()):
            raise ValueError("submitted tasks require all answers")
    if type(response.get("finished")) is not bool or response["finished"] != (not pending):
        raise ValueError("finished flag disagrees with task statuses")
    if version == 2 and pending and drafts != 1:
        raise ValueError("an unfinished recovery-capable response requires one draft task")


def score(keys, responses):
    packets = {}
    assignment_ids = set()
    for key in keys:
        packet = validate_key(key)
        if packet["packetId"] in packets or packet["assignmentId"] in assignment_ids:
            raise ValueError("duplicate planned assignment")
        assignment_ids.add(packet["assignmentId"])
        packets[packet["packetId"]] = key
    if not packets:
        raise ValueError("supply at least one planned assignment key")
    observed, response_ids = {}, set()
    for response in responses:
        key = packets.get(response.get("packetId"))
        if key is None:
            raise ValueError("response has no matching planned assignment")
        validate_response(key["packet"], response)
        if response["packetId"] in observed or response["responseId"] in response_ids:
            raise ValueError("duplicate response; select one explicit snapshot per assignment")
        observed[response["packetId"]] = response
        response_ids.add(response["responseId"])
    observations = []
    for packet_id, key in packets.items():
        packet, response = key["packet"], observed.get(packet_id)
        session_resumed = bool(response and any(row.get("resumeCount", 0) for row in response["tasks"]))
        for i, (task, answer) in enumerate(zip(packet["tasks"], key["answers"])):
            row = response["tasks"][i] if response else None
            submitted = row is not None and row["status"] == "submitted"
            observations.append({
                "packetId": packet_id, "assignmentId": packet["assignmentId"], "purpose": packet["purpose"],
                "taskId": task["id"], "position": i + 1, "domain": task["domain"], "language": task["language"],
                "revision": answer["revision"], "status": row["status"] if row else "missing_session",
                "profile": response["profile"] if response else None,
                "answeredPredictions": sum(v is not None for v in row["predictions"].values()) if row else 0,
                "correctPredictions": sum(row["predictions"][q] == v for q, v in answer["predictions"].items())
                if submitted else 0,
                "decisionCorrect": row["recommendation"] == answer["recommendation"] if submitted else False,
                "recommendation": row["recommendation"] if row else None,
                "rationale": row["rationale"] if row else None,
                "rationaleRubric": answer["rationaleRubric"], "rationaleAssessment": "pending_manual_review",
                "confidence": row["confidence"] if row else None,
                "activeMs": row["activeMs"] if row else None, "wallMs": row["wallMs"] if row else None,
                "resumeCount": row.get("resumeCount", 0) if row else None,
                "timingInterrupted": bool(row and row.get("resumeCount", 0)),
                "sessionResumed": session_resumed,
            })

    def summarize(rows):
        completed = [r for r in rows if r["status"] == "submitted"]
        timed = [r for r in completed if not r["timingInterrupted"]]
        return {"plannedTasks": len(rows), "statusCounts": dict(Counter(r["status"] for r in rows)),
                "plannedPredictions": 2 * len(rows), "answeredPredictionsIncludingDrafts": sum(r["answeredPredictions"] for r in rows),
                "correctSubmittedPredictions": sum(r["correctPredictions"] for r in rows),
                "correctSubmittedDecisions": sum(r["decisionCorrect"] for r in rows),
                "submittedTasks": len(completed),
                "resumedTasks": sum(r["timingInterrupted"] for r in rows),
                "resumedSessions": len({r["packetId"] for r in rows if r["sessionResumed"]}),
                "submittedTimingEligibleTasks": len(timed),
                "medianSubmittedActiveMs": median(r["activeMs"] for r in timed) if timed else None,
                "medianSubmittedWallMs": median(r["wallMs"] for r in timed) if timed else None}

    summaries = {}
    for purpose in ("participant", "rehearsal"):
        rows = [r for r in observations if r["purpose"] == purpose]
        summaries[purpose] = {"overall": summarize(rows), "byLanguage": {
            language: summarize([r for r in rows if r["language"] == language]) for language in ("gwt", "python")}}
    return {"schemaVersion": VERSION, "plannedSessions": len(keys), "receivedSessions": len(responses),
            "summaries": summaries, "observations": observations,
            "limitations": ["Descriptive observations; no superiority or statistical significance inference.",
                            "Resumed tasks retain answers and observed time segments but are excluded from timing medians; recovery gaps are unknown.",
                            "Purpose and profile are self-reported, not identity or human-participation authentication.",
                            "Correct rejection is not verified defect recognition; manually assess rationales.",
                            "Missing, skipped, draft and unseen tasks remain in planned denominators.",
                            "Times describe submitted tasks only; compare accuracy and attrition alongside time."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--group", type=int, required=True)
    prep.add_argument("--assignment", required=True)
    prep.add_argument("--purpose", choices=("rehearsal", "participant"), default="rehearsal")
    prep.add_argument("--output", type=Path, required=True)
    scoring = commands.add_parser("score")
    scoring.add_argument("--keys", type=Path, nargs="+", required=True)
    scoring.add_argument("--responses", type=Path, nargs="*", default=[])
    scoring.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        packet, key = prepare(args.group, args.assignment, args.purpose)
        args.output.mkdir(parents=True, exist_ok=False)
        write_json(args.output / "packet.json", packet)
        write_json(args.output / "facilitator-key.json", key)
        (args.output / "session.html").write_text(render(packet))
        print(f"Prepared {packet['purpose']} assignment {packet['assignmentId']}; distribute session.html only.")
    else:
        result = score([json.loads(path.read_text()) for path in args.keys],
                       [json.loads(path.read_text()) for path in args.responses])
        write_json(args.output, result)
        print(json.dumps(result["summaries"], indent=2))


if __name__ == "__main__":
    main()
