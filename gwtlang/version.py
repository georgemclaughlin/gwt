from __future__ import annotations

from typing import TypedDict


PACKAGE_NAME = "gwtlang"
PACKAGE_VERSION = "0.3.0"
LANGUAGE_SPEC_VERSION = "v0.2"
LANGUAGE_SPEC_PATH = "docs/spec/v0.2.md"
PAYLOAD_SCHEMA_VERSION = 3


class VersionPayload(TypedDict):
    schemaVersion: int
    packageName: str
    packageVersion: str
    languageSpecVersion: str
    languageSpecPath: str
    payloadSchemaVersion: int


def current_package_version() -> str:
    return PACKAGE_VERSION


def version_payload() -> VersionPayload:
    return {
        "schemaVersion": PAYLOAD_SCHEMA_VERSION,
        "packageName": PACKAGE_NAME,
        "packageVersion": current_package_version(),
        "languageSpecVersion": LANGUAGE_SPEC_VERSION,
        "languageSpecPath": LANGUAGE_SPEC_PATH,
        "payloadSchemaVersion": PAYLOAD_SCHEMA_VERSION,
    }
