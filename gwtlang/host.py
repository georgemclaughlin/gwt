from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
import re
from typing import Any, cast

from .api import CompiledProgram, ExecutionResult, compile_file, compile_text
from .payloads import JsonObject, JsonValue
from .runtime import GwtError

PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MISSING = object()


HostObserver = Callable[["HostContext"], Any]


@dataclass(frozen=True)
class HostObservation:
    """A host-computed value injected into GWT state before execution."""

    path: str
    observe: HostObserver

    def __post_init__(self) -> None:
        if not PATH_PATTERN.match(self.path):
            raise GwtError(f"invalid host observation path: {self.path}")


@dataclass(frozen=True)
class HostContext:
    """Read-only view of the normalized state available to host observers."""

    state: Mapping[str, Any]

    def get(self, path: str, default: Any = _MISSING) -> Any:
        if not PATH_PATTERN.match(path):
            raise GwtError(f"invalid host state path: {path}")
        value = _get_path(self.state, path)
        if value is _MISSING:
            if default is _MISSING:
                raise GwtError(f"host state path is missing: {path}")
            return default
        return value


@dataclass(frozen=True)
class GwtHostAdapter:
    """Run a GWT program with host-computed observations.

    Host code owns non-deterministic or ecosystem-specific work. Observers turn
    that work into JSON-compatible records, and GWT evaluates the deterministic
    behavior over the combined state.
    """

    program: CompiledProgram
    request: str
    observations: tuple[HostObservation, ...] = ()

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        request: str,
        observations: Sequence[HostObservation] = (),
        import_roots: Sequence[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> GwtHostAdapter:
        return cls(
            compile_file(
                path,
                import_roots=import_roots,
                allow_absolute_imports=allow_absolute_imports,
            ),
            request,
            tuple(observations),
        )

    @classmethod
    def from_text(
        cls,
        source: str,
        *,
        request: str,
        observations: Sequence[HostObservation] = (),
        filename: str = "<source>",
        import_roots: Sequence[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> GwtHostAdapter:
        return cls(
            compile_text(
                source,
                filename=filename,
                import_roots=import_roots,
                allow_absolute_imports=allow_absolute_imports,
            ),
            request,
            tuple(observations),
        )

    def with_observation(self, path: str, observe: HostObserver) -> GwtHostAdapter:
        return GwtHostAdapter(
            self.program,
            self.request,
            (*self.observations, HostObservation(path, observe)),
        )

    def run_json(
        self,
        state: Mapping[str, Any],
        *,
        observations: Sequence[HostObservation] = (),
        request: str | None = None,
        json_file: str | Path | None = None,
    ) -> ExecutionResult:
        json_state = _json_value(state)
        if not isinstance(json_state, dict):
            raise GwtError("host adapter state must normalize to a JSON object")
        json_object = cast(JsonObject, json_state)

        for observation in (*self.observations, *observations):
            context = HostContext(json_object)
            try:
                value = observation.observe(context)
            except GwtError:
                raise
            except Exception as exc:
                raise GwtError(f"host observation failed for {observation.path}: {exc}") from exc
            _set_path(json_object, observation.path, _json_value(value))

        return self.program.run_json(
            json_object,
            request=request or self.request,
            json_file=json_file,
        )


def _json_value(value: Any) -> JsonValue:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise GwtError(f"host decimal is not finite: {value}")
        return str(value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        normalized: JsonObject = {}
        for key, item in cast(Mapping[object, Any], value).items():
            if not isinstance(key, str):
                raise GwtError(f"host JSON object keys must be text, got {key!r}")
            normalized[key] = _json_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in cast(Sequence[Any], value)]
    raise GwtError(f"host value is not JSON-compatible: {type(value).__name__}")


def _get_path(state: Mapping[str, Any], path: str) -> Any:
    value: object = state
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return _MISSING
        mapping = cast(Mapping[str, object], value)
        if part not in mapping:
            return _MISSING
        value = mapping[part]
    return value


def _set_path(state: JsonObject, path: str, value: JsonValue) -> None:
    current = state
    parts = path.split(".")
    for part in parts[:-1]:
        existing = current.get(part)
        if existing is None:
            existing = {}
            current[part] = existing
        if not isinstance(existing, dict):
            raise GwtError(f"host observation path cannot extend non-object state: {path}")
        current = cast(JsonObject, existing)
    current[parts[-1]] = value
