"""
@file backend/app/instant/approvals.py
@description Approvals by voice or in a word (ADR-037).

When a run waits for the owner, the reply is one short question in the
interface language ("Posso eliminare vecchio.txt? Sì o no."), so a voice
request tells what it waits for without opening the screen.

While an approval is pending, a command that is only a yes or a no ("sì",
"consenti", "vai pure", "no", "annulla", "yes", "go ahead"…, with or without
"Aurora," and "per favore") decides the oldest pending one, the same the
Nucleo shows, through the same path as the button
(app.api.approvals.record_decision). The answer is a few words ("Ricevuto.",
"Ok, procedo.") and the run goes on; its result arrives as when the button
is clicked. Anything longer, or a yes or no with nothing pending, goes to the
engine as before.

Deleting and overwriting (N5): a plain "sì" is not enough for delete_path
and replace_file. The question asks for "sì, elimina" (or "sì,
sovrascrivi"), and only those words, or the same in English, allow it; a
plain yes gets the question again, a no still cancels. Off with
AEHUB_CONFIRM_DELETIONS=off. The buttons of the Nucleo are unchanged.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple

from app.instant.matcher import normalize

logger = logging.getLogger(__name__)

# Whole answers, after normalize() and the polite words around them.
_ALLOW: Dict[str, set] = {
    "it": {
        "si", "si si", "sì", "consenti", "consentito", "consenti pure", "approva", "approvato",
        "procedi", "procedi pure", "vai", "vai pure", "va bene", "fallo", "fai pure", "fallo pure",
        "confermo", "conferma", "certo", "certo che si", "si procedi", "si vai", "si vai pure",
        "si fallo", "si consenti", "si grazie", "d' accordo", "daccordo",
    },
    "en": {
        "yes", "yeah", "yep", "allow", "allow it", "approve", "approved", "go ahead", "go on",
        "do it", "confirm", "proceed", "sure", "yes please", "yes go ahead", "yes do it",
    },
}
_DENY: Dict[str, set] = {
    "it": {
        "no", "no no", "nega", "negato", "non consentire", "annulla", "non farlo", "non lo fare",
        "lascia stare", "lascia perdere", "rifiuta", "no lascia stare", "no annulla", "no grazie",
        "meglio di no", "fermati",
    },
    "en": {
        "no", "nope", "deny", "denied", "cancel", "don' t", "dont", "do not", "don' t do it",
        "do not do it", "no thanks", "leave it", "never mind",
    },
}
_SHARED = {"no", "ok", "okay"}
_ALLOW["it"] |= {"ok", "okay"}
_ALLOW["en"] |= {"ok", "okay"}

_LEAD = ("ehi aurora ", "hey aurora ", "ok aurora ", "aurora ", "ehi ", "hey ", "ok ", "okay ")
_TAIL = (" per favore", " perfavore", " please", " grazie", " thanks", " thank you", " aurora")

REPLIES: Dict[str, Dict[str, List[str]]] = {
    "it": {
        "allow": ["Ricevuto.", "Ok, procedo.", "Va bene, continuo."],
        "deny": ["Ricevuto, annullo.", "Ok, lascio stare.", "Va bene, non lo faccio."],
        "closed": ["È già scaduta."],
        "one_more": [" Ne resta un'altra."],
        "more": [" Ne restano {count}."],
    },
    "en": {
        "allow": ["Got it.", "Okay, going ahead.", "Alright, continuing."],
        "deny": ["Got it, cancelled.", "Okay, leaving it.", "Alright, I won't."],
        "closed": ["It has already expired."],
        "one_more": [" One more is waiting."],
        "more": [" {count} more are waiting."],
    },
}

# The question of a parked run: what the call does, in a few words.
_ACTIONS: Dict[str, Dict[str, str]] = {
    "it": {
        "delete_path": "eliminare {name}",
        "replace_file": "sovrascrivere {name}",
        "write_file": "scrivere {name}",
        "move_path": "spostare {name}",
        "make_folder": "creare la cartella {name}",
        "open_app": "aprire {name}",
        "open_folder": "aprire la cartella {name}",
        "home_unlock": "aprire {name}",
        "execute_shell_script": "eseguire un comando nella sandbox",
        "execute_python_code": "eseguire del codice nella sandbox",
    },
    "en": {
        "delete_path": "delete {name}",
        "replace_file": "overwrite {name}",
        "write_file": "write {name}",
        "move_path": "move {name}",
        "make_folder": "create the folder {name}",
        "open_app": "open {name}",
        "open_folder": "open the {name} folder",
        "home_unlock": "unlock {name}",
        "execute_shell_script": "run a command in the sandbox",
        "execute_python_code": "run code in the sandbox",
    },
}
_QUESTION = {"it": "Posso {action}? Sì o no.", "en": "May I {action}? Yes or no."}

# Deleting and overwriting need their own words (N5).
_STRONG: Dict[str, Dict[str, set]] = {
    "delete_path": {
        "it": {"si elimina", "elimina", "si eliminalo", "eliminalo", "si cancella", "cancella", "si cancellalo", "cancellalo"},
        "en": {"yes delete", "delete", "delete it", "yes delete it"},
    },
    "replace_file": {
        "it": {"si sovrascrivi", "sovrascrivi", "si sovrascrivilo", "sovrascrivilo"},
        "en": {"yes overwrite", "overwrite", "overwrite it", "yes overwrite it"},
    },
}
_CONFIRM_WORDS = {
    "delete_path": {"it": "sì, elimina", "en": "yes, delete"},
    "replace_file": {"it": "sì, sovrascrivi", "en": "yes, overwrite"},
}
_QUESTION_STRONG = {
    "it": "Posso {action}? Per confermare di' «{words}», altrimenti no.",
    "en": "May I {action}? To confirm say \"{words}\", otherwise no.",
}
_ASK_STRONG = {
    "it": "Per questo serve «{words}». Lo confermi?",
    "en": "This one needs \"{words}\". Do you confirm?",
}


def strict_deletions() -> bool:
    from app.core.runtime_config import config_value

    return (config_value("AEHUB_CONFIRM_DELETIONS") or "on").strip().lower() != "off"


def _strong_tool(text: str) -> Optional[Tuple[str, str]]:
    """(tool, language) when the text is the confirmation of a deletion or an overwrite."""
    words = _strip(text).replace(",", "")
    for tool, table in _STRONG.items():
        for language, answers in table.items():
            if words in answers:
                return tool, language
    return None
_WAITING = {"it": "Serve il tuo ok per continuare. Sì o no?", "en": "I need your okay to go on. Yes or no?"}
_GENERIC = {"it": "usare {tool}", "en": "use {tool}"}
_GENERIC_ON = {"it": "usare {tool} su {name}", "en": "use {tool} on {name}"}
_NAME_KEYS = ("path", "source_path", "name", "device", "app", "url", "query")
MAX_NAME = 60


def _strip(text: str) -> str:
    words = normalize(text)
    changed = True
    while changed:
        changed = False
        for lead in _LEAD:
            if words.startswith(lead):
                words, changed = words[len(lead):], True
        for tail in _TAIL:
            if words.endswith(tail):
                words, changed = words[: -len(tail)], True
    return words.strip()


def recognize_decision(text: str, default_language: str = "it") -> Optional[Tuple[str, str]]:
    """("allow" | "deny", language) when the whole text is a yes or a no, else None."""
    words = _strip(text)
    if not words:
        return None
    for decision, table in (("allow", _ALLOW), ("deny", _DENY)):
        languages = [language for language, answers in table.items() if words in answers]
        if languages:
            if words in _SHARED or len(languages) > 1:
                language = default_language if default_language in languages else languages[0]
            else:
                language = languages[0]
            return decision, language
    return None


def _short_name(tool: str, arguments: Dict[str, Any]) -> str:
    value = next((arguments[key] for key in _NAME_KEYS if isinstance(arguments.get(key), str) and arguments[key].strip()), "")
    if not value:
        return ""
    if tool == "home_unlock":
        try:
            from app.home.devices import load_devices

            device = load_devices().get(value)
            value = device.name if device else value
        except Exception:  # noqa: BLE001 - the id is a fine name when the file cannot be read
            pass
    elif "path" in next((key for key in _NAME_KEYS if arguments.get(key) == value), ""):
        # Both separators: a Windows path read on Linux, or the reverse.
        value = PureWindowsPath(value).name or value
    return value if len(value) <= MAX_NAME else value[: MAX_NAME - 1] + "…"


def approval_question(tool: str, arguments: Optional[Dict[str, Any]], language: str) -> str:
    """The one-line question for a call waiting on the owner."""
    language = language if language in _QUESTION else "it"
    name = _short_name(tool, arguments or {})
    template = _ACTIONS[language].get(tool)
    if template and ("{name}" not in template or name):
        action = template.format(name=name)
    else:
        spoken = tool.replace("_", " ")
        action = (_GENERIC_ON if name else _GENERIC)[language].format(tool=spoken, name=name)
    if tool in _CONFIRM_WORDS and strict_deletions():
        return _QUESTION_STRONG[language].format(action=action, words=_CONFIRM_WORDS[tool][language])
    return _QUESTION[language].format(action=action)


def waiting_question(language: str) -> str:
    """The question when the waiting call cannot be read."""
    return _WAITING.get(language, _WAITING["it"])


async def question_for_run(run_id: str, principal: Any, language: str) -> Optional[str]:
    """The question of the approval this run waits on, or None when there is none."""
    from app.agent_engine.approval.manager import ApprovalManager
    from app.api.approvals import _parked_arguments

    pending = await ApprovalManager.list_pending(principal.workspace_id)
    approval = next((item for item in pending if item.get("run_id") == run_id), None)
    if approval is None:
        return None
    approval.setdefault("workspace_id", principal.workspace_id)
    try:
        arguments = _parked_arguments(approval)
    except Exception:  # noqa: BLE001 - the question just names the tool
        arguments = None
    return approval_question(str(approval.get("tool") or ""), arguments, language)


async def try_decision(text: str, principal: Any, default_language: str = "it") -> Optional[Dict[str, Any]]:
    """
    Decide the oldest pending approval when the text is only a yes or a no.
    None when it is not, or when nothing is pending.
    """
    from app.agent_engine.approval.manager import ApprovalClosedError, ApprovalManager
    from app.api.approvals import record_decision

    started = time.perf_counter()
    strong = _strong_tool(text)
    recognized = recognize_decision(text, default_language)
    if recognized is None and strong is None:
        return None
    pending = await ApprovalManager.list_pending(principal.workspace_id)
    if not pending:
        return None

    oldest = pending[0]
    tool = str(oldest.get("tool") or "")
    if strong is not None and strong[0] == tool:
        decision, language = "allow", strong[1]
    elif recognized is None:
        return None  # "elimina" while something else waits: the engine reads it
    else:
        decision, language = recognized
    replies = REPLIES[language]

    # A plain yes does not delete or overwrite: ask for the words again (N5).
    if decision == "allow" and tool in _CONFIRM_WORDS and strict_deletions() and (strong is None or strong[0] != tool):
        return {
            "text": _ASK_STRONG[language].format(words=_CONFIRM_WORDS[tool][language]),
            "decision": None,
            "approval_id": oldest["id"],
            "tool": tool,
            "ms": round((time.perf_counter() - started) * 1000),
        }
    try:
        approval = await record_decision(oldest["id"], decision, principal)
    except ApprovalClosedError:
        approval, reply = None, random.choice(replies["closed"])
    else:
        reply = random.choice(replies[decision]) if approval else random.choice(replies["closed"])

    left = len(pending) - 1
    if left == 1:
        reply += replies["one_more"][0]
    elif left > 1:
        reply += replies["more"][0].format(count=left)

    logger.info("Approval %s decided in a word: %s", oldest["id"], decision)
    return {
        "text": reply,
        "decision": decision if approval else None,
        "approval_id": oldest["id"],
        "tool": str(oldest.get("tool") or ""),
        "ms": round((time.perf_counter() - started) * 1000),
    }


__all__ = ["REPLIES", "approval_question", "question_for_run", "recognize_decision", "try_decision", "waiting_question"]
