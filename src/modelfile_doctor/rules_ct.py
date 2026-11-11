"""CT rules: compare TEMPLATE and PARAMETER values with the model's GGUF metadata."""

from __future__ import annotations

from .gguf_header import GGUFMetadata
from .params import parse_int
from .parser import ParsedModelfile, split_parameter
from .report import Diagnostic, Severity
from .tokens import TOKEN_RE, find_tokens, model_role_tokens, turn_end_tokens


def check_against_gguf(parsed: ParsedModelfile, meta: GGUFMetadata) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    template_cmds = parsed.all("template")
    template = template_cmds[-1] if template_cmds else None
    template_text = template.args if template else None
    froms = parsed.all("from")
    anchor = froms[0].line if froms else 1

    stops: list[tuple[str, int]] = []
    num_ctx: tuple[int, int] | None = None
    for cmd in parsed.all("parameter"):
        name, value, _ = split_parameter(cmd)
        if name == "stop" and value:
            stops.append((value, cmd.line))
        elif name == "num_ctx":
            parsed_int = parse_int(value)
            if parsed_int is not None:
                num_ctx = (parsed_int, cmd.line)
    stop_values = {v for v, _ in stops}

    vocab = set(meta.tokens)
    role_tokens = model_role_tokens(meta)
    gguf_template = meta.chat_template or ""

    # CT001: turn-end token missing from stop
    for tok in turn_end_tokens(meta, role_tokens):
        if tok not in stop_values:
            line = stops[0][1] if stops else anchor
            diags.append(Diagnostic("CT001", Severity.WARNING, line, "diag.CT001", {"token": tok}))

    if template is not None and template_text is not None:
        # CT002: model role tokens absent from TEMPLATE
        missing = [t for t in role_tokens if t not in template_text]
        if missing:
            diags.append(Diagnostic(
                "CT002", Severity.WARNING, template.line, "diag.CT002", {"tokens": " ".join(missing)}
            ))
        # CT003: token-shaped strings in TEMPLATE the model does not know
        for tok in find_tokens(template_text):
            if tok in ("<s>",) and tok == meta.bos_token:
                continue
            if vocab and tok not in vocab:
                diags.append(Diagnostic("CT003", Severity.ERROR, template.line, "diag.CT003.missing", {"token": tok}))
            elif tok not in role_tokens and tok not in gguf_template and tok != meta.eos_token:
                diags.append(Diagnostic("CT003", Severity.WARNING, template.line, "diag.CT003.unused", {"token": tok}))

    # CT004: token-shaped stop values the model never produces
    for value, line in stops:
        if TOKEN_RE.fullmatch(value) and value not in vocab and value not in gguf_template:
            diags.append(Diagnostic("CT004", Severity.WARNING, line, "diag.CT004", {"token": value}))

    # CT005: num_ctx above the trained context length
    if num_ctx and meta.context_length and num_ctx[0] > meta.context_length:
        diags.append(Diagnostic(
            "CT005", Severity.WARNING, num_ctx[1], "diag.CT005",
            {"num_ctx": num_ctx[0], "context_length": meta.context_length},
        ))
    return diags
