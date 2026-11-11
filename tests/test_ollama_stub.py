import os
import socket

import pytest

from modelfile_doctor.cli import main
from modelfile_doctor.ollama import blob_path, default_url
from conftest import CHATML_TEMPLATE

MISMATCH = 'FROM qwen3:4b\nPARAMETER stop "</s>"\nTEMPLATE """[INST] {{ .Prompt }} [/INST]"""\n'


def write_modelfile(tmp_path, text=MISMATCH):
    f = tmp_path / "Modelfile"
    f.write_text(text, encoding="utf-8")
    return str(f)


def show_body(blob):
    return {
        "modelfile": f"# Modelfile\nFROM {blob}\nTEMPLATE \"\"\"x\"\"\"\n",
        "template": "x", "parameters": "stop \"<|im_end|>\"", "capabilities": ["completion"],
        "model_info": {"general.architecture": "qwen3"},
    }


def test_name_reference_compared_via_stub(tmp_path, make_gguf, ollama_stub, capsys):
    blob = make_gguf(tmp_path / "sha256-abc", "chatml")
    ollama_stub.body = show_body(blob)
    code = main(["--ollama", ollama_stub.url, write_modelfile(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    for rule in ("CT001", "CT002", "CT003", "CT004"):
        assert rule in out
    assert ollama_stub.requests == [{"path": "/api/show", "body": {"model": "qwen3:4b"}}]


def test_ollama_flag_does_not_swallow_the_path(tmp_path, make_gguf, capsys, monkeypatch):
    make_gguf(tmp_path / "m.gguf")
    f = write_modelfile(tmp_path, f'FROM {tmp_path}/m.gguf\nPARAMETER stop "<|im_end|>"\n{CHATML_TEMPLATE}')
    assert main(["--ollama", f]) == 0  # local gguf: no server needed
    assert "no problems" in capsys.readouterr().out


def test_name_reference_without_ollama_is_info(tmp_path, capsys):
    code = main(["--format", "json", write_modelfile(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert '"CT010"' in out
    assert '"CT003"' not in out


def test_connection_refused_exit_2(tmp_path, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    code = main(["--ollama", f"http://127.0.0.1:{port}", write_modelfile(tmp_path)])
    cap = capsys.readouterr()
    assert code == 2
    assert "Cannot reach Ollama" in cap.err and "Traceback" not in cap.err


def test_http_404_is_model_not_found(tmp_path, ollama_stub, capsys):
    ollama_stub.status = 404
    assert main(["--ollama", ollama_stub.url, write_modelfile(tmp_path)]) == 2
    assert "does not know the model" in capsys.readouterr().err


def test_blob_missing_is_info_not_failure(tmp_path, ollama_stub, capsys):
    ollama_stub.body = show_body(str(tmp_path / "gone"))
    assert main(["--ollama", ollama_stub.url, write_modelfile(tmp_path)]) == 0
    assert "CT011" in capsys.readouterr().out


def test_blob_path_and_default_url():
    assert blob_path({"modelfile": "FROM /a/b/sha256-1\n"}) == "/a/b/sha256-1"
    assert blob_path({"modelfile": "FROM qwen3\n"}) is None
    assert blob_path({}) is None
    assert default_url({}) == "http://127.0.0.1:11434"
    assert default_url({"OLLAMA_HOST": "0.0.0.0:11434"}) == "http://127.0.0.1:11434"
    assert default_url({"OLLAMA_HOST": "https://gpu.example:443/"}) == "https://gpu.example:443"


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("MODELFILE_DOCTOR_LIVE"), reason="set MODELFILE_DOCTOR_LIVE=1 to talk to a real local Ollama")
def test_live_ollama(tmp_path):
    model = os.environ.get("MODELFILE_DOCTOR_LIVE_MODEL", "qwen3:4b")
    f = tmp_path / "Modelfile"
    f.write_text(f"FROM {model}\n", encoding="utf-8")
    assert main(["--ollama", str(f)]) in (0, 1)
