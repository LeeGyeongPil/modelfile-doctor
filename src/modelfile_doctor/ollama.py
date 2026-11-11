"""Tiny client for a local Ollama server (standard library only)."""

from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Any

from .errors import OllamaError
from .parser import parse_modelfile

DEFAULT_URL = "http://127.0.0.1:11434"
TIMEOUT_SECONDS = 10.0  # /api/show is light, but the server may be busy with a model load


def default_url(env: dict[str, str] | None = None) -> str:
    """``OLLAMA_HOST`` (with or without scheme) or the local default."""
    env = os.environ if env is None else env
    host = (env.get("OLLAMA_HOST") or "").strip()
    if not host:
        return DEFAULT_URL
    if not re.match(r"^https?://", host):
        host = "http://" + host
    return host.replace("//0.0.0.0", "//127.0.0.1").rstrip("/")


def show_model(base_url: str, name: str, timeout: float = TIMEOUT_SECONDS) -> dict[str, Any]:
    """``POST /api/show`` for ``name``. Raises :class:`OllamaError` on any failure."""
    url = base_url.rstrip("/") + "/api/show"
    request = urllib.request.Request(
        url,
        data=json.dumps({"model": name}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 (user-chosen URL)
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise OllamaError("ollama.model_not_found", {"url": base_url, "name": name}) from exc
        raise OllamaError("ollama.http_error", {"url": base_url, "status": exc.code}) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise OllamaError("ollama.timeout", {"url": base_url}) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise OllamaError("ollama.timeout", {"url": base_url}) from exc
        raise OllamaError("ollama.unreachable", {"url": base_url, "detail": str(exc.reason)}) from exc
    except (OSError, ValueError) as exc:  # bad scheme, reset connection, ...
        raise OllamaError("ollama.unreachable", {"url": base_url, "detail": str(exc)}) from exc
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise OllamaError("ollama.bad_response", {"url": base_url}) from exc
    if not isinstance(data, dict):
        raise OllamaError("ollama.bad_response", {"url": base_url})
    return data


def blob_path(show: dict[str, Any]) -> str | None:
    """The local GGUF blob path from the ``modelfile`` text of an ``/api/show`` answer."""
    text = show.get("modelfile")
    if not isinstance(text, str):
        return None
    for cmd in parse_modelfile(text).all("from"):
        arg = cmd.args
        if arg.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", arg):
            return arg
    return None
