import io
import os

import pytest

from modelfile_doctor.demo import CHATML_JINJA, EOS_ID, TOKEN_TYPES, TOKENS
from modelfile_doctor.errors import GGUFError
from modelfile_doctor.gguf_header import parse_gguf, read_gguf_metadata, write_minimal_gguf


def test_matches_reference_reader(tmp_path, make_gguf):
    gguf = pytest.importorskip("gguf")
    for profile in ("chatml", "llama2", "llama3"):
        path = make_gguf(tmp_path / f"{profile}.gguf", profile, context_length=8192)
        ours = read_gguf_metadata(path)
        ref = gguf.GGUFReader(str(path))
        assert ours.architecture == ref.fields["general.architecture"].contents()
        assert ours.context_length == ref.fields["llama.context_length"].contents() == 8192
        assert ours.chat_template == ref.fields["tokenizer.chat_template"].contents()
        assert ours.tokens == ref.fields["tokenizer.ggml.tokens"].contents()
        assert ours.token_types == list(ref.fields["tokenizer.ggml.token_type"].contents())
        assert ours.eos_token_id == ref.fields["tokenizer.ggml.eos_token_id"].contents()
        bos = ref.fields.get("tokenizer.ggml.bos_token_id")
        assert ours.bos_token_id == (bos.contents() if bos else None)
        assert ours.tensor_count == 1
        assert ours.eos_token == ours.tokens[ours.eos_token_id]


def test_demo_writer_readable_by_reference(tmp_path):
    gguf = pytest.importorskip("gguf")
    path = tmp_path / "w.gguf"
    write_minimal_gguf(path, chat_template=CHATML_JINJA, tokens=TOKENS, token_types=TOKEN_TYPES, eos_token_id=EOS_ID)
    ref = gguf.GGUFReader(str(path))
    assert ref.fields["tokenizer.ggml.tokens"].contents() == TOKENS
    assert ref.fields["tokenizer.chat_template"].contents() == CHATML_JINJA
    assert ref.fields["tokenizer.ggml.eos_token_id"].contents() == EOS_ID
    assert read_gguf_metadata(path).context_length == 4096
    assert os.path.getsize(path) % 32 == 0


def test_bad_and_truncated_files(tmp_path, make_gguf):
    junk = tmp_path / "junk.gguf"
    junk.write_bytes(b"NOTGGUF" * 10)
    with pytest.raises(GGUFError) as bad:
        read_gguf_metadata(junk)
    assert bad.value.code == "gguf.bad_magic"

    full = make_gguf(tmp_path / "ok.gguf").read_bytes()
    cut = tmp_path / "cut.gguf"
    cut.write_bytes(full[:60])
    with pytest.raises(GGUFError) as truncated:
        read_gguf_metadata(cut)
    assert truncated.value.code == "gguf.truncated"

    old = tmp_path / "v1.gguf"
    old.write_bytes(b"GGUF" + (1).to_bytes(4, "little") + b"\0" * 16)
    with pytest.raises(GGUFError) as version:
        read_gguf_metadata(old)
    assert version.value.code == "gguf.unsupported_version" and version.value.params["version"] == 1

    empty = tmp_path / "empty.gguf"
    empty.write_bytes(b"")
    with pytest.raises(GGUFError):
        read_gguf_metadata(empty)


def test_does_not_read_tensor_data(tmp_path, make_gguf):
    path = make_gguf(tmp_path / "big.gguf", tensor_mb=4)
    assert path.stat().st_size > 4_000_000

    class Counting(io.BufferedReader):
        total = 0

        def read(self, n=-1):
            data = super().read(n)
            Counting.total += len(data)
            return data

    with open(path, "rb", buffering=0) as raw, Counting(raw) as fp:
        meta = parse_gguf(fp, str(path))
    assert Counting.total <= meta.kv_end
    assert meta.kv_end < 10_000
    assert meta.tokens[:2] == ["<unk>", "<|endoftext|>"]
