"""
@file backend/app/instant/matcher.py
@description Recognizes simple commands without a model (V1, ADR-035).

A command is instant only when the whole sentence is one of a few fixed forms
and its object is something the user declared:

    apri / avvia / lancia / open / launch / start  <app from AEHUB_APPS>
    apri la cartella <folder> / open the <folder> folder
    accendi / spegni la luce <light> / turn on / off the <light>
    chiudi a chiave <door> / lock the <door>
    alza / abbassa il volume, muto, pausa, canzone successiva... (N4)
    blocca lo schermo, fai uno screenshot (N4)
    timer di 5 minuti, ricordami tra 10 minuti di ..., ricordami alle 18 di ... (N4)

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


# The computer's controls (N4): fixed sentences -> (tool, arguments, reply).
_SYSTEM: Dict[str, Tuple[str, str, Dict[str, object], str]] = {}
for _language, _phrases, _tool, _arguments, _reply in [
    ("it", ["alza il volume", "alza volume", "volume su", "piu volume", "aumenta il volume"], "media_control", {"action": "volume_up"}, "volume_up"),
    ("it", ["abbassa il volume", "abbassa volume", "volume giu", "meno volume", "diminuisci il volume"], "media_control", {"action": "volume_down"}, "volume_down"),
    ("it", ["muto", "silenzia", "togli l' audio", "togli audio", "metti muto", "rimetti l' audio"], "media_control", {"action": "mute"}, "mute"),
    ("it", ["pausa", "metti in pausa", "metti pausa", "riprendi", "riprendi la musica", "fai ripartire la musica", "play"], "media_control", {"action": "play_pause"}, "play_pause"),
    ("it", ["canzone successiva", "prossima canzone", "brano successivo", "prossimo brano", "salta canzone", "salta"], "media_control", {"action": "next"}, "next"),
    ("it", ["canzone precedente", "brano precedente", "torna alla canzone prima"], "media_control", {"action": "previous"}, "previous"),
    ("it", ["blocca lo schermo", "blocca schermo", "blocca il pc", "blocca il computer"], "lock_screen", {}, "screen_locked"),
    ("it", ["fai uno screenshot", "screenshot", "cattura lo schermo", "fai una foto dello schermo"], "take_screenshot", {}, "screenshot"),
    ("en", ["volume up", "turn up the volume", "turn the volume up", "louder"], "media_control", {"action": "volume_up"}, "volume_up"),
    ("en", ["volume down", "turn down the volume", "turn the volume down", "quieter"], "media_control", {"action": "volume_down"}, "volume_down"),
    ("en", ["mute", "unmute"], "media_control", {"action": "mute"}, "mute"),
    ("en", ["pause", "pause the music", "resume", "resume the music"], "media_control", {"action": "play_pause"}, "play_pause"),
    ("en", ["next song", "next track", "skip song", "skip"], "media_control", {"action": "next"}, "next"),
    ("en", ["previous song", "previous track"], "media_control", {"action": "previous"}, "previous"),
    ("en", ["lock the screen", "lock screen", "lock my computer", "lock the computer"], "lock_screen", {}, "screen_locked"),
    ("en", ["take a screenshot", "screenshot"], "take_screenshot", {}, "screenshot"),
]:
    for _phrase in _phrases:
        _SYSTEM.setdefault(_phrase, (_tool, _language, _arguments, _reply))

_NUMBERS = {
    "un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
    "otto": 8, "nove": 9, "dieci": 10, "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
    "quarantacinque": 45, "cinquanta": 50, "sessanta": 60, "mezzo": 0.5, "mezza": 0.5, "mezz'": 0.5, "un'": 1,
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty-five": 45, "fifty": 50, "sixty": 60, "half": 0.5,
}
_UNITS = {
    "secondo": 1 / 60, "secondi": 1 / 60, "second": 1 / 60, "seconds": 1 / 60,
    "minuto": 1, "minuti": 1, "minute": 1, "minutes": 1, "min": 1,
    "ora": 60, "ore": 60, "hour": 60, "hours": 60,
}
_AMOUNT = r"(\d+(?:[.,]\d+)?|" + "|".join(sorted(map(re.escape, _NUMBERS), key=len, reverse=True)) + r")"
_UNIT = r"(" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")"
_TIMER = re.compile(
    r"^(?:(?:metti|imposta|fai partire|avvia|set|start)\s+)?(?:un\s+|a\s+)?timer\s+(?:di\s+|da\s+|for\s+)?"
    + _AMOUNT + r"\s+" + _UNIT + r"$"
)
_REMIND_IN = re.compile(
    r"^(?:ricordami|remind me)\s+(?:tra|fra|in)\s+" + _AMOUNT + r"\s+" + _UNIT + r"\s+(?:di\s+|che\s+|to\s+|that\s+|about\s+)?(.+)$"
)
_REMIND_AT = re.compile(
    r"^(?:ricordami|remind me)\s+(?:alle|all'|at)\s*(\d{1,2})(?:[:. ](\d{2}))?\s+(?:di\s+|che\s+|to\s+|that\s+|about\s+)?(.+)$"
)


def _minutes(amount: str, unit: str) -> float:
    value = float(amount.replace(",", ".")) if amount[0].isdigit() else _NUMBERS[amount]
    return value * _UNITS[unit]


def _system_command(sentence: str, original: str) -> Optional[InstantCommand]:
    """The computer's controls, a timer or a reminder (N4), or None."""
    found = _SYSTEM.get(sentence)
    if found:
        tool, language, arguments, reply = found
        return InstantCommand(tool, dict(arguments), reply, "", language)

    timer = _TIMER.match(sentence)
    if timer:
        minutes = _minutes(timer.group(1), timer.group(2))
        if 0 < minutes <= 7 * 24 * 60:
            language = "en" if re.search(r"\b(?:set|start|for|minutes?|seconds?|hours?)\b", sentence) else "it"
            return InstantCommand("set_timer", {"minutes": minutes}, "timer", f"{timer.group(1)} {timer.group(2)}".replace("' ", "'"), language)

    language = "en" if sentence.startswith("remind me") else "it"
    remind = _REMIND_IN.match(sentence)
    if remind:
        minutes = _minutes(remind.group(1), remind.group(2))
        what = _reminder_text(original, remind.group(3))
        if 0 < minutes <= 7 * 24 * 60 and what:
            return InstantCommand("set_reminder", {"text": what, "minutes": minutes}, "reminder_in", f"{remind.group(1)} {remind.group(2)}".replace("' ", "'"), language)
    remind = _REMIND_AT.match(sentence)
    if remind:
        hour, minute = int(remind.group(1)), int(remind.group(2) or 0)
        what = _reminder_text(original, remind.group(3))
        if hour < 24 and minute < 60 and what:
            at = f"{hour:02d}:{minute:02d}"
            return InstantCommand("set_reminder", {"text": what, "at": at}, "reminder_at", at, language)
    return None


def _reminder_text(original: str, normalized_tail: str) -> str:
    """What to remember, with its own spelling (accents, capitals) when it can be found."""
    words = normalized_tail.split()
    raw = original.strip().rstrip(".!?")
    # The original's last len(words) words, when they match the normalized ones.
    tail = raw.split()[-len(words):] if words else []
    if [normalize(word) for word in tail] == [normalize(word) for word in words] and tail:
        return " ".join(tail)
    return normalized_tail


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
    if not words:
        return None
    # A reminder may be long ("ricordami tra 10 minuti di chiamare Marco e Luca").
    system = _system_command(sentence, text)
    if system is not None:
        return system
    if len(words) > MAX_WORDS:
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
