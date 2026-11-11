"""Command line interface: ``modelfile-doctor [OPTIONS] PATH...``."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Sequence

from . import __version__
from .core import lint_path, validate_rule_filter
from .demo import run_demo
from .errors import DoctorError
from .gguf_header import read_gguf_metadata
from .i18n import LANGS, render, render_error, resolve_lang
from .ollama import default_url
from .output import render_report_text, render_rule_list, render_totals, report_to_dict
from .tokens import model_role_tokens

SUBCOMMANDS = ("demo", "inspect")


class _Parser(argparse.ArgumentParser):
    """argparse that raises a :class:`DoctorError` so the message can be translated."""

    def error(self, message: str) -> "Any":  # type: ignore[override]
        raise DoctorError("cli.usage", {"detail": message})


def _build_parser() -> _Parser:
    p = _Parser(prog="modelfile-doctor", add_help=False, allow_abbrev=False)
    p.add_argument("paths", nargs="*")
    p.add_argument("--lang")
    p.add_argument("--format", dest="fmt", default="text")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--ollama", nargs="?", const="")
    p.add_argument("--select", action="append", default=[])
    p.add_argument("--ignore", action="append", default=[])
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--list-rules", action="store_true")
    p.add_argument("--version", action="store_true")
    p.add_argument("--out")
    p.add_argument("-h", "--help", action="store_true")
    return p


def _split_ids(values: list[str]) -> list[str]:
    return [item for value in values for item in value.split(",") if item.strip()]


def _prescan_lang(argv: Sequence[str]) -> str | None:
    """Find ``--lang`` before real parsing so even usage errors use the chosen language."""
    for i, token in enumerate(argv):
        if token == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if token.startswith("--lang="):
            return token.split("=", 1)[1]
    return None


def _use_color(no_color: bool) -> bool:
    if no_color or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _error_line(exc: DoctorError, lang: str) -> str:
    return f"{render('cli.error', None, lang)}: {render_error(exc, lang)}"


def main(argv: Sequence[str] | None = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    prescan = _prescan_lang(args_in)
    if prescan is not None and prescan.lower() not in LANGS:
        lang = resolve_lang(None)
        print(_error_line(DoctorError("cli.bad_lang", {"value": prescan}), lang), file=sys.stderr)
        return 2
    lang = resolve_lang(prescan.lower() if prescan else None)
    try:
        return _run(args_in, lang)
    except DoctorError as exc:
        print(_error_line(exc, lang), file=sys.stderr)
        return 2


def _run(args_in: list[str], lang: str) -> int:
    ns = _build_parser().parse_intermixed_args(args_in)
    paths: list[str] = list(ns.paths)
    ollama_url: str | None = None
    if ns.ollama is not None:
        if ns.ollama and re.match(r"^https?://", ns.ollama):
            ollama_url = ns.ollama.rstrip("/")
        else:
            if ns.ollama:  # `--ollama Modelfile`: the word was a path, not a URL
                paths.insert(0, ns.ollama)
            ollama_url = default_url()

    command = paths[0] if paths and paths[0] in SUBCOMMANDS else None
    if ns.help:
        key = {"demo": "help.demo", "inspect": "help.inspect"}.get(command or "", "help.text")
        print(render(key, None, lang))
        return 0
    if ns.version:
        print(f"modelfile-doctor {__version__}")
        return 0
    if ns.list_rules:
        print("\n".join(render_rule_list(lang)))
        return 0
    if ns.fmt not in ("text", "json"):
        raise DoctorError("cli.bad_format", {"value": ns.fmt})
    select = validate_rule_filter(_split_ids(ns.select))
    ignore = validate_rule_filter(_split_ids(ns.ignore))
    color = _use_color(ns.no_color)

    if command == "demo":
        return run_demo(ns.out, lang, print, color)
    if command == "inspect":
        return _inspect(paths[1:], ns.fmt, lang)
    if not paths:
        raise DoctorError("cli.no_paths")
    return _lint_files(paths, ollama_url, select, ignore, ns.fmt, ns.strict, lang, color)


def _lint_files(
    paths: list[str], ollama_url: str | None, select: list[str], ignore: list[str],
    fmt: str, strict: bool, lang: str, color: bool,
) -> int:
    reports = []
    json_items: list[dict[str, Any]] = []
    failed = False
    for path in paths:
        try:
            report = lint_path(path, ollama_url=ollama_url, select=select, ignore=ignore)
        except DoctorError as exc:
            failed = True
            print(_error_line(exc, lang), file=sys.stderr)
            json_items.append({
                "path": path,
                "error": {"code": exc.code, "params": exc.params, "message": render_error(exc, lang)},
            })
            continue
        reports.append(report)
        json_items.append(report_to_dict(report, lang))
        if fmt == "text":
            print("\n".join(render_report_text(report, lang, color)))
    if fmt == "json":
        print(json.dumps(json_items, ensure_ascii=False, indent=2))
    elif reports:
        print(render_totals(reports, lang))
    if failed:
        return 2
    if any(r.errors for r in reports) or (strict and any(r.warnings for r in reports)):
        return 1
    return 0


def _inspect(paths: list[str], fmt: str, lang: str) -> int:
    if len(paths) != 1:
        raise DoctorError("cli.no_paths")
    meta = read_gguf_metadata(paths[0])
    roles = model_role_tokens(meta)
    if fmt == "json":
        print(json.dumps({
            "path": paths[0], "version": meta.version, "architecture": meta.architecture, "name": meta.name,
            "context_length": meta.context_length, "vocab_size": len(meta.tokens),
            "eos_token": meta.eos_token, "bos_token": meta.bos_token, "eot_token": meta.eot_token,
            "chat_template_length": len(meta.chat_template or ""), "role_tokens": roles,
        }, ensure_ascii=False, indent=2))
        return 0
    none = render("inspect.none", None, lang)
    rows = [
        ("inspect.architecture", meta.architecture), ("inspect.name", meta.name),
        ("inspect.version", meta.version), ("inspect.context_length", meta.context_length),
        ("inspect.vocab", len(meta.tokens)), ("inspect.eos", meta.eos_token),
        ("inspect.bos", meta.bos_token), ("inspect.eot", meta.eot_token),
        ("inspect.chat_template", len(meta.chat_template or "")),
        ("inspect.roles", " ".join(roles) or None),
    ]
    for key, value in rows:
        print(render(key, {"value": none if value is None else value}, lang))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
