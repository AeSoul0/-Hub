"""
@file tests/unit/test_database_legacy.py
@description Unit tests for the compatibility PostgreSQL persistence facade.

These tests verify SQL contracts without creating a live PostgreSQL
connection. The primary regression covered here is the mismatch between the
chat schema and the SQL used by save_chat/get_recent_chat.
"""

from unittest.mock import MagicMock, patch

from app.core import database


def _mock_connection():
    """
    Create a mocked psycopg2 connection context.
    """
    connection = MagicMock()
    cursor = connection.cursor.return_value

    context = MagicMock()
    context.__enter__.return_value = connection
    context.__exit__.return_value = False

    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    return context, connection


def test_save_chat_uses_schema_column_names() -> None:
    """
    save_chat must write the actual chats table columns.
    """
    context, connection = _mock_connection()

    with patch(
        "app.core.database.get_connection",
        return_value=context,
    ):
        with patch(
            "app.core.celery_app.celery_app.send_task"
        ):
            database.save_chat(
                "session-1",
                "hello",
                "world",
            )

    cursor = connection.cursor.return_value
    execute_calls = cursor.execute.call_args_list

    assert execute_calls

    query = execute_calls[0].args[0]

    assert "user_message" in query
    assert "bot_response" in query
    assert "user_text" not in query
    assert "ai_text" not in query


def test_get_recent_chat_uses_schema_column_names() -> None:
    """
    get_recent_chat must read the same columns created by init_db.
    """
    context, connection = _mock_connection()

    connection.cursor.return_value.fetchall.return_value = [
        ("hello", "world"),
    ]

    with patch(
        "app.core.database.get_connection",
        return_value=context,
    ):
        result = database.get_recent_chat(
            "session-1",
            limit=5,
        )

    cursor = connection.cursor.return_value
    execute_calls = cursor.execute.call_args_list

    assert execute_calls

    query = execute_calls[0].args[0]

    assert "user_message" in query
    assert "bot_response" in query

    assert result == [
        {
            "role": "user",
            "content": "hello",
        },
        {
            "role": "assistant",
            "content": "world",
        },
    ]


def test_get_recent_chat_rejects_invalid_session() -> None:
    """
    Session-less history access must fail closed.
    """
    try:
        database.get_recent_chat("")
    except ValueError as exc:
        assert str(exc) == "session_id is required"
    else:
        raise AssertionError(
            "Expected ValueError for an empty session_id"
        )


def test_clear_chat_rejects_invalid_session() -> None:
    """
    Session-less deletion must fail closed.
    """
    try:
        database.clear_chat("")
    except ValueError as exc:
        assert str(exc) == "session_id is required"
    else:
        raise AssertionError(
            "Expected ValueError for an empty session_id"
        )