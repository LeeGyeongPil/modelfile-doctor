"""Shared fixtures: locale pinning, synthetic GGUF factory, Ollama stub server."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

import pytest

LOCALE_VARS = ("MODELFILE_DOCTOR_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "OLLAMA_HOST", "NO_COLOR")


@pytest.fixture(autouse=True)
def pinned_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test independent of the developer's shell locale (English by default)."""
    for name in LOCALE_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODELFILE_DOCTOR_LANG", "en")


CHATML_JINJA = (
    "{% for message in messages %}{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>' + '\\n' }}"
    "{% endfor %}{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"
)
LLAMA2_JINJA = (
    "{% for m in messages %}{% if m['role'] == 'user' %}{{ '[INST] ' + m['content'] + ' [/INST]' }}"
    "{% else %}{{ ' ' + m['content'] + ' </s>' }}{% endif %}{% endfor %}"
)
LLAMA3_JINJA = (
    "{% for m in messages %}{{ '<|start_header_id|>' + m['role'] + '<|end_header_id|>\\n\\n' + m['content'] + '<|eot_id|>' }}"
    "{% endfor %}{% if add_generation_prompt %}{{ '<|start_header_id|>assistant<|end_header_id|>\\n\\n' }}{% endif %}"
)

PROFILES = {
    "chatml": dict(
        tokens=["<unk>", "<|endoftext|>", "<|im_start|>", "<|im_end|>", "hello"],
        types=[2, 3, 3, 3, 1], eos=3, bos=None, template=CHATML_JINJA,
    ),
    "llama2": dict(
        tokens=["<unk>", "<s>", "</s>", "[INST]", "[/INST]", "hello"],
        types=[2, 3, 3, 4, 4, 1], eos=2, bos=1, template=LLAMA2_JINJA,
    ),
    "llama3": dict(
        tokens=["<unk>", "<|begin_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>", "hello"],
        types=[2, 3, 3, 3, 3, 1], eos=4, bos=1, template=LLAMA3_JINJA,
    ),
}

CHATML_TEMPLATE = (
    'TEMPLATE """{{- range .Messages }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n'
    '{{ end }}<|im_start|>assistant\n"""\n'
)
LLAMA3_TEMPLATE = (
    'TEMPLATE """{{ range .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>\n\n'
    '{{ .Content }}<|eot_id|>{{ end }}<|start_header_id|>assistant<|end_header_id|>\n\n"""\n'
)


@pytest.fixture
def make_gguf() -> Callable[..., Path]:
    """Write a small synthetic GGUF with the reference writer (gguf-py), optionally with a big tensor."""
    gguf = pytest.importorskip("gguf")
    np = pytest.importorskip("numpy")

    def factory(path: Path, profile: str = "chatml", context_length: int = 4096, tensor_mb: int = 0) -> Path:
        p = PROFILES[profile]
        w = gguf.GGUFWriter(str(path), "llama")
        w.add_name("synthetic")
        w.add_context_length(context_length)
        w.add_tokenizer_model("gpt2")
        w.add_token_list(p["tokens"])
        w.add_token_types(p["types"])
        w.add_eos_token_id(p["eos"])
        if p["bos"] is not None:
            w.add_bos_token_id(p["bos"])
        w.add_chat_template(p["template"])
        rows = max(1, tensor_mb) * 256
        w.add_tensor("token_embd.weight", np.zeros((rows, 1024), dtype=np.float32))
        w.write_header_to_file()
        w.write_kv_data_to_file()
        w.write_tensors_to_file()
        w.close()
        return path

    return factory


class OllamaStub:
    def __init__(self) -> None:
        self.status = 200
        self.body: object = {}
        self.raw: bytes | None = None
        self.requests: list[dict] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                stub.requests.append({"path": self.path, "body": json.loads(self.rfile.read(length) or b"{}")})
                payload = stub.raw if stub.raw is not None else json.dumps(stub.body).encode()
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def ollama_stub():
    stub = OllamaStub()
    yield stub
    stub.close()
