import codecs

import pytest

from modelfile_doctor.decode import decode_modelfile
from modelfile_doctor.errors import ModelfileReadError
from modelfile_doctor.parser import parse_modelfile, split_parameter

TEXT = "FROM x\nPARAMETER temperature 1\n"


@pytest.mark.parametrize(
    "raw,name",
    [
        (TEXT.encode(), "utf-8"),
        (codecs.BOM_UTF8 + TEXT.encode(), "utf-8-bom"),
        (TEXT.encode("utf-16"), "utf-16-bom"),
        (TEXT.encode("utf-16-le"), "utf-16-le"),
        (TEXT.encode("utf-16-be"), "utf-16-be"),
    ],
)
def test_encodings(raw, name):
    text, enc = decode_modelfile(raw)
    assert enc == name
    assert text == TEXT


def test_invalid_bytes_raise_code():
    with pytest.raises(ModelfileReadError) as info:
        decode_modelfile(b"FROM x\n\x80\x81\xfe", "Modelfile")
    assert info.value.code == "decode.invalid"
    assert info.value.params["path"] == "Modelfile"


def test_parser_keeps_lines_and_ignores_case():
    parsed = parse_modelfile('# c\n\nfrom m.gguf\nParameter stop "</s>"\nTEMPLATE """a\nb"""\nSYSTEM hi\n')
    assert [(c.name, c.line, c.end_line) for c in parsed.commands] == [
        ("from", 3, 3), ("parameter", 4, 4), ("template", 5, 6), ("system", 7, 7),
    ]
    assert parsed.all("template")[0].args == "a\nb"
    assert split_parameter(parsed.all("parameter")[0]) == ("stop", "</s>", True)


def test_unterminated_quotes_are_flagged():
    parsed = parse_modelfile('SYSTEM "open\nSYSTEM """never\nclosed\n')
    assert [c.terminated for c in parsed.commands] == [False, False]
    assert [c.line for c in parsed.commands] == [1, 2]


def test_message_and_parameter_triple_quoted_values_span_lines():
    # Inputs mirror Ollama parser_test.go TestParseFileMessages / TestParseFileParameters.
    text = (
        'FROM m.gguf\nMESSAGE system """\nYou are a file parser.\n"""\n'
        'MESSAGE user """Hello\nthere"""\n'
        'PARAMETER stop <|im_end|>\nPARAMETER stop """### User:\n"""\n'
    )
    parsed = parse_modelfile(text)
    assert [(c.name, c.line, c.end_line) for c in parsed.commands] == [
        ("from", 1, 1), ("message", 2, 4), ("message", 5, 6), ("parameter", 7, 7), ("parameter", 8, 9),
    ]
    assert all(c.terminated for c in parsed.commands)
    assert parsed.commands[2].args == "user Hello\nthere"
    assert split_parameter(parsed.commands[4]) == ("stop", "### User:\n", True)


def test_single_line_triple_quoted_parameter_is_unquoted():
    cmd = parse_modelfile('PARAMETER stop """x"""\n').commands[0]
    assert split_parameter(cmd) == ("stop", "x", True)


def test_unterminated_triple_quoted_message_is_flagged():
    parsed = parse_modelfile('MESSAGE user """never\nclosed\n')
    assert [c.terminated for c in parsed.commands] == [False]
