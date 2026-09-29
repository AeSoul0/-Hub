"""
@file backend/app/skills/visual_memory_skill.py
@description Core module for A.U.R.O.R.A. System - Visual Memory Skill

Implements core logic and architectural definitions.
"""

from typing import Callable, Dict, List

from langchain_core.tools import tool

from app.skills.base import BaseSkill, RiskLevel, SkillMetadata, ToolMetadata


class VisualMemorySkill(BaseSkill):
    def __init__(self):
        super().__init__()

    @property
    def metadata(self) -> SkillMetadata:
        # Define the skill metadata
        return SkillMetadata(
            name="visual_memory",
            description="Allows A.U.R.O.R.A. to semantically search user's photos and files using CLIP embeddings.",
            version="1.0.0"
        )
        
    def get_tool_metadata(self) -> Dict[str, ToolMetadata]:
        # Return specific metadata and risk levels for memory tools
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
        # Expose the search and indexing tools
        return [search_photos, index_folder_for_vision]
        
    @property
    def system_prompt_extension(self) -> str:
        # Inform the agent how to utilize the visual search engine
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
        # Perform the actual embedding search
        results = search_images(query)
        if not results['ids'] or not results['ids'][0]:
            return "No matching photos found."
        
        # Extract and compile the matching file paths
        matches = [f"Path: {meta['path']}" for meta in results['metadatas'][0]]
        return "Found matching photos:\n" + "\n".join(matches)
    except Exception as e:
        return f"Search Error: {str(e)}"

@tool
def index_folder_for_vision(folder_path: str) -> str:
    """Triggers a background indexing job for a folder to make its images searchable."""
    from app.core.celery_app import celery_app
    from app.skills.memory_skill import current_session_id
    
    # Retrieve current user session context
    session_id = current_session_id.get("default-session")
    # Dispatch an asynchronous task to index images without blocking
    celery_app.send_task("vision.index_folder", args=[session_id, folder_path])
    return f"Started secure indexing folder: {folder_path} in the background."

def get_skill():
    # Factory function to instantiate the skill
    return VisualMemorySkill()
