"""
@file backend/app/workers/vision_indexer.py
@description Workspace-scoped visual memory indexing and retrieval.

This module computes CLIP embeddings, stores image metadata in ChromaDB,
and enforces workspace isolation for both indexing and semantic retrieval.
Background indexing always runs under a validated authenticated session.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from app.core.celery_app import celery_app, secure_task
from app.core.db import SessionLocal
from app.domain.models.identity import Session as SessionModel


# ==============================================================================
# LAZY MODEL STATE
# ==============================================================================

_chroma_client: Optional[Any] = None
_collection: Optional[Any] = None

_clip_model: Optional[Any] = None
_preprocess: Optional[Any] = None
_tokenizer: Optional[Any] = None
_device: Optional[str] = None


# ==============================================================================
# CHROMADB
# ==============================================================================


def _get_chroma() -> Any:
    """
    Return the shared visual-memory Chroma collection.

    Workspace isolation is enforced through per-record metadata filters rather
    than separate databases, which keeps the storage layer simple while still
    preventing cross-workspace retrieval.
    """
    global _chroma_client
    global _collection

    if _collection is None:
        import chromadb

        _chroma_client = chromadb.PersistentClient(
            path="workspace/chromadb"
        )

        _collection = _chroma_client.get_or_create_collection(
            name="visual_memory"
        )

    return _collection


# ==============================================================================
# CLIP MODEL
# ==============================================================================


def _get_clip() -> tuple[Any, Any, Any, str]:
    """
    Lazily initialize the CLIP model and preprocessing pipeline.
    """
    global _clip_model
    global _preprocess
    global _tokenizer
    global _device

    if _clip_model is None:
        import open_clip
        import torch

        _device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        (
            _clip_model,
            _preprocess,
            _,
        ) = open_clip.create_model_and_transforms(
            "ViT-B-32",
            pretrained="openai",
            device=_device,
        )

        _tokenizer = open_clip.get_tokenizer(
            "ViT-B-32"
        )

    return (
        _clip_model,
        _preprocess,
        _tokenizer,
        _device,
    )


# ==============================================================================
# IMAGE INDEXING
# ==============================================================================


def index_image(
    image_path: str,
    workspace_id: str,
) -> bool:
    """
    Compute an image embedding and store it with workspace ownership metadata.
    """
    if not workspace_id:
        raise ValueError(
            "workspace_id is required for visual indexing."
        )

    if not os.path.isfile(image_path):
        return False

    try:
        import torch
        from PIL import Image

        collection = _get_chroma()

        (
            model,
            preprocess,
            _,
            device,
        ) = _get_clip()

        image = Image.open(
            image_path
        ).convert("RGB")

        tensor = (
            preprocess(image)
            .unsqueeze(0)
            .to(device)
        )

        with torch.no_grad():
            image_features = model.encode_image(
                tensor
            )

            image_features /= image_features.norm(
                dim=-1,
                keepdim=True,
            )

        collection.add(
            embeddings=image_features.cpu()
            .numpy()
            .tolist(),
            metadatas=[
                {
                    "path": image_path,
                    "workspace_id": workspace_id,
                }
            ],
            ids=[
                f"{workspace_id}:{image_path}"
            ],
        )

        return True

    except Exception as exc:
        print(
            f"[VisualMemory] Failed to index "
            f"{image_path}: {exc}"
        )
        return False


# ==============================================================================
# IMAGE SEARCH
# ==============================================================================


def search_images(
    query: str,
    workspace_id: str,
    n_results: int = 5,
) -> Dict[str, Any]:
    """
    Search indexed images while enforcing workspace isolation.
    """
    if not query.strip():
        raise ValueError(
            "Visual search query cannot be empty."
        )

    if not workspace_id:
        raise ValueError(
            "workspace_id is required for visual search."
        )

    if n_results <= 0:
        raise ValueError(
            "n_results must be greater than zero."
        )

    import torch

    collection = _get_chroma()

    (
        model,
        _,
        tokenizer,
        device,
    ) = _get_clip()

    text = tokenizer(
        [query]
    ).to(device)

    with torch.no_grad():
        text_features = model.encode_text(
            text
        )

        text_features /= text_features.norm(
            dim=-1,
            keepdim=True,
        )

    return collection.query(
        query_embeddings=text_features.cpu()
        .numpy()
        .tolist(),
        n_results=n_results,
        where={
            "workspace_id": workspace_id,
        },
    )


# ==============================================================================
# DURABLE BACKGROUND INDEXING
# ==============================================================================


@secure_task(
    name="vision.index_folder"
)
def index_folder(
    session_id: str,
    folder_path: str,
) -> Dict[str, int]:
    """
    Index a workspace folder using the authenticated session context.

    The workspace is resolved from the persisted session rather than being
    accepted as an untrusted Celery argument.
    """
    if not folder_path:
        raise ValueError(
            "folder_path is required."
        )

    with SessionLocal() as db:
        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.id == session_id
            )
            .first()
        )

        if session is None:
            raise PermissionError(
                "Authenticated session could not be resolved."
            )

        workspace_id = session.workspace_id

    if not workspace_id:
        raise PermissionError(
            "Authenticated session has no workspace."
        )

    if not os.path.isdir(folder_path):
        raise FileNotFoundError(
            f"Indexing folder does not exist: {folder_path}"
        )

    indexed = 0
    failed = 0

    for root, _, files in os.walk(folder_path):
        for filename in files:
            if not filename.lower().endswith(
                (
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                )
            ):
                continue

            path = os.path.join(
                root,
                filename,
            )

            if index_image(
                path,
                workspace_id,
            ):
                indexed += 1
            else:
                failed += 1

    return {
        "indexed": indexed,
        "failed": failed,
    }