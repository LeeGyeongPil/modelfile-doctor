import pytest

from modelfile_doctor import lint_text
from modelfile_doctor.rules_tp import check_template

CHATML = "{{- range .Messages }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n{{ end }}<|im_start|>assistant\n"
LLAMA3 = (
    "{{ if .System }}<|start_header_id|>system<|end_header_id|>\n\n{{ .System }}<|eot_id|>{{ end }}"
    "{{ range .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>\n\n{{ .Content }}<|eot_id|>{{ end }}"
    "<|start_header_id|>assistant<|end_header_id|>\n\n"
)
TOOLS = """{{- if .System }}{{ .System }}{{ end }}
{{- range $i, $_ := .Messages }}
{{- $last := eq (len (slice $.Messages $i)) 1 -}}
{{- if eq .Role "user" }}[INST] {{ if and $.Tools $last }}{{ json $.Tools }}{{ end }}{{ .Content }}[/INST]
{{- else if eq .Role "assistant" }}
{{- if .ToolCalls }}{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ json .Function.Arguments }}}{{ end }}
{{- else }} {{ .Content }}{{ end }}
{{- end }}
{{- end }}
{{/* a comment with }} inside */}}{{ "}}" }}{{ `raw }}` }}
"""
LEGACY = "{{ if .System }}{{ .System }}{{ end }}{{ if .Prompt }}[INST] {{ .Prompt }} [/INST]{{ end }}{{ .Response }}"


def rules(text, start=1):
    return {(d.rule, d.line) for d in check_template(text, start)}


def test_block_balance_and_jinja():
    assert rules("{{ range .Messages }}x") == {("TP004", 1)}
    assert rules("{{ if .System }}a{{ end }}{{ end }}") == {("TP003", 1)}
    assert rules("{{ else }}") == {("TP003", 1)}
    assert rules("{% for m in messages %}x{% endfor %}") == {("TP002", 1)}
    assert rules("{# note #}") == {("TP002", 1)}
    assert rules("{{ .System") == {("TP001", 1)}
    assert rules("a }} b") == {("TP001", 1)}
    assert rules("{{ if .System }}{{ else if .Prompt }}{{ else }}{{ end }}") == set()


def test_unknown_variable_suggestion():
    diags = check_template("{{ .Contnt }} {{ .Zzzzzzz }}", 1)
    assert diags[0].rule == "TP005" and diags[0].params["suggestion"] == "Content"
    assert diags[1].message_key == "diag.TP005" and diags[1].params["name"] == "Zzzzzzz"


@pytest.mark.parametrize("template", [CHATML, LLAMA3, TOOLS, LEGACY], ids=["chatml", "llama3", "tools", "legacy"])
def test_official_templates_are_clean(template):
    assert check_template(template, 1) == []


def test_line_numbers_are_modelfile_based():
    text = 'FROM x\n# c\nTEMPLATE """{{ range .Messages }}\n{{ .Content }}\n{{ end }}{{ end }}\n{{ .Bogus }}"""\n'
    report = lint_text(text, select=["TP"])
    assert {(d.rule, d.line) for d in report.diagnostics} == {("TP003", 5), ("TP005", 6)}


def test_mixed_messages_and_prompt_is_info():
    report = lint_text('FROM x\nTEMPLATE """{{ range .Messages }}{{ end }}{{ .Prompt }}"""\n', select=["TP006"])
    assert [(d.rule, d.line) for d in report.diagnostics] == [("TP006", 2)]
