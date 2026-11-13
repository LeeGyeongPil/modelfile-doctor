"""MF rules: Modelfile syntax, instructions and PARAMETER values."""

from __future__ import annotations

import difflib
import os
from pathlib import Path

from .errors import from_oserror
from .params import DEPRECATED, PARAMS, parse_bool, parse_float, parse_int
from .parser import VALID_INSTRUCTIONS, ParsedModelfile, split_parameter
from .report import Diagnostic, Severity

ROLES = ("system", "user", "assistant")
GGUF_MAGIC = b"GGUF"


def _fmt(number: float) -> str:
    return str(int(number)) if float(number).is_integer() else str(number)


def _suggest(name: str, choices: list[str] | tuple[str, ...]) -> str | None:
    lowered = name.lower()
    if lowered != name and lowered in choices:
        return lowered
    close = difflib.get_close_matches(lowered, list(choices), n=1, cutoff=0.7)
    return close[0] if close else None


def looks_like_path(arg: str, base_dir: str) -> bool:
    """Is a FROM argument a file path (as opposed to a model name like ``qwen3:4b``)?"""
    if arg.startswith(("/", "./", "../", "~", ".\\", "..\\")) or (len(arg) > 2 and arg[1:3] in (":\\", ":/")):
        return True
    if arg.lower().endswith(".gguf"):
        return True
    return os.path.exists(os.path.join(base_dir, arg))


def resolve_from_path(arg: str, base_dir: str) -> Path:
    return Path(os.path.join(base_dir, os.path.expanduser(arg)))


def check_modelfile(parsed: ParsedModelfile, encoding: str, base_dir: str = ".") -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    if encoding != "utf-8":
        diags.append(Diagnostic("MF001", Severity.WARNING, 1, "diag.MF001", {"encoding": encoding}))

    froms = parsed.all("from")
    if not froms:
        diags.append(Diagnostic("MF002", Severity.ERROR, 1, "diag.MF002"))

    seen_single: dict[str, int] = {}
    for cmd in parsed.commands:
        if cmd.quote != "none" and not cmd.terminated:
            diags.append(Diagnostic("MF003", Severity.ERROR, cmd.line, "diag.MF003", {"name": cmd.raw_name}))

        if cmd.name not in VALID_INSTRUCTIONS:
            hint = _suggest(cmd.raw_name, VALID_INSTRUCTIONS)
            if hint:
                diags.append(Diagnostic(
                    "MF004", Severity.ERROR, cmd.line, "diag.MF004.suggest",
                    {"name": cmd.raw_name, "suggestion": hint.upper()},
                ))
            else:
                diags.append(Diagnostic("MF004", Severity.ERROR, cmd.line, "diag.MF004", {"name": cmd.raw_name}))
            continue

        if cmd.name in ("template", "system"):
            if cmd.name in seen_single:
                diags.append(Diagnostic(
                    "MF015", Severity.WARNING, cmd.line, "diag.MF015",
                    {"name": cmd.name.upper(), "first_line": seen_single[cmd.name]},
                ))
            else:
                seen_single[cmd.name] = cmd.line

        if cmd.name == "parameter":
            diags.extend(_check_parameter(cmd))
        elif cmd.name == "message":
            role = cmd.args.split(None, 1)[0] if cmd.args.split() else ""
            if role not in ROLES:
                diags.append(Diagnostic("MF014", Severity.ERROR, cmd.line, "diag.MF014", {"role": role}))
        elif cmd.name == "from" and cmd.args:
            diags.extend(_check_from_path(cmd.line, cmd.args, base_dir))
        elif cmd.name == "adapter" and cmd.args:
            diags.extend(_check_adapter_path(cmd.line, cmd.args, base_dir))
    return diags


def _check_parameter(cmd) -> list[Diagnostic]:  # type: ignore[no-untyped-def]
    name, value, quoted = split_parameter(cmd)
    line = cmd.line
    if name in DEPRECATED:
        return [Diagnostic("MF010", Severity.WARNING, line, "diag.MF010", {"name": name})]
    spec = PARAMS.get(name)
    if spec is None:
        hint = _suggest(name, list(PARAMS))
        if hint:
            return [Diagnostic("MF011", Severity.ERROR, line, "diag.MF011.suggest", {"name": name, "suggestion": hint})]
        return [Diagnostic("MF011", Severity.ERROR, line, "diag.MF011", {"name": name})]

    if spec.kind == "list":
        if value == "":
            return [Diagnostic("MF016", Severity.WARNING, line, "diag.MF016.empty")]
        if not quoted and any(ch.isspace() for ch in value):
            return [Diagnostic("MF016", Severity.WARNING, line, "diag.MF016.space", {"value": value})]
        return []

    number: float | None
    if spec.kind == "int":
        number = parse_int(value)
    elif spec.kind == "float":
        number = parse_float(value)
    else:
        number = None if parse_bool(value) is None else 0
    if number is None:
        return [Diagnostic("MF012", Severity.ERROR, line, "diag.MF012", {"name": name, "value": value, "kind": spec.kind})]
    if spec.kind in ("int", "float"):
        low, high = spec.min, spec.max
        if (low is not None and number < low) or (high is not None and number > high):
            rng = f">= {_fmt(low)}" if high is None else f"{_fmt(low)}..{_fmt(high)}"  # type: ignore[arg-type]
            return [Diagnostic(
                "MF013", Severity.WARNING, line, "diag.MF013", {"name": name, "value": value, "range": rng}
            )]
    return []


def _check_from_path(line: int, arg: str, base_dir: str) -> list[Diagnostic]:
    if not looks_like_path(arg, base_dir):
        return []
    path = resolve_from_path(arg, base_dir)
    if path.is_dir():
        return []  # safetensors directory: handled as "metadata not readable" later
    if not path.exists():
        return [Diagnostic("MF020", Severity.ERROR, line, "diag.MF020.missing", {"path": arg})]
    try:
        with open(path, "rb") as fh:
            magic = fh.read(4)
    except OSError as exc:
        raise from_oserror(exc, str(path)) from exc
    if magic != GGUF_MAGIC:
        return [Diagnostic("MF020", Severity.ERROR, line, "diag.MF020.not_gguf", {"path": arg})]
    return []


def _check_adapter_path(line: int, arg: str, base_dir: str) -> list[Diagnostic]:
    """MF021: an ADAPTER value that looks like a path must exist (file or directory)."""
    looks = arg.startswith(("/", "./", "../", "~", ".\\", "..\\")) or (len(arg) > 2 and arg[1:3] in (":\\", ":/"))
    looks = looks or arg.lower().endswith((".gguf", ".safetensors"))
    if not looks:
        return []  # model-name form: not checked
    if resolve_from_path(arg, base_dir).exists():
        return []
    return [Diagnostic("MF021", Severity.ERROR, line, "diag.MF021.missing", {"path": arg})]
