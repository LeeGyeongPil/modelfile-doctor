"""modelfile-doctor: check an Ollama Modelfile against the GGUF it points to."""

from __future__ import annotations

__version__ = "0.1.1"

from .core import lint_path, lint_text
from .errors import DoctorError, GGUFError, ModelfileReadError, OllamaError
from .gguf_header import GGUFMetadata, read_gguf_metadata
from .i18n import render, render_error, resolve_lang
from .report import Diagnostic, Report, Severity

__all__ = [
    "__version__",
    "lint_path",
    "lint_text",
    "read_gguf_metadata",
    "GGUFMetadata",
    "Report",
    "Diagnostic",
    "Severity",
    "DoctorError",
    "ModelfileReadError",
    "GGUFError",
    "OllamaError",
    "render",
    "render_error",
    "resolve_lang",
]
