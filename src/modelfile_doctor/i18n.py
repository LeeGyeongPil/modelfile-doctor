"""Message catalogs (English and Korean) and language selection."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Mapping

from .errors import DoctorError

LANGS = ("en", "ko")
ENV_VAR = "MODELFILE_DOCTOR_LANG"
_ENV_ORDER = (ENV_VAR, "LC_ALL", "LC_MESSAGES", "LANG")


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict[str, str]:
    """The message table for ``lang`` (``en`` or ``ko``)."""
    if lang not in LANGS:
        raise ValueError(f"unsupported language: {lang!r} (use one of {', '.join(LANGS)})")
    here = os.path.join(os.path.dirname(__file__), "locales", f"{lang}.json")
    with open(here, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_lang(cli_value: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """``--lang`` > ``MODELFILE_DOCTOR_LANG`` > ``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``.

    The first non-empty source decides; anything not starting with ``ko`` is English.
    """
    env = os.environ if env is None else env
    candidates = [cli_value] + [env.get(name) for name in _ENV_ORDER]
    for value in candidates:
        if value:
            return "ko" if value.strip().lower().startswith("ko") else "en"
    return "en"


def render(key: str, params: Mapping[str, Any] | None = None, lang: str = "en") -> str:
    """Render catalog entry ``key`` with ``params``; unknown keys come back as the key."""
    template = catalog(lang).get(key)
    if template is None:
        return key
    try:
        return template.format(**(params or {}))
    except (KeyError, IndexError):
        return template


def render_error(exc: DoctorError, lang: str = "en") -> str:
    """Translate a :class:`DoctorError` using its ``code`` and ``params``."""
    return render(f"err.{exc.code}", exc.params, lang)
