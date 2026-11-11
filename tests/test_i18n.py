import builtins
import json
import re
import socket
import string

import pytest

from modelfile_doctor import DoctorError, GGUFError, lint_path, render_error
from modelfile_doctor.cli import main
from modelfile_doctor.i18n import catalog, render, resolve_lang
from modelfile_doctor.report import RULES

HANGUL = re.compile("[가-힣]")
ALL_ERROR_CODES = [
    "cli.usage", "cli.bad_lang", "cli.bad_format", "cli.no_paths", "cli.unknown_rule",
    "io.not_found", "io.permission", "io.is_directory", "io.other", "io.cannot_create", "modelfile.is_gguf", "modelfile.too_large", "decode.invalid",
    "gguf.bad_magic", "gguf.truncated", "gguf.unsupported_version", "gguf.unsupported_type", "gguf.bad_value",
    "ollama.unreachable", "ollama.timeout", "ollama.http_error", "ollama.model_not_found", "ollama.bad_response",
]


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_catalog_keys_and_placeholders_match():
    en, ko = catalog("en"), catalog("ko")
    assert set(en) == set(ko)
    for key in en:
        assert placeholders(en[key]) == placeholders(ko[key]), key
    for rule in RULES:
        assert f"rule.{rule}" in en
    for code in ALL_ERROR_CODES:
        assert f"err.{code}" in en
    assert all(HANGUL.search(v) for k, v in ko.items() if k.startswith(("rule.", "err.")))
    assert not any(HANGUL.search(v) for v in en.values())


def test_every_message_key_used_in_rules_exists():
    import pathlib

    src = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path(__file__).parent.parent.joinpath("src").rglob("rules_*.py"))
    src += pathlib.Path(__file__).parent.parent.joinpath("src/modelfile_doctor/core.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'"(diag\.[A-Za-z0-9_.]+)"', src))
    assert keys
    assert keys <= set(catalog("en"))


def test_lang_precedence():
    assert resolve_lang("ko", {"MODELFILE_DOCTOR_LANG": "en"}) == "ko"
    assert resolve_lang(None, {"MODELFILE_DOCTOR_LANG": "ko", "LC_ALL": "en_US.UTF-8"}) == "ko"
    assert resolve_lang(None, {"LC_ALL": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}) == "ko"
    assert resolve_lang(None, {"LC_ALL": "C.UTF-8", "LANG": "ko_KR.UTF-8"}) == "en"
    assert resolve_lang(None, {"LC_ALL": "", "LC_MESSAGES": "ko_KR", "LANG": "fr_FR"}) == "ko"
    assert resolve_lang(None, {"LANG": "ko_KR.UTF-8"}) == "ko"
    assert resolve_lang(None, {"LANG": "fr_FR.UTF-8"}) == "en"
    assert resolve_lang(None, {}) == "en"


def test_env_var_picks_language(monkeypatch, capsys):
    monkeypatch.setenv("MODELFILE_DOCTOR_LANG", "ko")
    main(["--list-rules"])
    assert HANGUL.search(capsys.readouterr().out)
    main(["--lang", "en", "--list-rules"])
    assert not HANGUL.search(capsys.readouterr().out)


@pytest.mark.parametrize("lang,has_hangul", [("ko", True), ("en", False)])
def test_help_and_diagnostics_per_language(lang, has_hangul, tmp_path, capsys):
    f = tmp_path / "Modelfile"
    f.write_text("FROM qwen3\nPARAMETER TEMPERATURE 1\n", encoding="utf-8")
    for args in (["--help"], ["demo", "--help"], ["inspect", "--help"], ["--list-rules"], [str(f)]):
        main(["--lang", lang, *args])
        out = capsys.readouterr().out
        assert bool(HANGUL.search(out)) is has_hangul, args
        assert "{" not in out.replace("{{", "")
        if args == ["--list-rules"] and lang == "ko":
            assert not re.search(r"warning|error|info", out), out
        if args == ["--list-rules"] and lang == "en":
            assert "warning" in out and "error" in out
    main(["--lang", lang, "--format", "json", str(f)])
    data = json.loads(capsys.readouterr().out)
    assert all(bool(HANGUL.search(d["message"])) is has_hangul for d in data[0]["diagnostics"])


def test_library_errors_are_code_and_params(tmp_path):
    with pytest.raises(DoctorError) as info:
        lint_path(tmp_path / "missing")
    err = info.value
    assert err.code == "io.not_found" and err.params == {"path": str(tmp_path / "missing")}
    assert str(err).startswith("io.not_found")
    assert not HANGUL.search(str(err))
    assert "Cannot find" in render_error(err, "en") and HANGUL.search(render_error(err, "ko"))
    assert isinstance(GGUFError("gguf.truncated", {"path": "x"}), DoctorError)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def scenario_not_found(tmp_path, stub, mp):
    return [str(tmp_path / "missing")]


def scenario_directory(tmp_path, stub, mp):
    return [str(tmp_path)]


def scenario_permission(tmp_path, stub, mp):
    f = tmp_path / "Modelfile"
    f.write_text("FROM x\n")
    real_open = builtins.open

    def fake_open(file, *a, **k):
        if str(file) == str(f):
            raise PermissionError(13, "denied")
        return real_open(file, *a, **k)

    mp.setattr("modelfile_doctor.core.open", fake_open, raising=False)
    return [str(f)]


def scenario_undecodable(tmp_path, stub, mp):
    f = tmp_path / "Modelfile"
    f.write_bytes(b"FROM x\n\x80\x81\xfe\n")
    return [str(f)]


def _inspect_file(tmp_path, data):
    f = tmp_path / "x.gguf"
    f.write_bytes(data)
    return ["inspect", str(f)]


def scenario_bad_magic(tmp_path, stub, mp):
    return _inspect_file(tmp_path, b"NOTGGUF" * 8)


def scenario_truncated(tmp_path, stub, mp):
    return _inspect_file(tmp_path, b"GGUF" + (3).to_bytes(4, "little") + (0).to_bytes(8, "little") + (5).to_bytes(8, "little"))


def scenario_version(tmp_path, stub, mp):
    return _inspect_file(tmp_path, b"GGUF" + (9).to_bytes(4, "little") + b"\0" * 16)


def scenario_inspect_missing(tmp_path, stub, mp):
    return ["inspect", str(tmp_path / "nope.gguf")]


def _name_ref(tmp_path):
    f = tmp_path / "Modelfile"
    f.write_text("FROM qwen3:4b\n")
    return str(f)


def scenario_refused(tmp_path, stub, mp):
    return ["--ollama", f"http://127.0.0.1:{_free_port()}", _name_ref(tmp_path)]


def scenario_http_500(tmp_path, stub, mp):
    stub.status = 500
    return ["--ollama", stub.url, _name_ref(tmp_path)]


def scenario_http_404(tmp_path, stub, mp):
    stub.status = 404
    return ["--ollama", stub.url, _name_ref(tmp_path)]


def scenario_bad_json(tmp_path, stub, mp):
    stub.raw = b"<html>not json</html>"
    return ["--ollama", stub.url, _name_ref(tmp_path)]


def scenario_json_not_object(tmp_path, stub, mp):
    stub.raw = b"[1, 2]"
    return ["--ollama", stub.url, _name_ref(tmp_path)]


def scenario_bad_scheme(tmp_path, stub, mp):
    return ["--ollama", "http://127.0.0.1:1", _name_ref(tmp_path)]


def scenario_usage(tmp_path, stub, mp):
    return ["--bogus"]


def scenario_missing_value(tmp_path, stub, mp):
    return ["--select"]


def scenario_bad_format(tmp_path, stub, mp):
    return ["--format", "xml", _name_ref(tmp_path)]


def scenario_no_paths(tmp_path, stub, mp):
    return []


def scenario_unknown_rule(tmp_path, stub, mp):
    return ["--ignore", "ZZ99", _name_ref(tmp_path)]


def scenario_gguf_as_modelfile(tmp_path, stub, mp):
    from modelfile_doctor.demo import write_fixtures

    write_fixtures(str(tmp_path / "d"))
    return [str(tmp_path / "d" / "synthetic-chatml.gguf")]


def scenario_too_large(tmp_path, stub, mp):
    f = tmp_path / "Modelfile"
    f.write_bytes(b"# " + b"x" * (5 * 1024 * 1024))
    return [str(f)]


def scenario_demo_out_not_directory(tmp_path, stub, mp):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    return ["demo", "--out", str(blocker / "sub")]


def scenario_inspect_no_path(tmp_path, stub, mp):
    return ["inspect"]


SCENARIOS = [
    scenario_not_found, scenario_directory, scenario_permission, scenario_undecodable,
    scenario_bad_magic, scenario_truncated, scenario_version, scenario_inspect_missing,
    scenario_refused, scenario_http_500, scenario_http_404, scenario_bad_json, scenario_json_not_object,
    scenario_bad_scheme, scenario_usage, scenario_missing_value, scenario_bad_format, scenario_no_paths,
    scenario_unknown_rule, scenario_inspect_no_path,
    scenario_gguf_as_modelfile, scenario_too_large, scenario_demo_out_not_directory,
]


@pytest.mark.parametrize("lang", ["ko", "en"])
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda f: f.__name__.removeprefix("scenario_"))
def test_every_error_path_localized(scenario, lang, tmp_path, ollama_stub, monkeypatch, capsys):
    args = scenario(tmp_path, ollama_stub, monkeypatch)
    code = main(["--lang", lang, *args])
    cap = capsys.readouterr()
    assert code == 2
    assert "Traceback" not in cap.err
    assert bool(HANGUL.search(cap.err)) is (lang == "ko"), cap.err
    assert not re.search(r"\{[a-z_]+\}", cap.err), cap.err
    assert cap.err.strip()
    assert "Traceback" not in cap.out
    if scenario.__name__ == "scenario_gguf_as_modelfile":
        assert ("GGUF" in cap.err) and "UTF-8" not in cap.err and "inspect" in cap.err
    if scenario.__name__ == "scenario_demo_out_not_directory":
        assert cap.out == "", cap.out  # no banner after the error


def test_every_error_code_is_exercised_or_renderable():
    for code in ALL_ERROR_CODES:
        params = {"path": "p", "detail": "d", "offset": 1, "version": 9, "type": 99, "url": "u", "status": 500,
                  "name": "n", "value": "v", "limit_mib": 4}
        for lang in ("en", "ko"):
            text = render_error(DoctorError(code, params), lang)
            assert text != f"err.{code}" and not re.search(r"\{[a-z_]+\}", text)
