import pytest

from modelfile_doctor import lint_text
from conftest import CHATML_TEMPLATE, LLAMA3_TEMPLATE

INST_TEMPLATE = 'TEMPLATE """[INST] {{ .Prompt }} [/INST]"""\n'


def ct(report):
    return sorted((d.rule, d.severity.value, d.params.get("token")) for d in report.diagnostics if d.rule.startswith("CT"))


def test_chatml_model_with_inst_template(tmp_path, make_gguf):
    make_gguf(tmp_path / "m.gguf", "chatml")
    text = f'FROM ./m.gguf\nPARAMETER stop "</s>"\n{INST_TEMPLATE}'
    report = lint_text(text, base_dir=str(tmp_path))
    assert ct(report) == [
        ("CT001", "warning", "<|im_end|>"),
        ("CT002", "warning", None),
        ("CT003", "error", "[/INST]"),
        ("CT003", "error", "[INST]"),
        ("CT004", "warning", "</s>"),
    ]
    lines = {d.rule: d.line for d in report.diagnostics}
    assert lines["CT004"] == 2 and lines["CT002"] == 3


@pytest.mark.parametrize(
    "profile,template,stop",
    [("chatml", CHATML_TEMPLATE, "<|im_end|>"), ("llama3", LLAMA3_TEMPLATE, "<|eot_id|>")],
)
def test_matching_template_is_clean(tmp_path, make_gguf, profile, template, stop):
    make_gguf(tmp_path / "m.gguf", profile)
    text = f'FROM ./m.gguf\nPARAMETER temperature 0.7\nPARAMETER stop "{stop}"\n{template}'
    assert lint_text(text, base_dir=str(tmp_path)).diagnostics == []


def test_num_ctx_exceeds_context_length(tmp_path, make_gguf):
    make_gguf(tmp_path / "m.gguf", "chatml", context_length=4096)
    text = f'FROM ./m.gguf\nPARAMETER num_ctx 8192\nPARAMETER stop "<|im_end|>"\n{CHATML_TEMPLATE}'
    report = lint_text(text, base_dir=str(tmp_path))
    assert [(d.rule, d.line) for d in report.diagnostics] == [("CT005", 2)]


def test_token_in_vocab_but_unused_by_chat_template(tmp_path, make_gguf):
    make_gguf(tmp_path / "m.gguf", "chatml")
    template = CHATML_TEMPLATE.replace("assistant\n", "assistant\n<|endoftext|>")
    text = f'FROM ./m.gguf\nPARAMETER stop "<|im_end|>"\n{template}'
    report = lint_text(text, base_dir=str(tmp_path))
    assert [(d.rule, d.severity.value) for d in report.diagnostics] == [("CT003", "warning")]


def test_truncated_gguf_skips_comparison_with_info(tmp_path, make_gguf):
    full = make_gguf(tmp_path / "ok.gguf").read_bytes()
    (tmp_path / "m.gguf").write_bytes(full[:60])
    report = lint_text("FROM ./m.gguf\n", base_dir=str(tmp_path))
    assert [(d.rule, d.params["reason"]) for d in report.diagnostics] == [("CT011", "gguf.truncated")]


def test_directory_from_is_info(tmp_path):
    (tmp_path / "weights").mkdir()
    report = lint_text("FROM ./weights\n", base_dir=str(tmp_path))
    assert [d.rule for d in report.diagnostics] == ["CT011"]
