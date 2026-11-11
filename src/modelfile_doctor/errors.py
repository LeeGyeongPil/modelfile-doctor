"""Library exceptions.

Exceptions carry a machine-readable ``code`` and a ``params`` dict only. They never
hold translated text: the CLI (or any caller) renders them with
:func:`modelfile_doctor.i18n.render_error` in the language the user picked.
"""

from __future__ import annotations

from typing import Any


class DoctorError(Exception):
    """Base error: ``code`` such as ``"io.not_found"`` plus ``params`` for the message."""

    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(code, params or {})
        self.code = code
        self.params: dict[str, Any] = dict(params or {})

    def __str__(self) -> str:
        return f"{self.code} {self.params!r}"


class ModelfileReadError(DoctorError):
    """The Modelfile (or a file it points to) could not be read or decoded."""


class GGUFError(DoctorError):
    """A GGUF file is not valid, is truncated, or uses an unsupported feature."""


class OllamaError(DoctorError):
    """The local Ollama server could not be reached or answered unexpectedly."""


def from_oserror(exc: OSError, path: str, cls: type[DoctorError] = ModelfileReadError) -> DoctorError:
    """Convert an ``OSError`` into a :class:`DoctorError` with a stable code."""
    if isinstance(exc, PermissionError):
        return cls("io.permission", {"path": path})
    if isinstance(exc, IsADirectoryError):
        return cls("io.is_directory", {"path": path})
    if isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return cls("io.not_found", {"path": path})
    return cls("io.other", {"path": path, "detail": exc.strerror or type(exc).__name__})
