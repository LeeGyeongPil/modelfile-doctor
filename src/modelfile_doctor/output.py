"""Text and JSON renderers."""

from __future__ import annotations

from typing import Any

from .i18n import render
from .report import RULES, Diagnostic, Report, Severity

_COLORS = {Severity.ERROR: "31", Severity.WARNING: "33", Severity.INFO: "36"}


def diagnostic_message(d: Diagnostic, lang: str) -> str:
    return render(d.message_key, d.params, lang)


def render_report_text(report: Report, lang: str, color: bool = False) -> list[str]:
    """Lines for one file: one per diagnostic, or a single "no problems" line."""
    if not report.diagnostics:
        return [render("summary.clean", {"path": report.path}, lang)]
    lines = []
    for d in report.diagnostics:
        sev = render(f"severity.{d.severity.value}", None, lang)
        if color:
            sev = f"\033[{_COLORS[d.severity]}m{sev}\033[0m"
        lines.append(f"{report.path}:{d.line}: {sev} {d.rule} {diagnostic_message(d, lang)}")
    return lines


def render_totals(reports: list[Report], lang: str) -> str:
    return render(
        "summary.totals",
        {
            "errors": sum(r.errors for r in reports),
            "warnings": sum(r.warnings for r in reports),
            "infos": sum(r.infos for r in reports),
            "files": len(reports),
        },
        lang,
    )


def report_to_dict(report: Report, lang: str) -> dict[str, Any]:
    """JSON shape: ids, severities, lines, ``message_key`` and ``params`` never change with language."""
    return {
        "path": report.path,
        "encoding": report.encoding,
        "diagnostics": [
            {
                "rule": d.rule,
                "severity": d.severity.value,
                "line": d.line,
                "message_key": d.message_key,
                "params": d.params,
                "message": diagnostic_message(d, lang),
                "fixable": d.fixable,
            }
            for d in report.diagnostics
        ],
    }


def render_rule_list(lang: str) -> list[str]:
    lines = [render("list.header", None, lang)]
    for rule, severities in RULES.items():
        sev = "/".join(render(f"severity.{s.value}", None, lang) for s in severities)
        # pad by display width: Hangul is two columns wide
        pad = " " * max(1, 15 - sum(2 if ord(c) > 0x2E80 else 1 for c in sev))
        lines.append(f"{rule}  {sev}{pad}{render('rule.' + rule, None, lang)}")
    return lines
