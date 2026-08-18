"""
@file backend/app/skills/visual_memory_skill.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.

Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

from typing import Callable, Dict, List

from langchain_core.tools import tool

from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


class VisualMemorySkill(BaseSkill):
    def __init__(self):
        super().__init__()

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="visual_memory",
            description="Allows A.U.R.O.R.A. to semantically search user's photos and files using CLIP embeddings.",
            version="1.0.0"
        )
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        return {
            "search_photos": ToolMetadata(
                name="search_photos",
                description="Searches indexed images by semantic description.",
                risk_level=RiskLevel.LOW
            ),
            "index_folder_for_vision": ToolMetadata(
                name="index_folder_for_vision",
                description="Triggers a background indexing job for a folder.",
                risk_level=RiskLevel.MEDIUM
            )
        }

    @property
    def tools(self) -> List[Callable]:
        return [search_photos, index_folder_for_vision]
        
    @property
    def system_prompt_extension(self) -> str:
        return (
            "You have access to a semantic visual search engine. If the user asks to find a photo "
            "like 'the photo of my dog on the beach', use 'search_photos'. If they want to add a folder "
            "to the search, use 'index_folder_for_vision'."
        )

@tool
def search_photos(query: str) -> str:
    """Searches indexed images by semantic description (e.g. 'a dog on the beach')."""
    try:
        from app.workers.vision_indexer import search_images
        results = search_images(query)
        if not results['ids'] or not results['ids'][0]:
            return "No matching photos found."
        
        matches = [f"Path: {meta['path']}" for meta in results['metadatas'][0]]
        return "Found matching photos:\n" + "\n".join(matches)
    except Exception as e:
        return f"Search Error: {str(e)}"

@tool
def index_folder_for_vision(folder_path: str) -> str:
    """Triggers a background indexing job for a folder to make its images searchable."""
    from app.core.celery_app import celery_app
    celery_app.send_task("vision.index_folder", args=[folder_path])
    return f"Started indexing folder: {folder_path} in the background."

def get_skill():
    return VisualMemorySkill()
