"""
@file tests/agent_engine/test_embedder_onnx.py
@description O1: the memory's embedder on ONNX Runtime, without torch.

- the model is the sentence-transformers repository's ONNX export and its
  tokenizer, downloaded from the hub (faked here: no network in tests);
- the vector is the mean of the token vectors, padding excluded, at unit
  length, as sentence-transformers computes it; texts are cut at 256 tokens;
- the name stays "st:<model>", so stored vectors keep matching;
- a model without an ONNX export says so, and suggests the hash embedder;
- after AEHUB_VOICE_IDLE_MINUTES without use the model leaves memory and
  loads again with the next embedding; SISTEMA lists it while loaded.
"""

from __future__ import annotations

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

    def download(repository: str, filename: str) -> str:
        asked.append((repository, filename))
        if repository.endswith("no-onnx") and filename == embeddings.ONNX_FILE:
            raise FileNotFoundError("404 onnx/model.onnx")
        return str(tokenizer_file if filename == "tokenizer.json" else model_file)

    import huggingface_hub
    import onnxruntime

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

    assert hub == [
        ("sentence-transformers/all-MiniLM-L6-v2", "onnx/model.onnx"),
        ("sentence-transformers/all-MiniLM-L6-v2", "tokenizer.json"),
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
        SentenceTransformerEmbedder("someone/no-onnx").embed("ciao")


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
