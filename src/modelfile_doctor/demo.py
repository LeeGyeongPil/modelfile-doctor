"""`modelfile-doctor demo`: a practice run on a synthetic GGUF.

The GGUF written here has a ChatML chat template and special tokens but no weights.
The checks themselves are the real rule engine, not canned output.
"""

from __future__ import annotations

import os
import tempfile
from typing import Callable

from .core import lint_path
from .errors import ModelfileReadError
from .gguf_header import write_minimal_gguf
from .i18n import render
from .output import render_report_text, render_totals

GGUF_NAME = "synthetic-chatml.gguf"

CHATML_JINJA = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>' + '\\n' }}"
    "{% endfor %}{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"
)
TOKENS = ["<unk>", "<|endoftext|>", "<|im_start|>", "<|im_end|>", "hello", "world"]
TOKEN_TYPES = [2, 3, 3, 3, 1, 1]  # 3 = control token in the GGUF spec
EOS_ID = 3

GOOD = f'''FROM ./{GGUF_NAME}
PARAMETER temperature 0.7
PARAMETER stop "<|im_end|>"
TEMPLATE """{{{{- range .Messages }}}}<|im_start|>{{{{ .Role }}}}
{{{{ .Content }}}}<|im_end|>
{{{{ end }}}}<|im_start|>assistant
"""
'''

BAD = f'''FROM ./{GGUF_NAME}
PARAMETER TEMPERATURE 0.7
PARAMETER stop "</s>"
TEMPLATE """[INST] {{{{ .Prompt }}}} [/INST]"""
'''


def write_fixtures(directory: str) -> None:
    """Create the synthetic GGUF and the two Modelfiles in ``directory``."""
    try:
        os.makedirs(directory, exist_ok=True)
        for name, text in (("Modelfile.good", GOOD), ("Modelfile.bad", BAD)):
            with open(os.path.join(directory, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        write_minimal_gguf(
            os.path.join(directory, GGUF_NAME),
            chat_template=CHATML_JINJA,
            tokens=TOKENS,
            token_types=TOKEN_TYPES,
            eos_token_id=EOS_ID,
        )
    except OSError as exc:
        raise ModelfileReadError(
            "io.cannot_create", {"path": directory, "detail": exc.strerror or type(exc).__name__}
        ) from exc


def run_demo(out: str | None, lang: str, write: Callable[[str], None], color: bool = False) -> int:
    """Run the demo, printing through ``write``. Returns the exit code (0 on success)."""
    if out is not None:
        write_fixtures(out)  # fail before printing anything if the directory is unusable
    write(render("demo.banner", None, lang))
    if out is None:
        with tempfile.TemporaryDirectory(prefix="modelfile-doctor-") as tmp:
            write(render("demo.dir_temp", {"path": tmp}, lang))
            _check(tmp, lang, write, color)
    else:
        write(render("demo.dir_kept", {"path": out}, lang))
        _check(out, lang, write, color, already_written=True)
    write(render("demo.lesson", None, lang))
    return 0


def _check(directory: str, lang: str, write: Callable[[str], None], color: bool, already_written: bool = False) -> None:
    if not already_written:
        write_fixtures(directory)
    reports = []
    for name in ("Modelfile.good", "Modelfile.bad"):
        report = lint_path(os.path.join(directory, name))
        report.path = name  # show the short name, not the temporary directory
        reports.append(report)
        write("")
        for line in render_report_text(report, lang, color):
            write(line)
    write("")
    write(render_totals(reports, lang))
