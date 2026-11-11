"""Find role and control tokens in chat templates."""

from __future__ import annotations

import re

from .gguf_header import TOKEN_CONTROL, TOKEN_USER_DEFINED, GGUFMetadata

# Token-shaped strings: <|im_start|>, [INST], <<SYS>>, </s>, <start_of_turn>, <｜User｜> ...
TOKEN_RE = re.compile(
    r"<\|[^|<>\s]{1,40}\|>"
    r"|<｜[^｜<>\s]{1,40}｜>"
    r"|\[/?INST\]"
    r"|<</?SYS>>"
    r"|</?s>"
    r"|</?(?:start|end)_of_turn>"
)

_TURN_END_RE = re.compile(
    r"^(?:<\|(?:im_end|eot_id|eom_id|end|endoftext|end_of_text)\|>|<end_of_turn>|</s>|<｜end▁of▁sentence｜>)$"
)


def find_tokens(text: str) -> list[str]:
    """Token-shaped strings in ``text`` in first-seen order, without duplicates."""
    return list(dict.fromkeys(TOKEN_RE.findall(text)))


def model_role_tokens(meta: GGUFMetadata) -> list[str]:
    """Role/control tokens the model's own chat template relies on.

    Control and user-defined vocabulary entries that appear in the template, plus
    token-shaped strings found by regex. BOS is excluded (Ollama adds it itself);
    the EOS token counts when the template mentions ``eos_token`` or spells it out.
    """
    template = meta.chat_template or ""
    found: list[str] = []
    if meta.token_types and len(meta.token_types) == len(meta.tokens):
        for tok, kind in zip(meta.tokens, meta.token_types):
            if kind in (TOKEN_CONTROL, TOKEN_USER_DEFINED) and tok and tok in template:
                found.append(tok)
    found.extend(find_tokens(template))
    if meta.eos_token and re.search(r"\beos_token\b", template):
        found.append(meta.eos_token)
    bos = meta.bos_token
    return [t for t in dict.fromkeys(found) if t != bos and t not in ("<s>",)]


def turn_end_tokens(meta: GGUFMetadata, role_tokens: list[str]) -> list[str]:
    """Tokens that end an assistant turn: EOS, EOT and well-known end markers."""
    out = [t for t in (meta.eos_token, meta.eot_token) if t]
    out.extend(t for t in role_tokens if _TURN_END_RE.match(t))
    return list(dict.fromkeys(out))
