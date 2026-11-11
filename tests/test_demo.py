import os
import re
import subprocess
import sys

from modelfile_doctor.cli import main


def test_demo_reproduces_mismatch_lesson(capsys):
    assert main(["demo", "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("practice fixture")
    assert "Modelfile.good: no problems" in out
    for rule in ("CT001", "CT002", "CT003", "CT004", "MF011"):
        assert rule in out
    assert not re.search(r"Modelfile\.good:\d", out)


def test_demo_removes_its_temporary_directory(capsys):
    main(["demo"])
    out = capsys.readouterr().out
    tmp = re.search(r"\((.+modelfile-doctor-[^)]+)\)", out).group(1)
    assert not os.path.exists(tmp)


def test_demo_out_keeps_files_and_is_korean(tmp_path, capsys):
    target = tmp_path / "fx"
    assert main(["demo", "--lang", "ko", "--out", str(target)]) == 0
    out = capsys.readouterr().out
    assert "연습용 합성 GGUF" in out
    assert {p.name for p in target.iterdir()} == {"Modelfile.good", "Modelfile.bad", "synthetic-chatml.gguf"}
    assert main([str(target / "Modelfile.bad")]) == 1  # the kept files can be checked again by hand


def test_demo_out_unwritable_is_exit_2(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert main(["demo", "--out", str(blocker / "sub")]) == 2
    assert "Traceback" not in capsys.readouterr().err


def _run(args, **env):
    clean = {k: v for k, v in os.environ.items() if k not in ("LANG", "LC_ALL", "LC_MESSAGES", "MODELFILE_DOCTOR_LANG")}
    clean.update(env)
    return subprocess.run(
        [sys.executable, "-m", "modelfile_doctor", *args],
        capture_output=True, text=True, encoding="utf-8", env=clean, timeout=60,
    )


def test_subprocess_follows_locale_env():
    ko = _run(["demo"], LANG="ko_KR.UTF-8", PYTHONIOENCODING="utf-8")
    assert ko.returncode == 0 and "연습용" in ko.stdout
    en = _run(["demo"], LANG="C.UTF-8")
    assert en.returncode == 0 and "practice fixture" in en.stdout
    forced = _run(["demo", "--lang", "en"], LANG="ko_KR.UTF-8")
    assert "practice fixture" in forced.stdout
    unset = _run(["demo"])
    assert "practice fixture" in unset.stdout
