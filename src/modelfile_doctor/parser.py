"""Line-number preserving Modelfile parser.

Follows the observable rules of Ollama's ``parser/parser.go`` (instruction names are
case-insensitive, ``"`` and triple-quote quoting, ``#`` comments, multi-line triple-quoted
values) but keeps the line of every instruction so that all problems can be reported at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# parser.go isValidCommand (Ollama 0.40.15, checked 2026-11-12).
VALID_INSTRUCTIONS = (
    "from", "license", "template", "system", "adapter", "draft", "renderer",
    "parser", "parameter", "message", "requires", "capability",
)

TRIPLE = '"' * 3


@dataclass
class Command:
    """One instruction. ``line`` is 1-based; ``end_line`` differs for triple-quoted values."""

    line: int
    end_line: int
    raw_name: str
    name: str  # lower-cased
    args: str  # value with surrounding quotes removed
    quote: str  # "none" | "double" | "triple"
    terminated: bool = True


@dataclass
class ParsedModelfile:
    commands: list[Command] = field(default_factory=list)

    def all(self, name: str) -> list[Command]:
        return [c for c in self.commands if c.name == name]


def parse_modelfile(text: str) -> ParsedModelfile:
    """Parse ``text``. Never raises: unterminated quotes are flagged on the command."""
    lines = text.splitlines()
    result = ParsedModelfile()
    i = 0
    while i < len(lines):
        lineno = i + 1
        stripped = lines[i].strip()
        i += 1
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        raw_name = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        if rest.startswith(TRIPLE):
            body = rest[3:]
            end = body.find(TRIPLE)
            if end != -1:
                result.commands.append(
                    Command(lineno, lineno, raw_name, raw_name.lower(), body[:end], "triple")
                )
                continue
            buf = [body]
            closed = False
            end_line = lineno
            while i < len(lines):
                cur = lines[i]
                i += 1
                end_line = i
                pos = cur.find(TRIPLE)
                if pos != -1:
                    buf.append(cur[:pos])
                    closed = True
                    break
                buf.append(cur)
            result.commands.append(
                Command(lineno, end_line, raw_name, raw_name.lower(), "\n".join(buf), "triple", closed)
            )
        elif rest.startswith('"'):
            closed = len(rest) >= 2 and rest.endswith('"')
            value = rest[1:-1] if closed else rest[1:]
            result.commands.append(
                Command(lineno, lineno, raw_name, raw_name.lower(), value, "double", closed)
            )
        else:
            result.commands.append(Command(lineno, lineno, raw_name, raw_name.lower(), rest, "none"))
    return result


def split_parameter(cmd: Command) -> tuple[str, str, bool]:
    """Split a PARAMETER command into ``(name, value, value_was_quoted)``."""
    if cmd.quote != "none":  # `PARAMETER "x y"` is malformed; treat the whole thing as a name
        return cmd.args, "", False
    parts = cmd.args.split(None, 1)
    name = parts[0] if parts else ""
    value = parts[1].strip() if len(parts) > 1 else ""
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return name, value[1:-1], True
    return name, value, False
