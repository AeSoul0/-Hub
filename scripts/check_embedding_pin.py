"""
@file scripts/check_embedding_pin.py
@description CI check of the pinned embedding model (O1, ADR-039).

The backend downloads the default embedding model from one commit and checks
each file against its SHA-256 (app/memory/embeddings.py, PINNED_MODELS).
This asks the Hugging Face hub whether that commit exists and serves files
with those hashes, so a wrong pin fails here and not on the owner's PC.

    python scripts/check_embedding_pin.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from huggingface_hub import HfApi, hf_hub_download  # noqa: E402

from app.memory.embeddings import PINNED_MODELS  # noqa: E402


def file_sha256(repository: str, filename: str, revision: str, listed: dict) -> str:
    """The hub's own SHA-256 for a large (LFS) file; a small one is downloaded and hashed."""
    lfs = listed.get(filename)
    if lfs is not None:
        return lfs
    path = hf_hub_download(repository, filename, revision=revision)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    failures = []
    for name, source in PINNED_MODELS.items():
        repository, revision = source["repository"], source["revision"]
        try:
            info = HfApi().model_info(repository, revision=revision, files_metadata=True)
        except Exception as exc:  # noqa: BLE001 - an unknown commit: show what main is
            print(f"{name}: {repository}@{revision[:12]} not found ({exc.__class__.__name__})")
            info = HfApi().model_info(repository, files_metadata=True)
            failures.append(f"{name}: commit {revision} not found")
        if info.sha != revision:
            # To pin a new model: the commit and the hashes to write.
            print(f"{name}: {repository} main is {info.sha}")
            failures.append(f"{name}: {repository} resolves {revision} to {info.sha}")
            revision = info.sha
        listed = {
            sibling.rfilename: sibling.lfs.sha256
            for sibling in info.siblings or []
            if getattr(sibling, "lfs", None) is not None
        }
        for filename, expected in source["files"].items():
            actual = file_sha256(repository, filename, revision, listed)
            status = "ok" if actual == expected else f"MISMATCH (hub {actual})"
            print(f"{name}: {repository}@{revision[:12]} {filename} {status}")
            if actual != expected:
                failures.append(f"{name}: {filename}")
    if failures:
        print("Pinned embedding model check failed: " + "; ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
