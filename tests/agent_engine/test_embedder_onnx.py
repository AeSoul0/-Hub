"""
@file tests/agent_engine/test_embedder_onnx.py
@description O1: the memory's embedder on ONNX Runtime, without torch.

- the model is an ONNX export and its tokenizer, downloaded from the hub
  (faked here: no network in tests) at a pinned commit; the default model's
  files are checked against their SHA-256, another model must name its
  commit;
- the vector is the mean of the token vectors, padding excluded, at unit
  length, as sentence-transformers computes it; texts are cut at 256 tokens;
- the name stays "st:<model>", so stored vectors keep matching;
- a model without an ONNX export says so, and suggests the hash embedder;
- after AEHUB_VOICE_IDLE_MINUTES without use the model leaves memory and
  loads again with the next embedding; SISTEMA lists it while loaded.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List

import numpy
import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

from app.core.runtime_config import replace_stored
from app.memory import embeddings
from app.memory.embeddings import EMBEDDING_DIMENSION, SentenceTransformerEmbedder, get_embedder


class FakeInput:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeSession:
    """last_hidden_state from the token ids: token i is a vector of (id + 1) on component id % 384."""

    opened = 0
    fed: List[Dict[str, Any]] = []

    def __init__(self, path: str, options: Any = None, providers: Any = None) -> None:
        FakeSession.opened += 1
        self.path = path

    def get_inputs(self) -> List[FakeInput]:
        # Like many exports: no token_type_ids input.
        return [FakeInput("input_ids"), FakeInput("attention_mask")]

    def run(self, outputs: Any, feed: Dict[str, Any]) -> List[Any]:
        FakeSession.fed.append(feed)
        ids = feed["input_ids"][0]
        hidden = numpy.zeros((1, len(ids), EMBEDDING_DIMENSION), dtype=numpy.float32)
        for position, token in enumerate(ids):
            hidden[0, position, int(token) % EMBEDDING_DIMENSION] = float(token) + 1.0
        return [hidden]


@pytest.fixture
def hub(tmp_path, monkeypatch):
    """A tokenizer file and a stand-in ONNX session; hf_hub_download serves them."""
    vocab = {"[UNK]": 0, "ciao": 1, "mondo": 2, "gatto": 3}
    vocab.update({f"w{index}": 10 + index for index in range(300)})
    tokenizer = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer_file = tmp_path / "tokenizer.json"
    tokenizer.save(str(tokenizer_file))
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"onnx")

    asked: List[tuple] = []

    def download(repository: str, filename: str, revision: str = "") -> str:
        asked.append((repository, filename, revision))
        if repository.endswith("no-onnx") and filename == embeddings.ONNX_FILE:
            raise FileNotFoundError("404 onnx/model.onnx")
        return str(tokenizer_file if filename == "tokenizer.json" else model_file)

    import huggingface_hub
    import onnxruntime

    # The pinned default, with the hashes of these stand-in files.
    pinned = embeddings.PINNED_MODELS["all-MiniLM-L6-v2"]
    monkeypatch.setitem(
        embeddings.PINNED_MODELS,
        "all-MiniLM-L6-v2",
        {
            **pinned,
            "files": {
                embeddings.ONNX_FILE: hashlib.sha256(model_file.read_bytes()).hexdigest(),
                embeddings.TOKENIZER_FILE: hashlib.sha256(tokenizer_file.read_bytes()).hexdigest(),
            },
        },
    )
    monkeypatch.setattr(embeddings, "_verified", set())
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(onnxruntime, "InferenceSession", FakeSession)
    FakeSession.opened = 0
    FakeSession.fed = []
    replace_stored({})
    yield asked
    replace_stored({})
    embeddings._embedder = None
    embeddings._embedder_key = None


def test_mean_pooling_at_unit_length_and_the_same_name(hub):
    replace_stored({"AEHUB_EMBEDDER": "sentence-transformers"})
    embedder = get_embedder()
    assert embedder.name == "st:all-MiniLM-L6-v2"

    vector = embedder.embed("ciao mondo")

    revision = "751bff37182d3f1213fa05d7196b954e230abad9"
    assert hub == [
        ("Xenova/all-MiniLM-L6-v2", "onnx/model.onnx", revision),
        ("Xenova/all-MiniLM-L6-v2", "tokenizer.json", revision),
    ]
    # Tokens 1 and 2: components 1 and 2 hold 2 and 3, averaged then normalized.
    assert len(vector) == EMBEDDING_DIMENSION
    expected = numpy.zeros(EMBEDDING_DIMENSION)
    expected[1], expected[2] = 2.0 / 2, 3.0 / 2
    expected /= numpy.linalg.norm(expected)
    assert numpy.allclose(vector, expected, atol=1e-6)
    assert math.isclose(sum(component * component for component in vector), 1.0, rel_tol=1e-6)
    # Only the inputs the model declares are fed.
    assert set(FakeSession.fed[-1]) == {"input_ids", "attention_mask"}


def test_long_texts_are_cut_at_256_tokens(hub):
    SentenceTransformerEmbedder("all-MiniLM-L6-v2").embed(" ".join(f"w{index}" for index in range(300)))
    assert FakeSession.fed[-1]["input_ids"].shape == (1, embeddings.MAX_TOKENS)


def test_a_model_without_an_onnx_export_says_so(hub):
    with pytest.raises(RuntimeError, match="AEHUB_EMBEDDER=hash"):
        SentenceTransformerEmbedder("someone/no-onnx@abcdef1").embed("ciao")


def test_downloads_are_pinned_and_checked(hub, tmp_path, monkeypatch):
    # Another model must name its commit.
    with pytest.raises(RuntimeError, match="owner/name@<commit>"):
        SentenceTransformerEmbedder("intfloat/e5-small-v2").embed("ciao")
    assert embeddings.model_source("intfloat/e5-small-v2@0123abc") == {
        "repository": "intfloat/e5-small-v2",
        "revision": "0123abc",
        "files": {},
    }
    SentenceTransformerEmbedder("intfloat/e5-small-v2@0123abc").embed("ciao")
    assert hub[-1] == ("intfloat/e5-small-v2", "tokenizer.json", "0123abc")

    # A default file that does not match its hash is not used.
    pinned = embeddings.PINNED_MODELS["all-MiniLM-L6-v2"]
    monkeypatch.setitem(
        embeddings.PINNED_MODELS, "all-MiniLM-L6-v2", {**pinned, "files": {embeddings.ONNX_FILE: "0" * 64}}
    )
    opened = FakeSession.opened
    with pytest.raises(RuntimeError, match="expected 0000"):
        SentenceTransformerEmbedder("all-MiniLM-L6-v2").embed("ciao")
    assert FakeSession.opened == opened


def test_the_model_leaves_memory_when_idle(hub):
    replace_stored({"AEHUB_EMBEDDER": "sentence-transformers", "AEHUB_VOICE_IDLE_MINUTES": "1"})
    embedder = get_embedder()
    assert embeddings.loaded_embedder() is None

    embedder.embed("gatto")
    listed = embeddings.loaded_embedder(now=embedder.last_used + 30)
    assert listed == {"kind": "embedder", "config": ["all-MiniLM-L6-v2"], "idle_seconds": 30.0}

    assert embeddings.release_idle_embedder(now=embedder.last_used + 30) is False
    assert embeddings.release_idle_embedder(now=embedder.last_used + 61) is True
    assert embedder.loaded is False and embeddings.loaded_embedder() is None

    embedder.embed("gatto")
    assert FakeSession.opened == 2

    # 0 keeps it loaded.
    replace_stored({"AEHUB_EMBEDDER": "sentence-transformers", "AEHUB_VOICE_IDLE_MINUTES": "0"})
    assert embeddings.release_idle_embedder(now=embedder.last_used + 10_000) is False
