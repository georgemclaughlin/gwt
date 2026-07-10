from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gwtlang.program_identity import (
    PROGRAM_IDENTITY_ALGORITHM,
    build_program_identity,
    load_program_snapshot,
)
from gwtlang.runtime import GwtError, ImportPolicy, Runtime, parse_program


class ProgramIdentityTests(unittest.TestCase):
    def test_snapshot_backed_parse_uses_captured_entry_and_import_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "rules.gwt"
            dependency = root / "behavior.gwt"
            entry_source = (
                'USE "./behavior.gwt"\n'
                "PROGRAM snapshot\n"
                "SCENARIO captured\n"
                'GIVEN result is "pending"\n'
                "WHEN load result\n"
                'THEN result is "captured"\n'
            )
            dependency_source = (
                "WHEN load result\n"
                '  set result to "captured"\n'
            )
            entry.write_text(entry_source)
            dependency.write_text(dependency_source)

            snapshot = load_program_snapshot(entry)
            entry.unlink()
            dependency.write_text(
                "WHEN load result\n"
                '  set result to "changed"\n'
            )

            program = parse_program(
                snapshot.entry_source,
                str(snapshot.entry_path),
                source_loader=snapshot.source_for,
            )
            result = Runtime(program).run()

        self.assertEqual(result.state["result"], "captured")
        module_digests = {
            module.specifier: module.digest
            for module in snapshot.identity.modules
        }
        self.assertEqual(
            module_digests["./rules.gwt"],
            f"sha256:{hashlib.sha256(entry_source.encode()).hexdigest()}",
        )
        self.assertEqual(
            module_digests["./behavior.gwt"],
            f"sha256:{hashlib.sha256(dependency_source.encode()).hexdigest()}",
        )

    def test_snapshot_reads_each_module_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "rules.gwt"
            first = root / "first.gwt"
            second = root / "second.gwt"
            shared = root / "shared.gwt"
            entry.write_text('USE "./first.gwt"\nUSE "./second.gwt"\n')
            first.write_text('USE "./shared.gwt"\n')
            second.write_text('USE "./shared.gwt"\n')
            shared.write_text("RECORD Shared\n  value: text\n")
            read_counts: dict[Path, int] = {}
            original_read_bytes = Path.read_bytes

            def tracked_read_bytes(path: Path) -> bytes:
                resolved = path.resolve()
                read_counts[resolved] = read_counts.get(resolved, 0) + 1
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", tracked_read_bytes):
                snapshot = load_program_snapshot(entry)

        self.assertEqual(len(snapshot.modules), 4)
        self.assertEqual(
            read_counts,
            {
                entry.resolve(): 1,
                first.resolve(): 1,
                second.resolve(): 1,
                shared.resolve(): 1,
            },
        )

    def test_invalid_utf8_import_error_matches_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "rules.gwt"
            dependency = root / "invalid.gwt"
            source = 'USE "./invalid.gwt"\n'
            entry.write_text(source)
            dependency.write_bytes(b"\xff\xfe")

            runtime_error = self._runtime_error(source, entry)
            identity_error = self._identity_error(entry)

        self.assertEqual(identity_error, runtime_error)
        self.assertEqual(
            identity_error,
            f"{dependency.resolve()}: source is not valid UTF-8",
        )

    def test_manifest_includes_recursive_modules_and_logical_edges(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "lib"
            library.mkdir()
            entry = root / "rules.gwt"
            workflow = library / "workflow.gwt"
            types = library / "types.gwt"
            entry.write_text('USE "./lib/workflow.gwt"\nPROGRAM example\n')
            workflow.write_text('USE "./types.gwt"\nWHEN run workflow\n  PASS\n')
            types.write_text("RECORD Input\n  value: text\n")

            manifest = build_program_identity(entry)

        self.assertEqual(manifest.algorithm, PROGRAM_IDENTITY_ALGORITHM)
        self.assertEqual(manifest.entry, "./rules.gwt")
        self.assertRegex(manifest.digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            [module.specifier for module in manifest.modules],
            ["./lib/types.gwt", "./lib/workflow.gwt", "./rules.gwt"],
        )
        modules = {module.specifier: module for module in manifest.modules}
        self.assertEqual(modules["./rules.gwt"].imports, ("./lib/workflow.gwt",))
        self.assertEqual(modules["./lib/workflow.gwt"].imports, ("./lib/types.gwt",))
        self.assertEqual(modules["./lib/types.gwt"].imports, ())

    def test_module_digest_hashes_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = Path(temp_dir) / "rules.gwt"
            content = b"PROGRAM exact\r\nGIVEN value is 1\r\n"
            entry.write_bytes(content)

            manifest = build_program_identity(entry)

        expected = f"sha256:{hashlib.sha256(content).hexdigest()}"
        self.assertEqual(manifest.modules[0].digest, expected)

    def test_identity_is_independent_of_workstation_absolute_path(self):
        with (
            tempfile.TemporaryDirectory() as first_dir,
            tempfile.TemporaryDirectory() as second_dir,
        ):
            first = self._write_tree(Path(first_dir))
            second = self._write_tree(Path(second_dir))

            first_manifest = build_program_identity(first)
            second_manifest = build_program_identity(second)

        self.assertEqual(first_manifest, second_manifest)
        rendered = str(first_manifest.as_payload())
        self.assertNotIn(first_dir, rendered)
        self.assertNotIn(second_dir, rendered)

    def test_nested_dependency_change_changes_only_its_content_and_closure_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = self._write_tree(Path(temp_dir))
            before = build_program_identity(entry)
            dependency = Path(temp_dir) / "shared" / "types.gwt"
            dependency.write_text("RECORD Input\n  value: number\n")

            after = build_program_identity(entry)

        before_modules = {module.specifier: module.digest for module in before.modules}
        after_modules = {module.specifier: module.digest for module in after.modules}
        self.assertNotEqual(before.digest, after.digest)
        self.assertEqual(before_modules["./rules.gwt"], after_modules["./rules.gwt"])
        self.assertNotEqual(
            before_modules["./shared/types.gwt"],
            after_modules["./shared/types.gwt"],
        )

    def test_shared_dependency_is_listed_once_with_each_logical_edge(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "rules.gwt"
            first = root / "first.gwt"
            second = root / "second.gwt"
            shared = root / "shared.gwt"
            entry.write_text('USE "./first.gwt"\nUSE "./second.gwt"\n')
            first.write_text('USE "./shared.gwt"\n')
            second.write_text('USE "./shared.gwt"\n')
            shared.write_text("GIVEN shared is true\n")

            manifest = build_program_identity(entry)

        self.assertEqual(
            [module.specifier for module in manifest.modules].count("./shared.gwt"),
            1,
        )
        modules = {module.specifier: module for module in manifest.modules}
        self.assertEqual(modules["./first.gwt"].imports, ("./shared.gwt",))
        self.assertEqual(modules["./second.gwt"].imports, ("./shared.gwt",))

    def test_outside_relative_import_uses_entry_relative_logical_specifier(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rules = root / "rules"
            rules.mkdir()
            entry = rules / "main.gwt"
            shared = root / "shared.gwt"
            entry.write_text('USE "../shared.gwt"\n')
            shared.write_text("GIVEN shared is true\n")

            manifest = build_program_identity(entry)

        self.assertEqual(
            [module.specifier for module in manifest.modules],
            ["../shared.gwt", "./main.gwt"],
        )
        modules = {module.specifier: module for module in manifest.modules}
        self.assertEqual(modules["./main.gwt"].imports, ("../shared.gwt",))

    def test_missing_import_error_matches_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = Path(temp_dir) / "rules.gwt"
            source = 'USE "./missing.gwt"\n'
            entry.write_text(source)

            runtime_error = self._runtime_error(source, entry)
            identity_error = self._identity_error(entry)

        self.assertEqual(identity_error, runtime_error)
        self.assertIn("USE file not found", identity_error)

    def test_circular_import_error_matches_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.gwt"
            second = root / "second.gwt"
            source = 'USE "./second.gwt"\n'
            first.write_text(source)
            second.write_text('USE "./first.gwt"\n')

            runtime_error = self._runtime_error(source, first)
            identity_error = self._identity_error(first)

        self.assertEqual(identity_error, runtime_error)
        self.assertIn("circular USE import", identity_error)

    def test_import_errors_follow_runtime_depth_first_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "entry.gwt"
            nested = root / "nested.gwt"
            source = 'USE "./nested.gwt"\nUSE "./later-missing.gwt"\n'
            entry.write_text(source)
            nested.write_text('USE "./nested.gwt"\n')

            runtime_error = self._runtime_error(source, entry)
            identity_error = self._identity_error(entry)

        self.assertEqual(identity_error, runtime_error)
        self.assertIn("circular USE import", identity_error)
        self.assertNotIn("later-missing", identity_error)

    def test_import_policy_error_matches_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rules = root / "rules"
            rules.mkdir()
            entry = rules / "main.gwt"
            outside = root / "outside.gwt"
            source = 'USE "../outside.gwt"\n'
            entry.write_text(source)
            outside.write_text("GIVEN outside is true\n")
            policy = ImportPolicy((rules,), allow_absolute=False)

            runtime_error = self._runtime_error(source, entry, policy)
            identity_error = self._identity_error(entry, policy)

        self.assertEqual(identity_error, runtime_error)
        self.assertIn("USE import is outside allowed roots", identity_error)

    def test_absolute_import_policy_error_matches_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "main.gwt"
            dependency = root / "dependency.gwt"
            source = f'USE "{dependency}"\n'
            entry.write_text(source)
            dependency.write_text("GIVEN dependency is true\n")
            policy = ImportPolicy((root,), allow_absolute=False)

            runtime_error = self._runtime_error(source, entry, policy)
            identity_error = self._identity_error(entry, policy)

        self.assertEqual(identity_error, runtime_error)
        self.assertIn("USE absolute import is not allowed", identity_error)

    @staticmethod
    def _write_tree(root: Path) -> Path:
        shared = root / "shared"
        shared.mkdir()
        entry = root / "rules.gwt"
        entry.write_text('USE "./shared/types.gwt"\nPROGRAM portable\n')
        (shared / "types.gwt").write_text("RECORD Input\n  value: text\n")
        return entry

    @staticmethod
    def _runtime_error(
        source: str,
        entry: Path,
        import_policy: ImportPolicy | None = None,
    ) -> str:
        try:
            parse_program(source, str(entry), import_policy=import_policy)
        except GwtError as exc:
            return str(exc)
        raise AssertionError("runtime parsing unexpectedly succeeded")

    @staticmethod
    def _identity_error(
        entry: Path,
        import_policy: ImportPolicy | None = None,
    ) -> str:
        try:
            build_program_identity(entry, import_policy=import_policy)
        except GwtError as exc:
            return str(exc)
        raise AssertionError("identity construction unexpectedly succeeded")


if __name__ == "__main__":
    unittest.main()
