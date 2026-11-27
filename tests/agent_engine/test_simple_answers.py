"""
@file tests/agent_engine/test_simple_answers.py
@description The quick path of simple requests: the Critic is skipped for a
triage or fast-worker answer that changed nothing (no tool, or only
read-only ones) on trusted context; AEHUB_CRITIC_SIMPLE=check keeps it.
The whole run with the skip is covered by the onboarding test, which sets
"check" to keep its Critic call.
"""

from __future__ import annotations

import pytest

from app.agent_engine.runtime import _simple_answer


@pytest.fixture(autouse=True)
def default_setting(monkeypatch):
    monkeypatch.delenv("AEHUB_CRITIC_SIMPLE", raising=False)


def test_a_simple_answer_that_changed_nothing_skips_the_critic():
    assert _simple_answer({"worker_role": "triage"})
    assert _simple_answer({"worker_role": "fast_worker", "tools_used": ["search_documents"]})


@pytest.mark.parametrize(
    "context",
    [
        # A tool that writes (memory, the interface language, files...).
        {"worker_role": "triage", "tools_used": ["search_documents", "save_user_preference"]},
        {"worker_role": "triage", "tools_used": ["set_interface_language"]},
        # Not a simple request.
        {"worker_role": "architect"},
        {"worker_role": "research"},
        {},
        # Content from outside (a web page, a document) may carry instructions.
        {"worker_role": "triage", "untrusted_context": True},
    ],
)
def test_everything_else_goes_to_the_critic(context):
    assert not _simple_answer(context)


def test_the_critic_can_be_kept_for_simple_answers_too(monkeypatch):
    monkeypatch.setenv("AEHUB_CRITIC_SIMPLE", "check")
    assert not _simple_answer({"worker_role": "triage"})
