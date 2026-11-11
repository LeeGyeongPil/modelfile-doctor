"""PARAMETER table: names, value types and usual ranges.

Snapshot of the ``json`` tags of ``Options`` and ``Runner`` in Ollama's ``api/types.go``
(Ollama 0.40.15, checked 2026-11-12): https://github.com/ollama/ollama/blob/main/api/types.go
The deprecated list comes from ``parser/parser.go`` (the parser only warns and drops them).
Names newer than this snapshot are reported as unknown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    kind: str  # "int" | "float" | "bool" | "list"
    min: float | None = None
    max: float | None = None


PARAMS: dict[str, ParamSpec] = {
    "num_keep": ParamSpec("int", -1),
    "seed": ParamSpec("int"),
    "num_predict": ParamSpec("int", -2),
    "top_k": ParamSpec("int", 0),
    "top_p": ParamSpec("float", 0.0, 1.0),
    "min_p": ParamSpec("float", 0.0, 1.0),
    "typical_p": ParamSpec("float", 0.0, 1.0),
    "repeat_last_n": ParamSpec("int", -1),
    "temperature": ParamSpec("float", 0.0, 2.0),
    "repeat_penalty": ParamSpec("float", 0.0),
    "presence_penalty": ParamSpec("float", -2.0, 2.0),
    "frequency_penalty": ParamSpec("float", -2.0, 2.0),
    "stop": ParamSpec("list"),
    "num_ctx": ParamSpec("int", 1),
    "num_batch": ParamSpec("int", 1),
    "num_gpu": ParamSpec("int", -1),
    "main_gpu": ParamSpec("int", 0),
    "use_mmap": ParamSpec("bool"),
    "num_thread": ParamSpec("int", 0),
    "draft_num_predict": ParamSpec("int", 0),
}

DEPRECATED = frozenset({
    "penalize_newline", "low_vram", "f16_kv", "logits_all", "vocab_only",
    "use_mlock", "mirostat", "mirostat_tau", "mirostat_eta",
})

_INT = re.compile(r"[+-]?\d+")
_TRUE = {"1", "t", "T", "TRUE", "true", "True"}
_FALSE = {"0", "f", "F", "FALSE", "false", "False"}


def parse_int(value: str) -> int | None:
    """Go ``strconv.ParseInt(v, 10, 64)`` shape."""
    return int(value) if _INT.fullmatch(value) else None


def parse_float(value: str) -> float | None:
    """Go ``strconv.ParseFloat`` shape (underscores and surrounding spaces are not allowed)."""
    if not value or "_" in value or value != value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_bool(value: str) -> bool | None:
    """Go ``strconv.ParseBool``."""
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None
