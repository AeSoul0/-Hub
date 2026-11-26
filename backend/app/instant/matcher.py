"""
@file backend/app/instant/matcher.py
@description Recognizes simple commands without a model (V1, ADR-035).

A command is instant only when the whole sentence is one of a few fixed forms
and its object is something the user declared:

    apri / avvia / lancia / open / launch / start  <app from AEHUB_APPS>
    apri la cartella <folder> / open the <folder> folder
    accendi / spegni la luce <light> / turn on / off the <light>
    chiudi a chiave <door> / lock the <door>

After the verb, filler words ("la", "luce della", "the ... light") may be
dropped from either end; what remains must be exactly the name or id of a
declared object. Polite words around the command ("Aurora, per favore",
"please") are ignored. Anything else, an unknown name, or more words ("apri
Spotify e metti la playlist") returns None, and the sentence goes to the
engine as before. So a wrong guess costs nothing: the worst case is the
normal, slower path.

Unlocking a door is never instant: it is HIGH risk and needs the approval
card, which the engine's run provides.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.instant.apps import FOLDERS

MAX_WORDS = 12


@dataclass(frozen=True)
class InstantCommand:
    """A recognized command: the tool to call, its arguments, and how to answer."""

    tool: str
    arguments: Dict[str, object]
    reply: str  # a key of the reply catalog (app.instant.runner)
    name: str  # what the object is called, for the reply
    language: str  # "it" or "en": the reply follows the language spoken


def normalize(text: str) -> str:
    """Lowercase, no accents, no punctuation, single spaces; "l'app" -> "l' app"."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[’`]", "'", text)
    text = re.sub(r"'", "' ", text)
    text = re.sub(r"[^\w'+-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Words that may come before or after the command without changing it.
_LEAD = re.compile(
    r"^(?:(?:ehi|hey|ok|okay|ciao|hi)\s+)?(?:aurora\s+)?"
    r"(?:(?:per favore|perfavore|please|puoi|potresti|can you|could you|would you)\s+)*"
)
_TAIL = re.compile(r"(?:\s+(?:per favore|perfavore|please|grazie|thanks|thank you|subito|now))+$")

_ARTICLES = {"il", "lo", "la", "i", "gli", "le", "l'", "un", "una", "mio", "mia", "miei", "mie", "the", "my", "a"}
_PREPOSITIONS = {"del", "della", "dello", "dei", "degli", "delle", "di", "in", "nel", "nella", "sul", "sulla", "of", "in"}

# Verb phrases: (language, words, kind, on). Longest first within a language.
_VERBS: List[Tuple[str, str, str, Optional[bool]]] = [
    ("it", "chiudi a chiave", "lock", None),
    ("it", "fai partire", "app", None),
    ("it", "apri", "app_or_folder", None),
    ("it", "avvia", "app", None),
    ("it", "lancia", "app", None),
    ("it", "esegui", "app", None),
    ("it", "accendi", "light", True),
    ("it", "spegni", "light", False),
    ("it", "blocca", "lock", None),
    ("en", "turn on", "light", True),
    ("en", "switch on", "light", True),
    ("en", "turn off", "light", False),
    ("en", "switch off", "light", False),
    ("en", "open", "app_or_folder", None),
    ("en", "launch", "app", None),
    ("en", "start", "app", None),
    ("en", "run", "app", None),
    ("en", "lock", "lock", None),
]

# Filler that may stand before or after the object, by kind.
_FILLER = {
    "app": _ARTICLES | {"app", "l' app", "applicazione", "application", "programma", "program"},
    "folder": _ARTICLES | _PREPOSITIONS | {"cartella", "folder"},
    "light": _ARTICLES | _PREPOSITIONS | {"luce", "luci", "lampada", "light", "lights", "lamp"},
    "lock": _ARTICLES | _PREPOSITIONS | {"porta", "door", "serratura", "lock"},
}


def _strip(text: str) -> str:
    text = _LEAD.sub("", text, count=1)
    return _TAIL.sub("", text).strip()


def _names(pairs: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    """Spoken key -> id, from (id, name) pairs: the id and the name both count."""
    names: Dict[str, str] = {}
    for ident, name in pairs:
        for spoken in {ident, ident.replace("_", " ").replace("-", " "), name}:
            if spoken:
                names[normalize(spoken)] = ident
    return names


def _find(words: Sequence[str], kind: str, names: Dict[str, str]) -> Optional[str]:
    """
    The declared object the words name, dropping only filler from either end.
    Tried from the longest span, so "porta di casa" wins over "casa".
    """
    filler = _FILLER[kind]
    count = len(words)
    for length in range(count, 0, -1):
        for start in range(0, count - length + 1):
            skipped = list(words[:start]) + list(words[start + length:])
            if all(word in filler for word in skipped):
                found = names.get(" ".join(words[start:start + length]))
                if found:
                    return found
    return None


def match(
    text: str,
    apps: Iterable[str] = (),
    lights: Iterable[Tuple[str, str]] = (),
    locks: Iterable[Tuple[str, str]] = (),
) -> Optional[InstantCommand]:
    """
    The instant command this sentence is, or None for the engine.

    apps: the names in AEHUB_APPS; lights and locks: (id, name) of the
    declared home devices.
    """
    sentence = _strip(normalize(text))
    words = sentence.split()
    if not words or len(words) > MAX_WORDS:
        return None
    # "apri Spotify e poi...", "open X and Y": more than one thing to do.
    if any(word in {"e", "ed", "poi", "and", "then"} for word in words[1:]):
        return None

    lights, locks = list(lights), list(locks)
    names = {
        "app": _names((name, name) for name in apps),
        "folder": {normalize(name): name for name in FOLDERS},
        "light": _names(lights),
        "lock": _names(locks),
    }
    display = {ident: name or ident for ident, name in lights + locks}

    for language, verb, kind, on in _VERBS:
        verb_words = verb.split()
        rest = words[len(verb_words):]
        # "turn the kitchen light on": the particle comes last.
        if verb.startswith(("turn ", "switch ")) and words[:1] == verb_words[:1] and words[-1:] == verb_words[1:]:
            rest = words[1:-1]
        elif words[:len(verb_words)] != verb_words:
            continue
        if not rest:
            continue

        if kind in ("app", "app_or_folder"):
            app = _find(rest, "app", names["app"])
            if app:
                return InstantCommand("open_app", {"app": app}, "open_app", app, language)
        if kind == "app_or_folder":
            folder = _find(rest, "folder", names["folder"])
            if folder:
                return InstantCommand("open_folder", {"folder": folder}, "open_folder", folder, language)
        if kind == "light":
            light = _find(rest, "light", names["light"])
            if light:
                reply = "light_on" if on else "light_off"
                return InstantCommand("home_set_light", {"device": light, "on": on}, reply, display[light], language)
        if kind == "lock":
            lock = _find(rest, "lock", names["lock"])
            if lock:
                return InstantCommand("home_lock", {"device": lock}, "locked", display[lock], language)
        return None

    return None


__all__ = ["InstantCommand", "match", "normalize"]
