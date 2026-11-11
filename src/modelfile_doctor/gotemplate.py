"""A small lexer for Go ``text/template`` (what Ollama's TEMPLATE uses).

It does not evaluate templates. It finds the ``{{ ... }}`` actions (honouring trim markers,
comments and quoted strings), tracks block nesting and collects ``.Field`` references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

OPENERS = ("if", "range", "with", "define", "block")
BRANCHES = ("else",)

# Variables Ollama passes to templates (template/template.go, docs/template.mdx; checked 2026-11-12).
KNOWN_FIELDS = frozenset({
    "System", "Prompt", "Response", "Suffix", "Messages", "Tools",
    "Role", "Content", "ToolCalls", "ToolName", "ToolCallID", "Thinking", "Think", "IsThinkSet",
    "Function", "Name", "Description", "Parameters", "Arguments", "Type", "Properties", "Required", "Enum",
    "ID", "Index",
})

_FIELD = re.compile(r"(?<![0-9])\.([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class Action:
    kind: str  # first word: "if", "end", "range", "else", "comment", "expr", ...
    body: str
    line: int  # 1-based line inside the template where the action starts


@dataclass
class LexProblem:
    code: str  # "unclosed_action" | "stray_close"
    line: int


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def lex(text: str) -> tuple[list[Action], list[LexProblem]]:
    actions: list[Action] = []
    problems: list[LexProblem] = []
    pos = 0
    n = len(text)
    while pos < n:
        start = text.find("{{", pos)
        if start == -1:
            stray = text.find("}}", pos)
            if stray != -1:
                problems.append(LexProblem("stray_close", _line_of(text, stray)))
            break
        stray = text.find("}}", pos, start)
        if stray != -1:
            problems.append(LexProblem("stray_close", _line_of(text, stray)))
        i = start + 2
        if i + 1 < n and text[i] == "-" and text[i + 1] in " \t\r\n":
            i += 1  # left trim marker
        body_start = i
        # comment: "/*" right after the delimiter (spaces allowed after a trim marker)
        probe = body_start
        while probe < n and text[probe] in " \t\r\n":
            probe += 1
        if text.startswith("/*", probe):
            end_comment = text.find("*/", probe + 2)
            close = text.find("}}", end_comment + 2) if end_comment != -1 else -1
            if end_comment == -1 or close == -1:
                problems.append(LexProblem("unclosed_action", _line_of(text, start)))
                break
            actions.append(Action("comment", "", _line_of(text, start)))
            pos = close + 2
            continue
        # scan the action body, skipping quoted strings
        j = body_start
        close = -1
        while j < n:
            ch = text[j]
            if ch in "\"'":
                k = j + 1
                while k < n and text[k] != ch and text[k] != "\n":
                    k += 2 if text[k] == "\\" else 1
                j = k + 1
                continue
            if ch == "`":
                k = text.find("`", j + 1)
                if k == -1:
                    break
                j = k + 1
                continue
            if text.startswith("}}", j):
                close = j
                break
            j += 1
        if close == -1:
            problems.append(LexProblem("unclosed_action", _line_of(text, start)))
            break
        body = text[body_start:close]
        if body.endswith((" -", "\t-", "\n-")) or body == "-":
            body = body[:-1]  # right trim marker
        body = body.strip()
        word = re.match(r"[A-Za-z_]+", body)
        kind = word.group(0) if word else "expr"
        actions.append(Action(kind, body, _line_of(text, start)))
        pos = close + 2
    return actions, problems


def strip_strings(body: str) -> str:
    """Remove quoted strings from an action body so ``".x"`` is not read as a field."""
    return re.sub(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`[^`]*`', '""', body)


def fields_in(body: str) -> list[str]:
    return _FIELD.findall(strip_strings(body))
