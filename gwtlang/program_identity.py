"""Deterministic identity for a GWT program's complete ``USE`` closure.

Identity format ``gwt-program-closure-sha256-v1`` is computed as follows:

1. Resolve ``USE`` paths with the same base-directory and :class:`ImportPolicy`
   rules as the runtime.
2. Name every module with a POSIX logical specifier relative to the entry
   module's directory. Specifiers inside that directory begin with ``./``;
   modules outside it use one or more ``../`` components.
3. Hash each module's exact bytes with SHA-256.
4. Serialize an object containing the algorithm, entry specifier, and modules
   sorted by specifier. Each module contains its specifier, ``sha256:`` content
   digest, and logical import targets in source order. Serialization uses
   ``json.dumps(..., ensure_ascii=False, sort_keys=True,
   separators=(",", ":"))`` encoded as UTF-8.
5. Hash those canonical bytes with SHA-256 and prefix the result with
   ``sha256:``.

Resolved absolute filesystem paths never enter the manifest or closure digest,
so a relative-import tree copied intact to another workstation has the same
identity. An absolute path literally written in GWT source remains part of that
module's content and therefore still affects its per-module digest.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import textwrap
from typing import Literal, TypedDict

from .errors import GwtError
from .runtime import ImportPolicy, _logical_lines, _tokens


PROGRAM_IDENTITY_ALGORITHM = "gwt-program-closure-sha256-v1"
_SHA256_PREFIX = "sha256:"


class ProgramModuleIdentityPayload(TypedDict):
    specifier: str
    digest: str
    imports: list[str]


class ProgramIdentityPayload(TypedDict):
    algorithm: Literal["gwt-program-closure-sha256-v1"]
    entry: str
    digest: str
    modules: list[ProgramModuleIdentityPayload]


@dataclass(frozen=True)
class ProgramModuleIdentity:
    """Content identity and logical dependency edges for one GWT module."""

    specifier: str
    digest: str
    imports: tuple[str, ...]

    def as_payload(self) -> ProgramModuleIdentityPayload:
        return {
            "specifier": self.specifier,
            "digest": self.digest,
            "imports": list(self.imports),
        }


@dataclass(frozen=True)
class ProgramIdentityManifest:
    """Path-portable identity for an entry module and its complete closure."""

    entry: str
    digest: str
    modules: tuple[ProgramModuleIdentity, ...]
    algorithm: Literal["gwt-program-closure-sha256-v1"] = (
        "gwt-program-closure-sha256-v1"
    )

    def as_payload(self) -> ProgramIdentityPayload:
        return {
            "algorithm": self.algorithm,
            "entry": self.entry,
            "digest": self.digest,
            "modules": [module.as_payload() for module in self.modules],
        }


@dataclass(frozen=True)
class _CollectedModule:
    path: Path
    source_bytes: bytes
    source: str
    imports: tuple[Path, ...]


@dataclass(frozen=True)
class LoadedProgramModule:
    """One source module captured as part of a loaded program snapshot."""

    path: Path
    source_bytes: bytes
    source: str
    imports: tuple[Path, ...]


@dataclass(frozen=True)
class LoadedProgramSnapshot:
    """Immutable sources and identity for one complete program closure.

    Paths are resolved absolute paths used only to address sources inside this
    process. The portable :attr:`identity` excludes those physical paths.
    """

    entry_path: Path
    identity: ProgramIdentityManifest
    modules: tuple[LoadedProgramModule, ...]

    @property
    def entry_source(self) -> str:
        """Return the captured entry-module source."""

        return self.source_for(self.entry_path)

    def source_for(self, path: str | Path) -> str:
        """Return captured UTF-8 source for ``path`` without reading the file.

        ``KeyError`` indicates that the resolved path was not part of the
        closure at snapshot construction time. This makes the method directly
        usable as ``parse_program(..., source_loader=snapshot.source_for)``.
        """

        resolved_path = Path(path).resolve()
        for module in self.modules:
            if module.path == resolved_path:
                return module.source
        raise KeyError(resolved_path)


def build_program_identity(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
) -> ProgramIdentityManifest:
    """Build a deterministic manifest for ``path`` and all of its imports.

    Import syntax, relative path resolution, confinement checks, missing-file
    errors, and circular-import errors intentionally mirror ``parse_program``.
    Other GWT syntax is not parsed here; callers should still check or compile
    the program before executing it.
    """

    return load_program_snapshot(path, import_policy=import_policy).identity


def load_program_snapshot(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
) -> LoadedProgramSnapshot:
    """Read a program closure once and bind its identity to those exact bytes.

    Each entry or imported file is read at most once, including when a cycle
    revisits the entry while producing the runtime-compatible cycle error.
    """

    entry_path = Path(path).resolve()
    root = entry_path.parent
    collected: dict[Path, _CollectedModule] = {}
    _collect_module(
        entry_path,
        entry_path=entry_path,
        collected=collected,
        importing=set(),
        import_policy=import_policy,
    )

    identity_modules = tuple(
        sorted(
            (
                ProgramModuleIdentity(
                    specifier=_logical_specifier(module.path, root),
                    digest=_content_digest(module.source_bytes),
                    imports=tuple(
                        _logical_specifier(import_path, root)
                        for import_path in module.imports
                    ),
                )
                for module in collected.values()
            ),
            key=lambda module: module.specifier,
        )
    )
    entry = _logical_specifier(entry_path, root)
    digest = _closure_digest(entry, identity_modules)
    identity = ProgramIdentityManifest(
        entry=entry,
        digest=digest,
        modules=identity_modules,
    )
    loaded_modules = tuple(
        LoadedProgramModule(
            path=module.path,
            source_bytes=module.source_bytes,
            source=module.source,
            imports=module.imports,
        )
        for module in sorted(
            collected.values(),
            key=lambda module: _logical_specifier(module.path, root),
        )
    )
    return LoadedProgramSnapshot(
        entry_path=entry_path,
        identity=identity,
        modules=loaded_modules,
    )


def _collect_module(
    path: Path,
    *,
    entry_path: Path,
    collected: dict[Path, _CollectedModule],
    importing: set[Path],
    import_policy: ImportPolicy | None,
) -> None:
    collected_module = collected.get(path)
    if collected_module is None:
        source_bytes = path.read_bytes()
        source = _decode_source(path, source_bytes)
        # Register before descending so shared dependencies can be
        # de-duplicated. The finalized edge list replaces this placeholder
        # after traversal. A cycle that revisits the entry also reuses these
        # bytes instead of reading the entry a second time.
        collected[path] = _CollectedModule(path, source_bytes, source, ())
    else:
        source_bytes = collected_module.source_bytes
        source = collected_module.source
    imports: list[Path] = []

    for import_path in _resolved_imports(source, path, importing, import_policy):
        imports.append(import_path)
        # Runtime parsing does not place the initial entry in its ``importing``
        # set. Revisit it if imported so a cycle is reported at the same point
        # as ``parse_program`` rather than being hidden by closure de-duplication.
        if import_path in collected and import_path != entry_path:
            continue
        importing.add(import_path)
        try:
            _collect_module(
                import_path,
                entry_path=entry_path,
                collected=collected,
                importing=importing,
                import_policy=import_policy,
            )
        finally:
            importing.remove(import_path)
    collected[path] = _CollectedModule(path, source_bytes, source, tuple(imports))


def _decode_source(path: Path, source_bytes: bytes) -> str:
    try:
        return source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise GwtError(f"{path}: source is not valid UTF-8") from None


def _resolved_imports(
    source: str,
    filename: Path,
    importing: set[Path],
    import_policy: ImportPolicy | None,
) -> Iterator[Path]:
    for line in _logical_lines(textwrap.dedent(source), str(filename)):
        if not line.text.startswith("USE "):
            continue
        tokens = _tokens(line.text, str(filename), line.number)
        if len(tokens) != 2:
            raise GwtError(
                f"{filename}:{line.number}: USE expects one quoted path"
            )

        raw_import_path = Path(tokens[1])
        import_path = raw_import_path
        if not import_path.is_absolute():
            import_path = filename.parent / import_path
        import_path = import_path.resolve()
        if import_policy is not None:
            import_policy.validate(
                raw_import_path,
                import_path,
                str(filename),
                line.number,
            )

        if import_path in importing:
            raise GwtError(
                f"{filename}:{line.number}: circular USE import: {import_path}"
            )
        if not import_path.exists():
            raise GwtError(
                f"{filename}:{line.number}: USE file not found: {import_path}"
            )
        if not import_path.is_file():
            raise GwtError(
                f"{filename}:{line.number}: USE path is not a file: {import_path}"
            )
        # Yield immediately so traversal remains depth-first, like the runtime:
        # an error below an earlier import wins over a later direct-import error.
        yield import_path


def _logical_specifier(path: Path, root: Path) -> str:
    relative = Path(os.path.relpath(path, start=root)).as_posix()
    if relative == ".." or relative.startswith("../"):
        return relative
    return f"./{relative}"


def _content_digest(content: bytes) -> str:
    return f"{_SHA256_PREFIX}{hashlib.sha256(content).hexdigest()}"


def _closure_digest(
    entry: str,
    modules: tuple[ProgramModuleIdentity, ...],
) -> str:
    canonical = {
        "algorithm": PROGRAM_IDENTITY_ALGORITHM,
        "entry": entry,
        "modules": [module.as_payload() for module in modules],
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{_SHA256_PREFIX}{hashlib.sha256(encoded).hexdigest()}"
