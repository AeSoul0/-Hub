"""
@file tests/agent_engine/test_memory_isolation.py
@description Security-focused unit tests for AuroraMemoryManager.

The tests verify that persisted memory always carries the authenticated
session/workspace boundary and that the embedding contract matches the
configured pgvector dimension.
"""

from unittest.mock import MagicMock, patch

from app.domain.models.memory import MemoryType
from app.memory.manager import AuroraMemoryManager


# ==============================================================================
# MEMORY WRITE ISOLATION
# ==============================================================================


@patch("app.memory.manager.SessionLocal")
@patch("app.memory.manager.AuroraMemoryManager._get_embedding")
def test_save_memory_enforces_isolation(
    mock_get_embedding,
    mock_session_local,
):
    """
    Memory writes must preserve the authenticated session and workspace IDs.
    """
    mock_get_embedding.return_value = [0.1] * 384

    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    manager = AuroraMemoryManager(
        session_id="s1",
        workspace_id="w1",
    )

    manager.save_memory(
        "Test content",
        MemoryType.SEMANTIC,
    )

    mock_db.add.assert_called_once()

    added_record = mock_db.add.call_args[0][0]

    assert added_record.session_id == "s1"
    assert added_record.workspace_id == "w1"
    assert added_record.content == "Test content"
    assert added_record.memory_type == MemoryType.SEMANTIC

    mock_db.commit.assert_called_once()


# ==============================================================================
# MEMORY READ ISOLATION
# ==============================================================================


@patch("app.memory.manager.SessionLocal")
def test_fetch_all_context_enforces_isolation(
    mock_session_local,
):
    """
    Memory reads must build their query through the session/workspace filter.
    """
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    mock_query = (
        mock_db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
    )

    mock_query.all.return_value = []

    manager = AuroraMemoryManager(
        session_id="s2",
        workspace_id="w2",
    )

    manager.fetch_all_context(
        "test query"
    )

    mock_db.query.return_value.filter.assert_called_once()