"""The pre-commit hook definition must stay consistent (no YAML dependency)."""
import re
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / ".pre-commit-hooks.yaml"


def _field(text: str, key: str) -> str:
    m = re.search(rf"^\s*-?\s*{key}:\s*(.+)$", text, re.M)
    assert m, key
    return m.group(1).strip().strip("'")


def test_hook_definition_fields_and_pattern():
    text = HOOKS.read_text(encoding="utf-8")
    assert _field(text, "id") == "modelfile-doctor"
    assert _field(text, "entry") == "modelfile-doctor"
    assert _field(text, "language") == "python"
    pattern = re.compile(_field(text, "files"))
    assert pattern.search("Modelfile")
    assert pattern.search("sub/Modelfile.x")
    assert not pattern.search("README.md")
