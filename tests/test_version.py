from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

from gwtlang.version import (
    PACKAGE_VERSION,
    current_package_version,
    version_payload,
)


class VersionTests(unittest.TestCase):
    def test_current_package_version_reports_source_constant(self):
        self.assertEqual(current_package_version(), PACKAGE_VERSION)

    def test_package_version_matches_pyproject(self):
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())

        self.assertEqual(PACKAGE_VERSION, pyproject["project"]["version"])

    def test_version_payload_uses_current_source_version(self):
        payload = version_payload()

        self.assertEqual(payload["packageVersion"], PACKAGE_VERSION)


if __name__ == "__main__":
    unittest.main()
