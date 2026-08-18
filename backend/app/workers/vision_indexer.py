"""
@file backend/app/workers/vision_indexer.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import os

from app.core.celery_app import celery_app

# Lazy loaded components
_client = None
_collection = None
_model = None
_preprocess = None
_tokenizer = None
_device = None

def _get_chroma():
    global _client, _collection
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path="workspace/chromadb")
        _collection = _client.get_or_create_collection(name="visual_memory")
    return _collection

def _get_clip():
    global _model, _preprocess, _tokenizer, _device
    if _model is None:
        import open_clip
        import torch
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _model, _, _preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai', device=_device)
        _tokenizer = open_clip.get_tokenizer('ViT-B-32')
    return _model, _preprocess, _tokenizer, _device

def index_image(image_path: str):
    """Computes CLIP embedding and stores it in ChromaDB."""
    try:
        import torch
        from PIL import Image
        collection = _get_chroma()
        model, preprocess, _, device = _get_clip()
        
        image = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
        with torch.no_grad():
            image_features = model.encode_image(image)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            
        collection.add(
            embeddings=image_features.cpu().numpy().tolist(),
            metadatas=[{"path": image_path}],
            ids=[image_path]
        )
        return True
    except Exception as e:
        print(f"Error indexing {image_path}: {e}")
        return False

def search_images(query: str, n_results: int = 5):
    """Searches indexed images using text query via CLIP text embeddings."""
    import torch
    collection = _get_chroma()
    model, _, tokenizer, device = _get_clip()
    
    text = tokenizer([query]).to(device)
    with torch.no_grad():
        text_features = model.encode_text(text)
        text_features /= text_features.norm(dim=-1, keepdim=True)
        
    results = collection.query(
        query_embeddings=text_features.cpu().numpy().tolist(),
        n_results=n_results
    )
    return results

from app.core.celery_app import secure_task

@secure_task(name="vision.index_folder")
def index_folder(session_id: str, folder_path: str):
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                path = os.path.join(root, file)
                index_image(path)
