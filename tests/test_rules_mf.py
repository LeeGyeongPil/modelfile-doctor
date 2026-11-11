from modelfile_doctor import lint_path, lint_text

SYNTAX_ERRORS = """FROM qwen3:4b
PARAMETER TEMPERATURE 0.7
PARAMETER num_ctx 4k
PARAMETER mirostat 2
PARAMETER temperature 5
MESSAGE User hi
SYSTM hi
"""
CLEAN = """FROM qwen3:4b
PARAMETER temperature 0.7
PARAMETER num_ctx 4096
MESSAGE user hi
SYSTEM hi
"""


def pairs(report):
    return {(d.rule, d.line) for d in report.diagnostics}


def test_reports_all_syntax_errors_at_once(tmp_path):
    # UTF-16 without BOM, as Windows PowerShell redirection writes it
    f = tmp_path / "Modelfile"
    f.write_bytes(SYNTAX_ERRORS.encode("utf-16-le"))
    report = lint_path(f, select=["MF"])
    assert report.encoding == "utf-16-le"
    assert pairs(report) == {
        ("MF001", 1), ("MF011", 2), ("MF012", 3), ("MF010", 4), ("MF013", 5), ("MF014", 6), ("MF004", 7),
    }
    by_rule = {d.rule: d for d in report.diagnostics}
    assert by_rule["MF011"].params["suggestion"] == "temperature"
    assert by_rule["MF004"].params["suggestion"] == "SYSTEM"


def test_clean_modelfile_has_no_diagnostics():
    assert lint_text(CLEAN, select=["MF", "TP"]).diagnostics == []


def test_missing_from_and_unterminated_quote():
    report = lint_text('PARAMETER temperature 1\nSYSTEM """hello\n', select=["MF"])
    assert pairs(report) == {("MF002", 1), ("MF003", 2)}


def test_duplicates_and_stop_values():
    text = 'FROM x\nSYSTEM a\nSYSTEM b\nPARAMETER stop\nPARAMETER stop a b\nPARAMETER stop "a b"\n'
    report = lint_text(text, select=["MF015", "MF016"])
    assert pairs(report) == {("MF015", 3), ("MF016", 4), ("MF016", 5)}


def test_from_path_checks(tmp_path):
    (tmp_path / "bad.gguf").write_bytes(b"NOPE" + b"\0" * 16)
    missing = lint_text("FROM ./nope.gguf\n", base_dir=str(tmp_path), select=["MF020"])
    assert missing.diagnostics[0].message_key == "diag.MF020.missing"
    bad = lint_text("FROM ./bad.gguf\n", base_dir=str(tmp_path), select=["MF020"])
    assert bad.diagnostics[0].message_key == "diag.MF020.not_gguf"
    assert lint_text("FROM qwen3:4b\n", base_dir=str(tmp_path), select=["MF020"]).diagnostics == []


def test_parameter_value_forms():
    text = "FROM x\nPARAMETER use_mmap maybe\nPARAMETER use_mmap true\nPARAMETER top_p 1.5\nPARAMETER num_ctx -1\n"
    assert pairs(lint_text(text, select=["MF"])) == {("MF012", 2), ("MF013", 4), ("MF013", 5)}
