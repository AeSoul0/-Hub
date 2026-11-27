"""
@file backend/app/google/api.py
@description Calendar and Gmail calls of the owner's Google account (N4, ADR-046).

Plain REST calls with the access token of app.google.oauth: the primary
calendar's events (list, create), Gmail search, reading one message and
sending one. What comes back from Google (event descriptions, mail) was
written by other people: the tools mark it untrusted, it is data and never
instructions.
"""

from __future__ import annotations

import base64
import html
import re
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

from app.google import oauth

CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_EVENTS = 25
MAX_MESSAGES = 10
MAX_BODY = 8000
MAX_RECIPIENTS = 10
_ADDRESS = re.compile(r"^[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[^@\s,;<>\"]+$")


async def _call(method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
    for attempt in (1, 2):
        token = await oauth.access_token()
        async with oauth.http_client() as client:
            response = await client.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        if response.status_code != 401:
            break
        # An access token Google no longer takes: renew it once.
        oauth.reset_access()
    if response.status_code == 401:
        raise oauth.GoogleNotConnected("Google refused the token: connect again from STRUMENTI.")
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400:
        message = ((body.get("error") or {}) if isinstance(body.get("error"), dict) else {}).get("message")
        raise oauth.GoogleError(f"Google answered {response.status_code}: {message or response.reason_phrase}.")
    return body


def _local(moment: datetime) -> datetime:
    """A time with the offset of this computer when it has none."""
    return moment if moment.tzinfo else moment.astimezone()


def _when(item: Dict[str, Any]) -> str:
    value = item.get("dateTime") or item.get("date") or ""
    try:
        if "T" in value:
            return f"{datetime.fromisoformat(value).astimezone():%Y-%m-%d %H:%M}"
        return f"{date.fromisoformat(value):%Y-%m-%d} (all day)"
    except ValueError:
        return value


# ==============================================================================
# CALENDAR
# ==============================================================================


async def list_events(days: float = 7, query: str = "", now: Optional[datetime] = None) -> List[Dict[str, str]]:
    start = _local(now or datetime.now())
    params = {
        "timeMin": start.isoformat(),
        "timeMax": (start + timedelta(days=days)).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": str(MAX_EVENTS),
    }
    if query.strip():
        params["q"] = query.strip()
    body = await _call("GET", CALENDAR, params=params)
    return [
        {
            "id": str(item.get("id", "")),
            "title": str(item.get("summary") or "(no title)"),
            "start": _when(item.get("start") or {}),
            "end": _when(item.get("end") or {}),
            "location": str(item.get("location") or ""),
            "description": str(item.get("description") or "")[:500],
        }
        for item in body.get("items") or []
    ]


def event_body(title: str, start: str, end: str = "", all_day: bool = False, location: str = "", description: str = "") -> Dict[str, Any]:
    """The event Google receives: a whole day, or a start and an end (an hour by default)."""
    if not title.strip():
        raise ValueError("An event needs a title.")
    body: Dict[str, Any] = {"summary": title.strip()[:300]}
    if location.strip():
        body["location"] = location.strip()[:300]
    if description.strip():
        body["description"] = description.strip()[:2000]
    if all_day:
        first = date.fromisoformat(start[:10])
        last = date.fromisoformat(end[:10]) if end else first
        if last < first:
            raise ValueError("The event ends before it starts.")
        # Google's end date of a whole-day event is the day after the last.
        body["start"] = {"date": first.isoformat()}
        body["end"] = {"date": (last + timedelta(days=1)).isoformat()}
        return body
    begin = _local(datetime.fromisoformat(start))
    finish = _local(datetime.fromisoformat(end)) if end else begin + timedelta(hours=1)
    if finish <= begin:
        raise ValueError("The event ends before it starts.")
    body["start"] = {"dateTime": begin.isoformat()}
    body["end"] = {"dateTime": finish.isoformat()}
    return body


async def create_event(**fields: Any) -> Dict[str, str]:
    created = await _call("POST", CALENDAR, json=event_body(**fields))
    return {
        "id": str(created.get("id", "")),
        "title": str(created.get("summary") or ""),
        "start": _when(created.get("start") or {}),
        "link": str(created.get("htmlLink") or ""),
    }


# ==============================================================================
# GMAIL
# ==============================================================================


def _headers(payload: Dict[str, Any]) -> Dict[str, str]:
    return {str(item.get("name", "")).lower(): str(item.get("value", "")) for item in payload.get("headers") or []}


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _text_of(payload: Dict[str, Any]) -> str:
    """The plain text of a message: its text/plain part, else its HTML without tags."""
    plain: List[str] = []
    rich: List[str] = []

    def walk(part: Dict[str, Any]) -> None:
        mime = str(part.get("mimeType") or "")
        data = (part.get("body") or {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(_decode(data))
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    if plain:
        return "\n".join(plain)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", "\n".join(rich))
    text = re.sub(r"(?s)<br\s*/?>|</p>|</div>", "\n", text)
    return html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))


async def search_mail(query: str, limit: int = MAX_MESSAGES) -> List[Dict[str, str]]:
    listed = await _call("GET", f"{GMAIL}/messages", params={"q": query, "maxResults": str(max(1, min(limit, MAX_MESSAGES)))})
    found: List[Dict[str, str]] = []
    for item in listed.get("messages") or []:
        message = await _call(
            "GET",
            f"{GMAIL}/messages/{item['id']}",
            params=[("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Subject"), ("metadataHeaders", "Date")],
        )
        headers = _headers(message.get("payload") or {})
        found.append(
            {
                "id": str(message.get("id", "")),
                "from": headers.get("from", ""),
                "subject": headers.get("subject", ""),
                "date": headers.get("date", ""),
                "snippet": html.unescape(str(message.get("snippet") or "")),
            }
        )
    return found


async def read_mail(message_id: str) -> Dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", message_id or ""):
        raise ValueError("Not a Gmail message id.")
    message = await _call("GET", f"{GMAIL}/messages/{message_id}", params={"format": "full"})
    payload = message.get("payload") or {}
    headers = _headers(payload)
    text = re.sub(r"\n{3,}", "\n\n", _text_of(payload)).strip()
    return {
        "id": str(message.get("id", "")),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "text": text[:MAX_BODY] + ("…" if len(text) > MAX_BODY else ""),
    }


def recipients(raw: str) -> List[str]:
    addresses = [item.strip() for item in re.split(r"[,;]", raw or "") if item.strip()]
    if not addresses:
        raise ValueError("An email needs at least one recipient.")
    if len(addresses) > MAX_RECIPIENTS:
        raise ValueError(f"At most {MAX_RECIPIENTS} recipients.")
    wrong = [item for item in addresses if not _ADDRESS.match(item)]
    if wrong:
        raise ValueError(f"Not an email address: {', '.join(wrong)}.")
    return addresses


def mime_message(to: str, subject: str, body: str, sender: str = "") -> str:
    message = EmailMessage()
    message["To"] = ", ".join(recipients(to))
    message["Subject"] = " ".join(subject.split())[:300]
    if sender:
        message["From"] = sender
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


async def send_mail(to: str, subject: str, body: str) -> Dict[str, str]:
    sent = await _call("POST", f"{GMAIL}/messages/send", json={"raw": mime_message(to, subject, body)})
    return {"id": str(sent.get("id", "")), "to": ", ".join(recipients(to))}


async def profile() -> str:
    """The address of the connected account."""
    body = await _call("GET", f"{GMAIL}/profile")
    email = str(body.get("emailAddress") or "")
    oauth.remember_account(email)
    return email


__all__ = [
    "create_event",
    "event_body",
    "list_events",
    "mime_message",
    "profile",
    "read_mail",
    "recipients",
    "search_mail",
    "send_mail",
]

