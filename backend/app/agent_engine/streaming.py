"""
@file backend/app/agent_engine/streaming.py
@description The draft of an answer while the model writes it (N1, ADR-040).

The orchestrator opens a DraftStream for a command asked from the Nucleo
(`streaming_answer`). While it is open, the model adapter streams the reply
and hands every piece of text to it; the stream publishes the text so far as
`answer.delta` on the workspace channel, at most every DRAFT_INTERVAL
seconds, and `answer.reset` when the text was not the answer after all (the
model went on with a tool call, or the Critic sent it back).

It is only a draft: the answer the Nucleo keeps, and the one that is spoken,
is the one the Critic accepted and the output guardrail checked, in the
reply of the request. Subagents never write into the draft.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# Seconds between two drafts on the wire: a few words each, smooth to read.
DRAFT_INTERVAL = 0.08
# Longer drafts are cut: the Nucleo shows the start, the final answer the rest.
MAX_DRAFT_CHARS = 20_000

_current: ContextVar[Optional["DraftStream"]] = ContextVar("aehub_answer_draft", default=None)


class DraftStream:
    """The text the model has written so far for one command, published as a draft."""

    def __init__(self, session_id: str, workspace_id: str, command_id: str = "") -> None:
        self.session_id = session_id
        self.workspace_id = workspace_id
        # The Nucleo's id of the command, so drafts of commands running
        # together go to the right one.
        self.command_id = command_id
        self.text = ""
        self.published = ""
        self._last = 0.0

    async def _publish(self, event_type: str, data: dict) -> None:
        from app.core.event_bus import event_bus

        if self.command_id:
            data = {**data, "command_id": self.command_id}
        try:
            await event_bus.publish(self.session_id, event_type, data, workspace_id=self.workspace_id)
        except Exception as exc:  # noqa: BLE001 - a lost draft costs nothing: the answer still arrives
            logger.debug("Draft not delivered: %s", exc)

    async def delta(self, piece: str) -> None:
        """More text from the model; published when enough time has passed."""
        if not piece or len(self.text) >= MAX_DRAFT_CHARS:
            return
        self.text = (self.text + piece)[:MAX_DRAFT_CHARS]
        now = time.monotonic()
        if now - self._last >= DRAFT_INTERVAL:
            await self.flush()

    async def flush(self) -> None:
        """Publish what is not on the wire yet."""
        if self.text and self.text != self.published:
            self._last = time.monotonic()
            self.published = self.text
            await self._publish("answer.delta", {"text": self.text})

    async def reset(self) -> None:
        """The text so far was not the answer: the Nucleo clears the draft."""
        had_text = bool(self.text or self.published)
        self.text = ""
        self.published = ""
        if had_text:
            await self._publish("answer.reset", {})


def current_draft() -> Optional[DraftStream]:
    """The draft of the command being answered in this task, if any."""
    return _current.get()


@contextmanager
def streaming_answer(draft: Optional[DraftStream]) -> Iterator[Optional[DraftStream]]:
    """Answer with this draft open (None closes it, as for a subagent)."""
    token = _current.set(draft)
    try:
        yield draft
    finally:
        _current.reset(token)


__all__ = ["DRAFT_INTERVAL", "DraftStream", "current_draft", "streaming_answer"]
