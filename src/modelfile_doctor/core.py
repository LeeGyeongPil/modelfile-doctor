"""The lint pipeline: decode, parse, run MF/TP/CT rules, filter."""

from __future__ import annotations

import os
from typing import Iterable

from .decode import decode_modelfile
from .errors import DoctorError, ModelfileReadError, from_oserror
from .gguf_header import GGUFMetadata, read_gguf_metadata
from .ollama import blob_path, show_model
from .parser import ParsedModelfile, parse_modelfile
from .report import RULES, Diagnostic, Report, Severity, sort_key
from .rules_ct import check_against_gguf
from .rules_mf import check_modelfile, looks_like_path, resolve_from_path
from .rules_tp import check_template


MAX_MODELFILE_BYTES = 4 * 1024 * 1024  # a real Modelfile is a few KiB
GGUF_MAGIC = b"GGUF"


def validate_rule_filter(ids: Iterable[str] | None) -> list[str]:
    """Normalise ``--select``/``--ignore`` values; prefixes such as ``CT`` are allowed."""
    out: list[str] = []
    for raw in ids or []:
        item = raw.strip().upper()
        if not item:
            continue
        if not any(rule.startswith(item) for rule in RULES):
            raise DoctorError("cli.unknown_rule", {"value": raw})
        out.append(item)
    return out


def _wanted(rule: str, select: list[str], ignore: list[str]) -> bool:
    if select and not any(rule.startswith(s) for s in select):
        return False
    return not any(rule.startswith(i) for i in ignore)


def _resolve_metadata(
    parsed: ParsedModelfile, base_dir: str, ollama_url: str | None
) -> tuple[GGUFMetadata | None, list[Diagnostic]]:
    froms = parsed.all("from")
    if not froms or not froms[0].args:
        return None, []
    cmd = froms[0]
    arg = cmd.args
    if looks_like_path(arg, base_dir):
        target = resolve_from_path(arg, base_dir)
        if target.is_dir():
            return None, [Diagnostic("CT011", Severity.INFO, cmd.line, "diag.CT011", {"reason": "directory"})]
        if not target.exists():
            return None, []  # MF020 already reports it
        return _read_or_note(str(target), cmd.line)
    if ollama_url is None:
        return None, [Diagnostic("CT010", Severity.INFO, cmd.line, "diag.CT010", {"name": arg})]
    show = show_model(ollama_url, arg)  # OllamaError propagates (exit 2 in the CLI)
    blob = blob_path(show)
    if blob is None:
        return None, [Diagnostic("CT011", Severity.INFO, cmd.line, "diag.CT011", {"reason": "no_blob"})]
    return _read_or_note(blob, cmd.line)


def _read_or_note(path: str, line: int) -> tuple[GGUFMetadata | None, list[Diagnostic]]:
    try:
        return read_gguf_metadata(path), []
    except DoctorError as exc:
        if exc.code == "gguf.bad_magic":
            return None, []  # reported as MF020 for local files
        return None, [Diagnostic("CT011", Severity.INFO, line, "diag.CT011", {"reason": exc.code})]


def lint_text(
    text: str,
    *,
    base_dir: str = ".",
    gguf_meta: GGUFMetadata | None = None,
    ollama_url: str | None = None,
    select: Iterable[str] | None = None,
    ignore: Iterable[str] | None = None,
    path: str = "<string>",
    encoding: str = "utf-8",
) -> Report:
    """Lint Modelfile ``text``. ``base_dir`` resolves relative ``FROM`` paths."""
    sel = validate_rule_filter(select)
    ign = validate_rule_filter(ignore)
    parsed = parse_modelfile(text)
    diags = check_modelfile(parsed, encoding, base_dir)
    for cmd in parsed.all("template"):
        if cmd.terminated:
            diags.extend(check_template(cmd.args, cmd.line))
    if gguf_meta is not None:
        diags.extend(check_against_gguf(parsed, gguf_meta))
    else:
        meta, notes = _resolve_metadata(parsed, base_dir, ollama_url)
        diags.extend(notes)
        if meta is not None:
            diags.extend(check_against_gguf(parsed, meta))
    kept = sorted((d for d in diags if _wanted(d.rule, sel, ign)), key=sort_key)
    return Report(path=path, diagnostics=kept, encoding=encoding)


def lint_path(
    path: str | os.PathLike[str],
    *,
    ollama_url: str | None = None,
    select: Iterable[str] | None = None,
    ignore: Iterable[str] | None = None,
) -> Report:
    """Read and lint the Modelfile at ``path``. Raises :class:`DoctorError` on I/O problems."""
    spath = os.fspath(path)
    try:
        with open(spath, "rb") as fh:
            raw = fh.read(MAX_MODELFILE_BYTES + 1)  # never slurp a multi-GB file
    except OSError as exc:
        raise from_oserror(exc, spath, ModelfileReadError) from exc
    if raw.startswith(GGUF_MAGIC):
        raise ModelfileReadError("modelfile.is_gguf", {"path": spath})
    if len(raw) > MAX_MODELFILE_BYTES:
        raise ModelfileReadError(
            "modelfile.too_large", {"path": spath, "limit_mib": MAX_MODELFILE_BYTES // (1024 * 1024)}
        )
    text, encoding = decode_modelfile(raw, spath)
    return lint_text(
        text,
        base_dir=os.path.dirname(os.path.abspath(spath)),
        ollama_url=ollama_url,
        select=select,
        ignore=ignore,
        path=spath,
        encoding=encoding,
    )
