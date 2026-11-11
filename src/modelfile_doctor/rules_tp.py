"""TP rules: structure checks for a Go ``text/template`` TEMPLATE."""

from __future__ import annotations

import difflib

from .gotemplate import BRANCHES, KNOWN_FIELDS, OPENERS, fields_in, lex
from .report import Diagnostic, Severity


def check_template(text: str, start_line: int) -> list[Diagnostic]:
    """Check ``text``; ``start_line`` is the Modelfile line where the template text begins.

    A line ``n`` inside the template is reported as ``start_line + n - 1``.
    """
    diags: list[Diagnostic] = []

    def at(rel: int) -> int:
        return start_line + rel - 1

    actions, problems = lex(text)
    for p in problems:
        message_id = "diag.TP001.unclosed" if p.code == "unclosed_action" else "diag.TP001.stray"
        diags.append(Diagnostic("TP001", Severity.ERROR, at(p.line), message_id))

    # Jinja leftovers: `{%` and `{#` are literal text for Go, which silently breaks the prompt.
    for lineno, line in enumerate(text.splitlines() or [text], start=1):
        for token in ("{%", "{#"):
            if token in line:
                diags.append(Diagnostic("TP002", Severity.ERROR, at(lineno), "diag.TP002", {"token": token}))

    stack: list[tuple[str, int]] = []
    used: set[str] = set()
    seen_fields: set[tuple[str, int]] = set()
    for act in actions:
        if act.kind in OPENERS:
            stack.append((act.kind, act.line))
        elif act.kind == "end":
            if stack:
                stack.pop()
            else:
                diags.append(Diagnostic("TP003", Severity.ERROR, at(act.line), "diag.TP003", {"action": "end"}))
        elif act.kind in BRANCHES:
            if not stack or stack[-1][0] not in ("if", "range", "with"):
                diags.append(Diagnostic("TP003", Severity.ERROR, at(act.line), "diag.TP003", {"action": "else"}))
        for name in fields_in(act.body):
            used.add(name)
            if name not in KNOWN_FIELDS and (name, act.line) not in seen_fields:
                seen_fields.add((name, act.line))
                close = difflib.get_close_matches(name, sorted(KNOWN_FIELDS), n=1, cutoff=0.7)
                if close:
                    diags.append(Diagnostic(
                        "TP005", Severity.WARNING, at(act.line), "diag.TP005.suggest",
                        {"name": name, "suggestion": close[0]},
                    ))
                else:
                    diags.append(Diagnostic("TP005", Severity.WARNING, at(act.line), "diag.TP005", {"name": name}))
    for kind, line in stack:
        diags.append(Diagnostic("TP004", Severity.ERROR, at(line), "diag.TP004", {"block": kind}))

    if "Messages" in used and used & {"Prompt", "Response"}:
        diags.append(Diagnostic("TP006", Severity.INFO, start_line, "diag.TP006"))
    return diags
