import json
from pathlib import Path

import pytest

from modelfile_doctor import __version__
from modelfile_doctor.cli import main
from modelfile_doctor.report import RULES

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
GOOD = 'FROM qwen3:4b\nPARAMETER temperature 0.7\n'


def write(tmp_path, text, name="Modelfile"):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return str(f)


def test_json_schema(capsys):
    code = main(["--format", "json", str(EXAMPLES / "Modelfile.syntax-errors")])
    data = json.loads(capsys.readouterr().out)
    assert code == 1
    assert isinstance(data, list) and len(data) == 1
    item = data[0]
    assert set(item) == {"path", "encoding", "diagnostics"}
    assert item["diagnostics"]
    for d in item["diagnostics"]:
        assert set(d) == {"rule", "severity", "line", "message_key", "params", "message", "fixable"}
        assert d["rule"] in RULES and d["message"]


def test_json_ids_do_not_change_with_language(capsys):
    main(["--format", "json", "--lang", "en", str(EXAMPLES / "Modelfile.syntax-errors")])
    en = json.loads(capsys.readouterr().out)
    main(["--format", "json", "--lang", "ko", str(EXAMPLES / "Modelfile.syntax-errors")])
    ko = json.loads(capsys.readouterr().out)
    strip = lambda data: [(d["rule"], d["severity"], d["line"], d["message_key"], d["params"]) for d in data[0]["diagnostics"]]
    assert strip(en) == strip(ko)
    assert [d["message"] for d in en[0]["diagnostics"]] != [d["message"] for d in ko[0]["diagnostics"]]


def test_exit_codes(tmp_path, capsys):
    assert main([write(tmp_path, GOOD)]) == 0
    assert main([write(tmp_path, "PARAMETER temperature 1\n", "a")]) == 1  # MF002 error
    warn = write(tmp_path, GOOD + "PARAMETER temperature 5\n", "w")
    assert main([warn]) == 0
    assert main(["--strict", warn]) == 1
    assert main([str(tmp_path / "missing")]) == 2
    assert main(["--bogus"]) == 2
    assert main(["--format", "xml", warn]) == 2
    assert main([]) == 2
    capsys.readouterr()


def test_error_beats_clean_file_and_missing_file_is_2(tmp_path, capsys):
    good = write(tmp_path, GOOD)
    assert main(["--ignore", "CT010", good, str(tmp_path / "missing")]) == 2
    cap = capsys.readouterr()
    assert "no problems" in cap.out and "Cannot find" in cap.err


def test_select_ignore(tmp_path, capsys):
    f = write(tmp_path, "FROM x.gguf\nPARAMETER TEMPERATURE 1\nSYSTM hi\n".replace("x.gguf", "qwen3"))
    main(["--format", "json", "--select", "MF011", f])
    rules = {d["rule"] for d in json.loads(capsys.readouterr().out)[0]["diagnostics"]}
    assert rules == {"MF011"}
    main(["--format", "json", "--ignore", "MF011,CT", f])
    rules = {d["rule"] for d in json.loads(capsys.readouterr().out)[0]["diagnostics"]}
    assert rules == {"MF004"}
    assert main(["--select", "ZZ9", f]) == 2


def test_list_rules(capsys):
    assert main(["--list-rules"]) == 0
    out = capsys.readouterr().out
    for rule in RULES:
        assert rule in out
    assert "error/warning" in out


def test_version_and_help(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"modelfile-doctor {__version__}"
    assert main(["-h"]) == 0
    assert "--lang" in capsys.readouterr().out


def test_multiple_files_and_options_after_paths(tmp_path, capsys):
    a, b = write(tmp_path, GOOD, "a"), write(tmp_path, GOOD, "b")
    assert main([a, "--no-color", "--ignore", "CT010", b]) == 0
    out = capsys.readouterr().out
    assert out.count("no problems") == 2 and "2 file(s)" in out


def test_version_matches_pyproject():
    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in text


def test_example_files_behave(tmp_path, capsys):
    from modelfile_doctor.demo import write_fixtures

    write_fixtures(str(tmp_path))  # creates synthetic-chatml.gguf next to the copies
    for name in ("Modelfile.chatml-good", "Modelfile.mismatch"):
        (tmp_path / name).write_text((EXAMPLES / name).read_text(encoding="utf-8"), encoding="utf-8")
    assert main([str(tmp_path / "Modelfile.chatml-good")]) == 0
    capsys.readouterr()
    assert main(["--format", "json", str(tmp_path / "Modelfile.mismatch")]) == 1
    data = json.loads(capsys.readouterr().out)
    assert {"CT001", "CT002", "CT003", "CT004"} <= {d["rule"] for d in data[0]["diagnostics"]}
