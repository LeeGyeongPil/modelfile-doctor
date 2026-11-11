"""Bytes to text, detecting the encodings Windows tools like to produce."""

from __future__ import annotations

import codecs

from .errors import ModelfileReadError


def _looks_like_utf16(raw: bytes) -> str | None:
    """Guess BOM-less UTF-16 from the share of NUL bytes at even or odd offsets."""
    sample = raw[:4096]
    if len(sample) < 4 or len(sample) % 2:
        sample = sample[: len(sample) - (len(sample) % 2)]
    if len(sample) < 4:
        return None
    even_nul = sample[0::2].count(0) / (len(sample) / 2)
    odd_nul = sample[1::2].count(0) / (len(sample) / 2)
    if odd_nul > 0.3 and even_nul < 0.05:
        return "utf-16-le"
    if even_nul > 0.3 and odd_nul < 0.05:
        return "utf-16-be"
    return None


def decode_modelfile(raw: bytes, path: str = "<bytes>") -> tuple[str, str]:
    """Return ``(text, encoding_name)``.

    Encoding names: ``utf-8``, ``utf-8-bom``, ``utf-16-bom``, ``utf-16-le``, ``utf-16-be``.
    Raises :class:`ModelfileReadError` (``decode.invalid``) when the bytes are not text.
    """
    try:
        if raw.startswith(codecs.BOM_UTF8):
            return raw[3:].decode("utf-8"), "utf-8-bom"
        if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return raw.decode("utf-16"), "utf-16-bom"
        guess = _looks_like_utf16(raw)
        if guess:
            return raw.decode(guess), guess
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError as exc:
        raise ModelfileReadError("decode.invalid", {"path": path, "offset": exc.start}) from exc
