"""
@file backend/app/voice/wake.py
@description The wake word (N2, ADR-041): the openWakeWord models the Nucleo
listens with.

The word is recognized in the browser (onnxruntime-web): the microphone
audio never leaves the page until the word is heard, not even towards this
backend. The backend only hands out the models:

- the two shared models that turn audio into features (melspectrogram and
  speech embedding) and one model per ready-made word (hey_jarvis, alexa,
  hey_mycroft), downloaded once from the openWakeWord release v0.5.1 and
  checked against their SHA-256 before they are used or served;
- "aurora": a model of your own (an openWakeWord .onnx, for example trained
  with its notebook), put in <AEHUB_VOICE_MODELS_DIR>/wake/aurora.onnx.

Settings: AEHUB_WAKE_WORD (off by default) and AEHUB_WAKE_SENSITIVITY.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"

# file name in the release -> SHA-256
PINNED: Dict[str, Dict[str, str]] = {
    "melspectrogram": {
        "file": "melspectrogram.onnx",
        "sha256": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    },
    "embedding_model": {
        "file": "embedding_model.onnx",
        "sha256": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
    },
    "hey_jarvis": {
        "file": "hey_jarvis_v0.1.onnx",
        "sha256": "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
    },
    "alexa": {
        "file": "alexa_v0.1.onnx",
        "sha256": "6ff566a01d12670e8d9e3c59da32651db1575d17272a601b7f8a39283dfbae3e",
    },
    "hey_mycroft": {
        "file": "hey_mycroft_v0.1.onnx",
        "sha256": "c2a311e8fa1338de89c31b3b46dc4dffd4af2f9a8d6ddead48893c2d301b1f18",
    },
}

WORDS = ("hey_jarvis", "alexa", "hey_mycroft", "aurora")
LABELS = {"hey_jarvis": "Hey Jarvis", "alexa": "Alexa", "hey_mycroft": "Hey Mycroft", "aurora": "Aurora"}
OWN_MODEL = "aurora.onnx"

# Score the word model must reach (0..1): lower hears the word more easily,
# and other words by mistake more often.
THRESHOLDS = {"low": 0.7, "medium": 0.5, "high": 0.35}

# The models are about 1 MB each; anything much larger is not one of them.
MAX_MODEL_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60.0

_lock = threading.Lock()


class WakeModelUnavailable(RuntimeError):
    """The model cannot be handed out; the message says why."""


def wake_dir() -> Path:
    from app.voice.engines import models_dir

    folder = models_dir() / "wake"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def wake_word() -> str:
    """The chosen word, or "off"."""
    from app.core.runtime_config import config_value

    word = (config_value("AEHUB_WAKE_WORD", "off") or "off").strip().lower()
    return word if word in WORDS else "off"


def wake_threshold() -> float:
    from app.core.runtime_config import config_value

    sensitivity = (config_value("AEHUB_WAKE_SENSITIVITY", "medium") or "medium").strip().lower()
    return THRESHOLDS.get(sensitivity, THRESHOLDS["medium"])


def own_model_path() -> Path:
    return wake_dir() / OWN_MODEL


def wake_state() -> Dict[str, object]:
    """What the Nucleo needs to listen (part of GET /api/interface)."""
    word = wake_word()
    return {
        "word": word,
        "label": LABELS.get(word, ""),
        "threshold": wake_threshold(),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch(url: str) -> bytes:
    import httpx

    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as response:
        if response.status_code != 200:
            raise WakeModelUnavailable(f"Download of {url} failed: HTTP {response.status_code}.")
        data = bytearray()
        for block in response.iter_bytes():
            data.extend(block)
            if len(data) > MAX_MODEL_BYTES:
                raise WakeModelUnavailable(f"Download of {url} stopped: larger than a wake model.")
    return bytes(data)


def model_path(name: str) -> Path:
    """
    The file of one model, downloaded and checked first if needed.
    `name` is one of PINNED or "aurora".
    """
    if name == "aurora":
        path = own_model_path()
        if not path.is_file():
            raise WakeModelUnavailable(
                f"The Aurora model is not there: put your openWakeWord model in {path}, "
                "or choose a ready-made word."
            )
        if path.stat().st_size > MAX_MODEL_BYTES:
            raise WakeModelUnavailable(f"{path} is too large to be a wake word model.")
        return path

    pinned = PINNED.get(name)
    if pinned is None:
        raise KeyError(name)

    path = wake_dir() / pinned["file"]
    with _lock:
        if path.is_file() and _sha256(path) == pinned["sha256"]:
            return path

        data = _fetch(f"{RELEASE}/{pinned['file']}")
        actual = hashlib.sha256(data).hexdigest()
        if actual != pinned["sha256"]:
            raise WakeModelUnavailable(
                f"Wake model {pinned['file']} has SHA-256 {actual}, expected {pinned['sha256']}. "
                "The file was not used."
            )
        partial = path.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(path)
        logger.info("Wake model %s downloaded.", pinned["file"])
        return path


def downloaded() -> Dict[str, bool]:
    """Which models are on disk (not checked again here)."""
    folder = wake_dir()
    present = {name: (folder / pinned["file"]).is_file() for name, pinned in PINNED.items()}
    present["aurora"] = own_model_path().is_file()
    return present


def missing_own_model() -> Optional[str]:
    """The path the Aurora model should be at, when it is chosen and missing."""
    if wake_word() == "aurora" and not own_model_path().is_file():
        return str(own_model_path())
    return None


__all__ = [
    "LABELS",
    "PINNED",
    "THRESHOLDS",
    "WORDS",
    "WakeModelUnavailable",
    "downloaded",
    "missing_own_model",
    "model_path",
    "wake_state",
    "wake_threshold",
    "wake_word",
]
