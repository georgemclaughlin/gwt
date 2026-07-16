from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
import importlib.util
import inspect
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from gwtlang import (
    CaseCorpusEntrySpec,
    case_corpus_digest,
    load_case_corpus,
    write_case_corpus,
)
from gwtlang.__main__ import main
from gwtlang.comparison import CaseComparison, compare_execution_cases
from gwtlang.execution_case import ExecutionCase


FIXTURES = Path("tests/fixtures/v0.4")
BASELINE = Path("examples/behavior_review/baseline.gwt")
CANDIDATE = Path("examples/behavior_review/candidate.gwt")


class CaseCorpusTests(unittest.TestCase):
    def test_round_trip_preserves_order_integrity_and_portability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "original"
            entries = self._copy_cases(root)
            corpus_path = root / "corpus.json"
            written = write_case_corpus(
                corpus_path,
                name="Library review cases",
                entries=entries,
            )
            payload = written.as_payload()
            moved = Path(temp_dir) / "moved"
            root.rename(moved)
            loaded = load_case_corpus(moved / "corpus.json")

        self.assertEqual(loaded.name, "Library review cases")
        self.assertEqual(loaded.references, ("hold-ready", "hold-waiting"))
        self.assertEqual(
            [case.request_name for case in loaded.cases],
            ["route hold", "route hold"],
        )
        self.assertEqual(
            payload["integrity"]["digest"],
            case_corpus_digest(payload),
        )
        self.assertRegex(payload["integrity"]["digest"], r"^sha256:[0-9a-f]{64}$")
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(Path("docs/schemas/case-corpus.schema.json").read_text())
            Draft202012Validator(schema).validate(payload)

    def test_compare_and_workbench_use_corpus_references(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entries = self._copy_cases(root)
            entries[0] = CaseCorpusEntrySpec(
                reference='<script>alert("case")</script>',
                case_id=entries[0].case_id,
                artifact=entries[0].artifact,
            )
            corpus_path = root / "corpus.json"
            corpus = write_case_corpus(
                corpus_path,
                name="Escaping review",
                entries=entries,
            )
            api_comparison = compare_execution_cases(
                BASELINE,
                CANDIDATE,
                corpus.cases,
                case_references=corpus.references,
            )
            with self.assertRaisesRegex(ValueError, "must be supplied together"):
                replace(api_comparison.cases[0], execution_case_id=None)
            with self.assertRaisesRegex(ValueError, "must be supplied together"):
                replace(api_comparison.cases[0], reference=None)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                compare_status = main(
                    [
                        "compare",
                        "--corpus",
                        str(corpus_path),
                        "--old",
                        str(BASELINE),
                        "--new",
                        str(CANDIDATE),
                        "--json",
                    ]
                )
            comparison = json.loads(stdout.getvalue())

            workbench_path = root / "workbench.html"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                workbench_status = main(
                    [
                        "workbench",
                        "--corpus",
                        str(corpus_path),
                        "--old",
                        str(BASELINE),
                        "--new",
                        str(CANDIDATE),
                        "--output",
                        str(workbench_path),
                    ]
                )
            workbench = workbench_path.read_text()

        self.assertEqual(compare_status, 0)
        self.assertEqual(workbench_status, 0)
        self.assertEqual(
            [item["reference"] for item in comparison["cases"]],
            ['<script>alert("case")</script>', "hold-waiting"],
        )
        self.assertEqual(
            [item["id"] for item in comparison["cases"]],
            ["case-0001-route-hold", "case-0002-route-hold"],
        )
        self.assertEqual(
            [item["executionCaseId"] for item in comparison["cases"]],
            [entry.case_id for entry in corpus.entries],
        )
        self.assertIn("&lt;script&gt;alert", workbench)
        self.assertNotIn('<script>alert("case")</script>', workbench)
        self.assertIn("hold-waiting", workbench)
        self.assertIn('<span class="muted">route hold</span>', workbench)
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(
                Path("docs/schemas/comparison.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            validator = Draft202012Validator(schema)
            self.assertTrue(validator.is_valid(comparison))
            for field in ("reference", "executionCaseId"):
                with self.subTest(missing=field):
                    incomplete = deepcopy(comparison)
                    incomplete["cases"][0].pop(field)
                    self.assertFalse(validator.is_valid(incomplete))

    def test_rejects_digest_mismatch_and_case_id_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entries = self._copy_cases(root)
            corpus_path = root / "corpus.json"
            corpus = write_case_corpus(
                corpus_path,
                name="Library cases",
                entries=entries,
            )
            payload = corpus.as_payload()
            tampered = deepcopy(payload)
            tampered["name"] = "Changed without digest"
            corpus_path.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, "integrity digest mismatch"):
                load_case_corpus(corpus_path)

            mismatched = deepcopy(payload)
            mismatched["cases"][0]["caseId"] = mismatched["cases"][1]["caseId"]
            mismatched["cases"] = mismatched["cases"][:1]
            mismatched["integrity"]["digest"] = case_corpus_digest(mismatched)
            corpus_path.write_text(json.dumps(mismatched))
            with self.assertRaisesRegex(ValueError, "caseId does not match artifact"):
                load_case_corpus(corpus_path)

    def test_loader_and_schema_reject_invalid_versions_and_display_text(self):
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("jsonschema package is not installed")
        from jsonschema import Draft202012Validator

        schema = json.loads(Path("docs/schemas/case-corpus.schema.json").read_text())
        validator = Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entries = self._copy_cases(root)[:1]
            corpus_path = root / "corpus.json"
            valid = write_case_corpus(
                corpus_path,
                name="Display text",
                entries=entries,
            ).as_payload()

            invalid_values = (
                ("schemaVersion", True),
                ("name", "   "),
                ("name", " leading"),
                ("reference", "   "),
                ("reference", "trailing "),
                ("reference", "line\nbreak"),
                ("reference", "trailing-newline\n"),
                ("reference", "escape\x1b[31m"),
                ("reference", "arabic-mark\u061c"),
                ("reference", "line-separator\u2028next"),
                ("reference", "paragraph-separator\u2029next"),
                ("reference", "spoof\u202etxt"),
                ("reference", "hidden-bom\ufefftxt"),
            )
            for field, value in invalid_values:
                with self.subTest(field=field, value=repr(value)):
                    payload = deepcopy(valid)
                    if field == "reference":
                        payload["cases"][0]["reference"] = value
                    else:
                        payload[field] = value
                    payload["integrity"]["digest"] = case_corpus_digest(payload)
                    self.assertFalse(validator.is_valid(payload))
                    corpus_path.write_text(json.dumps(payload))
                    with self.assertRaises(ValueError):
                        load_case_corpus(corpus_path)

            corpus = load_case_corpus(self._restore_payload(corpus_path, valid))
            with self.assertRaisesRegex(ValueError, "case reference must be"):
                compare_execution_cases(
                    BASELINE,
                    CANDIDATE,
                    corpus.cases,
                    case_references=[123],  # type: ignore[list-item]
                )

    def test_rejects_duplicate_json_object_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corpus_path = root / "corpus.json"
            payload = write_case_corpus(
                corpus_path,
                name="Duplicate keys",
                entries=self._copy_cases(root)[:1],
            ).as_payload()
            rendered = json.dumps(payload, ensure_ascii=False)
            duplicates = (
                rendered.replace(
                    '"kind": "gwt.case-corpus"',
                    '"kind": "wrong", "kind": "gwt.case-corpus"',
                    1,
                ),
                rendered.replace(
                    '"reference": "hold-ready"',
                    '"reference": "wrong", "reference": "hold-ready"',
                    1,
                ),
            )
            for duplicate in duplicates:
                with self.subTest(duplicate=duplicate[:80]):
                    corpus_path.write_text(duplicate, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "duplicate object key"):
                        load_case_corpus(corpus_path)

    def test_canonical_digest_string_escaping_vector(self):
        payload = {
            "schemaVersion": 1,
            "kind": "gwt.case-corpus",
            "name": 'Café "A/B"',
            "cases": [
                {
                    "reference": 'réf "one/two"',
                    "caseId": "sha256:" + "a" * 64,
                    "artifact": "cases/one.json",
                }
            ],
        }
        self.assertEqual(
            case_corpus_digest(payload),
            "sha256:424ccc1d98e551fd221d69445d0c162a0e628451f36aca797e4553cc15f76d94",
        )

    def test_comparison_constructor_keeps_new_identity_fields_optional(self):
        parameters = inspect.signature(CaseComparison).parameters
        self.assertEqual(
            list(parameters)[-2:],
            ["reference", "execution_case_id"],
        )
        self.assertIsNone(parameters["reference"].default)
        self.assertIsNone(parameters["execution_case_id"].default)

    def test_rejects_duplicate_references_and_case_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entries = self._copy_cases(root)
            duplicate_reference = [
                entries[0],
                CaseCorpusEntrySpec(
                    entries[0].reference,
                    entries[1].case_id,
                    entries[1].artifact,
                ),
            ]
            with self.assertRaisesRegex(ValueError, "duplicate case corpus reference"):
                write_case_corpus(
                    root / "duplicate-reference.json",
                    name="Duplicates",
                    entries=duplicate_reference,
                )

            duplicate_id = [
                entries[0],
                CaseCorpusEntrySpec(
                    entries[1].reference,
                    entries[0].case_id,
                    entries[1].artifact,
                ),
            ]
            with self.assertRaisesRegex(ValueError, "duplicate case corpus caseId"):
                write_case_corpus(
                    root / "duplicate-id.json",
                    name="Duplicates",
                    entries=duplicate_id,
                )

    def test_rejects_missing_absolute_traversal_and_symlink_escape_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "corpus"
            root.mkdir()
            outside = Path(temp_dir) / "outside.execution-case.json"
            shutil.copy2(FIXTURES / "library-completed.execution-case.json", outside)
            execution_case = ExecutionCase.load(outside)
            case_id = execution_case.as_payload()["integrity"]["digest"]

            for artifact in (
                "missing.execution-case.json",
                str(outside),
                "../outside.execution-case.json",
                "cases\\outside.execution-case.json",
                "cases//outside.execution-case.json",
                "cases/",
                "cases/line\nbreak.execution-case.json",
                "cases/nul\x00.execution-case.json",
                "cases/hidden\ufeff.execution-case.json",
            ):
                with self.subTest(artifact=artifact):
                    with self.assertRaisesRegex(
                        ValueError,
                        "artifact (must be|does not exist)",
                    ):
                        write_case_corpus(
                            root / "invalid.json",
                            name="Invalid paths",
                            entries=[CaseCorpusEntrySpec("case", case_id, artifact)],
                        )

            links = root / "cases"
            links.mkdir()
            link = links / "linked.execution-case.json"
            try:
                link.symlink_to(outside)
            except OSError:
                self.skipTest("symbolic links are not available")
            with self.assertRaisesRegex(ValueError, "must not use symbolic links"):
                write_case_corpus(
                    root / "symlink.json",
                    name="Symlink escape",
                    entries=[
                        CaseCorpusEntrySpec(
                            "linked",
                            case_id,
                            "cases/linked.execution-case.json",
                        )
                    ],
                )

            real = links / "real.execution-case.json"
            shutil.copy2(FIXTURES / "library-completed.execution-case.json", real)
            internal_link = links / "internal.execution-case.json"
            internal_link.symlink_to(real.name)
            with self.assertRaisesRegex(ValueError, "must not use symbolic links"):
                write_case_corpus(
                    root / "internal-symlink.json",
                    name="Internal symlink",
                    entries=[
                        CaseCorpusEntrySpec(
                            "linked-inside",
                            case_id,
                            "cases/internal.execution-case.json",
                        )
                    ],
                )

    def test_loader_and_schema_agree_on_invalid_artifact_paths(self):
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("jsonschema package is not installed")
        from jsonschema import Draft202012Validator

        schema = json.loads(
            Path("docs/schemas/case-corpus.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid = write_case_corpus(
                root / "corpus.json",
                name="Path agreement",
                entries=self._copy_cases(root)[:1],
            ).as_payload()
            for artifact in (
                "cases/",
                "cases/line\nbreak.execution-case.json",
                "cases/nul\x00.execution-case.json",
                "cases/hidden\ufeff.execution-case.json",
            ):
                with self.subTest(artifact=repr(artifact)):
                    payload = deepcopy(valid)
                    payload["cases"][0]["artifact"] = artifact
                    payload["integrity"]["digest"] = case_corpus_digest(payload)
                    self.assertFalse(validator.is_valid(payload))
                    path = root / "invalid.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "normalized relative POSIX"):
                        load_case_corpus(path)

    def test_writer_cannot_overwrite_a_referenced_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "corpus.json"
            shutil.copy2(
                FIXTURES / "library-completed.execution-case.json",
                destination,
            )
            execution_case = ExecutionCase.load(destination)
            original = destination.read_bytes()

            with self.assertRaisesRegex(
                ValueError,
                "cannot overwrite a referenced artifact",
            ):
                write_case_corpus(
                    destination,
                    name="Self overwrite",
                    entries=[
                        CaseCorpusEntrySpec(
                            "self",
                            execution_case.as_payload()["integrity"]["digest"],
                            destination.name,
                        )
                    ],
                )

            self.assertEqual(destination.read_bytes(), original)
            self.assertEqual(
                ExecutionCase.load(destination).as_payload(),
                execution_case.as_payload(),
            )

    def test_same_case_can_be_referenced_by_distinct_corpora(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = self._copy_cases(root)[:1]
            first = write_case_corpus(
                root / "first.json",
                name="First review",
                entries=entry,
            )
            second = write_case_corpus(
                root / "second.json",
                name="Second review",
                entries=[
                    CaseCorpusEntrySpec(
                        "different-domain-name",
                        entry[0].case_id,
                        entry[0].artifact,
                    )
                ],
            )

        self.assertEqual(first.entries[0].case_id, second.entries[0].case_id)
        self.assertNotEqual(first.references, second.references)

    def test_cli_creates_and_checks_a_portable_corpus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "evidence"
            entries = self._copy_cases(root)
            corpus_path = root / "review.case-corpus.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                create_status = main(
                    [
                        "corpus",
                        "create",
                        "--name",
                        "Library CLI review",
                        "--case",
                        f"ready={root / entries[0].artifact}",
                        "--case",
                        f"waiting={root / entries[1].artifact}",
                        "--output",
                        str(corpus_path),
                    ]
                )
            create_output = stdout.getvalue()
            corpus = load_case_corpus(corpus_path)
            before_check = corpus_path.read_bytes()

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                check_status = main(["corpus", "check", str(corpus_path)])
            check_output = stdout.getvalue()
            after_check = corpus_path.read_bytes()

            moved = Path(temp_dir) / "moved"
            root.rename(moved)
            moved_corpus = load_case_corpus(moved / corpus_path.name)

        self.assertEqual(create_status, 0)
        self.assertEqual(check_status, 0)
        self.assertIn("Wrote", create_output)
        self.assertIn("2 cases", create_output)
        self.assertIn("sha256:", create_output)
        self.assertIn("OK", check_output)
        self.assertEqual(after_check, before_check)
        self.assertEqual(corpus.references, ("ready", "waiting"))
        self.assertEqual(
            [entry.case_id for entry in corpus.entries],
            [entry.case_id for entry in entries],
        )
        self.assertEqual(
            [entry.artifact for entry in corpus.entries],
            [
                "cases/library-completed.execution-case.json",
                "cases/library-available.execution-case.json",
            ],
        )
        self.assertEqual(moved_corpus.references, corpus.references)

    def test_corpus_cli_rejects_outside_members_and_tampered_corpora(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            root = temp / "evidence"
            root.mkdir()
            outside = temp / "outside.execution-case.json"
            shutil.copy2(FIXTURES / "library-completed.execution-case.json", outside)
            corpus_path = root / "review.case-corpus.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                outside_status = main(
                    [
                        "corpus",
                        "create",
                        "--name",
                        "Outside member",
                        "--case",
                        f"outside={outside}",
                        "--output",
                        str(corpus_path),
                    ]
                )
            outside_error = stderr.getvalue()
            outside_created = corpus_path.exists()

            entries = self._copy_cases(root)[:1]
            corpus = write_case_corpus(
                corpus_path,
                name="Tamper check",
                entries=entries,
            )
            tampered = corpus.as_payload()
            tampered["name"] = "Changed"
            corpus_path.write_text(json.dumps(tampered), encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                tampered_status = main(["corpus", "check", str(corpus_path)])
            tampered_error = stderr.getvalue()

        self.assertEqual(outside_status, 1)
        self.assertIn("beneath the corpus directory", outside_error)
        self.assertFalse(outside_created)
        self.assertEqual(tampered_status, 1)
        self.assertIn("integrity digest mismatch", tampered_error)

    def test_cli_requires_exactly_one_case_selection_mode(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            missing_status = main(
                ["compare", "--old", str(BASELINE), "--new", str(CANDIDATE)]
            )
        self.assertEqual(missing_status, 2)
        self.assertIn("CASE files or --corpus", stderr.getvalue())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entries = self._copy_cases(root)
            corpus_path = root / "corpus.json"
            write_case_corpus(
                corpus_path,
                name="Selection mode",
                entries=entries,
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                both_status = main(
                    [
                        "compare",
                        str(root / entries[0].artifact),
                        "--corpus",
                        str(corpus_path),
                        "--old",
                        str(BASELINE),
                        "--new",
                        str(CANDIDATE),
                    ]
                )
            both_error = stderr.getvalue()
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                corpus_workbench_status = main(
                    [
                        "workbench",
                        "--corpus",
                        str(corpus_path),
                        "--output",
                        str(root / "review.html"),
                    ]
                )
            corpus_workbench_error = stderr.getvalue()
        self.assertEqual(both_status, 2)
        self.assertIn("but not both", both_error)
        self.assertEqual(corpus_workbench_status, 2)
        self.assertIn("multiple corpus cases require", corpus_workbench_error)

    @staticmethod
    def _copy_cases(root: Path) -> list[CaseCorpusEntrySpec]:
        case_dir = root / "cases"
        case_dir.mkdir(parents=True)
        specs: list[CaseCorpusEntrySpec] = []
        for reference, filename in (
            ("hold-ready", "library-completed.execution-case.json"),
            ("hold-waiting", "library-available.execution-case.json"),
        ):
            target = case_dir / filename
            shutil.copy2(FIXTURES / filename, target)
            execution_case = ExecutionCase.load(target)
            specs.append(
                CaseCorpusEntrySpec(
                    reference,
                    execution_case.as_payload()["integrity"]["digest"],
                    f"cases/{filename}",
                )
            )
        return specs

    @staticmethod
    def _restore_payload(path: Path, payload: object) -> Path:
        path.write_text(json.dumps(payload))
        return path


if __name__ == "__main__":
    unittest.main()
