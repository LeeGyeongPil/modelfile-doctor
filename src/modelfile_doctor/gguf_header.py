"""Dependency-free GGUF key/value reader (v2/v3) plus a minimal tensor-less writer.

Only the header and the key/value section are read. Tensor infos and tensor data are never
touched, so multi-gigabyte files are read in milliseconds.
Format: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from .errors import GGUFError, from_oserror

MAGIC = b"GGUF"
TOKEN_CONTROL = 3
TOKEN_USER_DEFINED = 4

_FIXED = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
_SIZES = {t: struct.calcsize(f) for t, f in _FIXED.items()}
T_STRING, T_ARRAY = 8, 9

_WANTED_EXACT = {
    "general.architecture", "general.name", "tokenizer.chat_template",
    "tokenizer.ggml.tokens", "tokenizer.ggml.token_type",
    "tokenizer.ggml.eos_token_id", "tokenizer.ggml.bos_token_id", "tokenizer.ggml.eot_token_id",
}


@dataclass
class GGUFMetadata:
    path: str = ""
    version: int = 0
    tensor_count: int = 0
    kv_count: int = 0
    kv_end: int = 0  # file offset just after the key/value section
    architecture: str | None = None
    name: str | None = None
    context_length: int | None = None
    chat_template: str | None = None
    tokens: list[str] = field(default_factory=list)
    token_types: list[int] = field(default_factory=list)
    eos_token_id: int | None = None
    bos_token_id: int | None = None
    eot_token_id: int | None = None

    def token(self, token_id: int | None) -> str | None:
        if token_id is None or not 0 <= token_id < len(self.tokens):
            return None
        return self.tokens[token_id]

    @property
    def eos_token(self) -> str | None:
        return self.token(self.eos_token_id)

    @property
    def bos_token(self) -> str | None:
        return self.token(self.bos_token_id)

    @property
    def eot_token(self) -> str | None:
        return self.token(self.eot_token_id)


class _Stream:
    def __init__(self, fp: BinaryIO, path: str) -> None:
        self.fp = fp
        self.path = path
        self.pos = 0
        fp.seek(0, os.SEEK_END)
        self.size = fp.tell()
        fp.seek(0)

    def _truncated(self) -> GGUFError:
        return GGUFError("gguf.truncated", {"path": self.path})

    def read(self, n: int) -> bytes:
        if n < 0 or self.pos + n > self.size:
            raise self._truncated()
        data = self.fp.read(n)
        if len(data) != n:
            raise self._truncated()
        self.pos += n
        return data

    def skip(self, n: int) -> None:
        if n < 0 or self.pos + n > self.size:
            raise self._truncated()
        self.fp.seek(n, os.SEEK_CUR)
        self.pos += n

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def string(self) -> str:
        raw = self.read(self.u64())
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GGUFError("gguf.bad_value", {"path": self.path}) from exc

    def skip_string(self) -> None:
        self.skip(self.u64())


def _unsupported(path: str, vtype: int) -> GGUFError:
    return GGUFError("gguf.unsupported_type", {"path": path, "type": vtype})


def _read_value(s: _Stream, vtype: int) -> Any:
    if vtype in _FIXED:
        return struct.unpack(_FIXED[vtype], s.read(_SIZES[vtype]))[0]
    if vtype == T_STRING:
        return s.string()
    if vtype == T_ARRAY:
        etype = s.u32()
        count = s.u64()
        if count > s.size:
            raise s._truncated()
        return [_read_value(s, etype) for _ in range(count)]
    raise _unsupported(s.path, vtype)


def _skip_value(s: _Stream, vtype: int) -> None:
    if vtype in _FIXED:
        s.skip(_SIZES[vtype])
    elif vtype == T_STRING:
        s.skip_string()
    elif vtype == T_ARRAY:
        etype = s.u32()
        count = s.u64()
        if etype in _FIXED:
            s.skip(count * _SIZES[etype])
        elif count > s.size:
            raise s._truncated()
        else:
            for _ in range(count):
                _skip_value(s, etype)
    else:
        raise _unsupported(s.path, vtype)


def parse_gguf(fp: BinaryIO, path: str = "<stream>") -> GGUFMetadata:
    """Read the metadata from an open binary file object (positioned anywhere)."""
    s = _Stream(fp, path)
    if s.size < 4 or s.read(4) != MAGIC:
        raise GGUFError("gguf.bad_magic", {"path": path})
    version = s.u32()
    if version not in (2, 3):
        raise GGUFError("gguf.unsupported_version", {"path": path, "version": version})
    meta = GGUFMetadata(path=path, version=version)
    meta.tensor_count = s.u64()
    meta.kv_count = s.u64()
    ctx: dict[str, int] = {}
    for _ in range(meta.kv_count):
        key = s.string()
        vtype = s.u32()
        wanted = key in _WANTED_EXACT or key.endswith(".context_length")
        if not wanted:
            _skip_value(s, vtype)
            continue
        value = _read_value(s, vtype)
        if key == "general.architecture" and isinstance(value, str):
            meta.architecture = value
        elif key == "general.name" and isinstance(value, str):
            meta.name = value
        elif key == "tokenizer.chat_template" and isinstance(value, str):
            meta.chat_template = value
        elif key == "tokenizer.ggml.tokens" and isinstance(value, list):
            meta.tokens = [str(v) for v in value]
        elif key == "tokenizer.ggml.token_type" and isinstance(value, list):
            meta.token_types = [int(v) for v in value]
        elif key == "tokenizer.ggml.eos_token_id" and isinstance(value, int):
            meta.eos_token_id = value
        elif key == "tokenizer.ggml.bos_token_id" and isinstance(value, int):
            meta.bos_token_id = value
        elif key == "tokenizer.ggml.eot_token_id" and isinstance(value, int):
            meta.eot_token_id = value
        elif key.endswith(".context_length") and isinstance(value, int):
            ctx[key] = value
    if meta.architecture and f"{meta.architecture}.context_length" in ctx:
        meta.context_length = ctx[f"{meta.architecture}.context_length"]
    elif ctx:
        meta.context_length = next(iter(ctx.values()))
    meta.kv_end = s.pos
    return meta


def read_gguf_metadata(path: str | os.PathLike[str]) -> GGUFMetadata:
    """Read GGUF metadata from ``path``. Raises :class:`GGUFError` or an I/O ``DoctorError``."""
    spath = os.fspath(path)
    try:
        with open(spath, "rb") as fp:
            return parse_gguf(fp, spath)
    except OSError as exc:
        raise from_oserror(exc, spath, GGUFError) from exc


# ---------------------------------------------------------------- minimal writer (demo)

def _w_str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _kv_str(key: str, value: str) -> bytes:
    return _w_str(key) + struct.pack("<I", T_STRING) + _w_str(value)


def _kv_u32(key: str, value: int) -> bytes:
    return _w_str(key) + struct.pack("<I", 4) + struct.pack("<I", value)


def write_minimal_gguf(
    path: str | os.PathLike[str],
    *,
    architecture: str = "llama",
    name: str = "practice-fixture",
    context_length: int = 4096,
    chat_template: str,
    tokens: list[str],
    token_types: list[int],
    eos_token_id: int,
    bos_token_id: int | None = None,
) -> None:
    """Write a GGUF v3 file with metadata only (no tensors, no weights)."""
    parts = [
        _kv_str("general.architecture", architecture),
        _kv_str("general.name", name),
        _kv_u32(f"{architecture}.context_length", context_length),
        _kv_str("tokenizer.ggml.model", "gpt2"),
        _w_str("tokenizer.ggml.tokens") + struct.pack("<IIQ", T_ARRAY, T_STRING, len(tokens))
        + b"".join(_w_str(t) for t in tokens),
        _w_str("tokenizer.ggml.token_type") + struct.pack("<IIQ", T_ARRAY, 5, len(token_types))
        + b"".join(struct.pack("<i", t) for t in token_types),
        _kv_u32("tokenizer.ggml.eos_token_id", eos_token_id),
    ]
    if bos_token_id is not None:
        parts.append(_kv_u32("tokenizer.ggml.bos_token_id", bos_token_id))
    parts.append(_kv_str("tokenizer.chat_template", chat_template))
    body = b"".join(parts)
    data = MAGIC + struct.pack("<IQQ", 3, 0, len(parts)) + body
    data += b"\0" * (-len(data) % 32)  # keep the 32-byte alignment readers expect
    try:
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        raise from_oserror(exc, os.fspath(path), GGUFError) from exc
