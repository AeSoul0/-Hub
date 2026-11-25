"""
@file backend/app/home/mqtt.py
@description Talk to the home MQTT broker.

AEHUB_MQTT_URL: mqtt://host:1883 or mqtts://host:8883 (TLS with the system
CA store). AEHUB_MQTT_USERNAME and, from the keyring, AEHUB_MQTT_PASSWORD.
The URL and the user are settings (F7): read on every message, so a change
from the Control Plane applies without a restart.

- publish(): one command, QoS 1; returns once the broker has it.
- request_state(): ask a device its state and wait for the answer (F7).
- check_broker(): connect once, to test the settings (F7).

Tests replace the publisher with set_publisher(), and monkeypatch the other
two.
"""

from __future__ import annotations

import os
import ssl
import threading
from typing import Any, Callable, List, Optional
from urllib.parse import urlsplit

from app.core.runtime_config import config_value


PUBLISH_TIMEOUT_SECONDS = 10
STATE_TIMEOUT_SECONDS = 3.0

Publisher = Callable[[str, str], None]


class MqttNotConfigured(RuntimeError):
    pass


class MqttError(RuntimeError):
    pass


def broker() -> dict:
    url = (config_value("AEHUB_MQTT_URL", "") or "").strip()

    if not url:
        raise MqttNotConfigured("No MQTT broker: set AEHUB_MQTT_URL (e.g. mqtt://192.168.1.10:1883).")

    parts = urlsplit(url)

    try:
        port = parts.port
    except ValueError:
        port = -1

    if parts.scheme not in ("mqtt", "mqtts") or not parts.hostname or port == -1:
        raise MqttNotConfigured("AEHUB_MQTT_URL must look like mqtt://host:1883 or mqtts://host:8883.")

    secure = parts.scheme == "mqtts"
    username = (config_value("AEHUB_MQTT_USERNAME", "") or "").strip() or None
    password = os.getenv("AEHUB_MQTT_PASSWORD", "") or None

    return {
        "hostname": parts.hostname,
        "port": port or (8883 if secure else 1883),
        "auth": {"username": username, "password": password} if username else None,
        # paho takes an SSLContext as is (tls_set_context).
        "tls": ssl.create_default_context() if secure else None,
    }


def _paho_publish(topic: str, payload: str) -> None:
    from paho.mqtt import publish

    settings = broker()
    publish.single(
        topic,
        payload=payload,
        qos=1,
        hostname=settings["hostname"],
        port=settings["port"],
        auth=settings["auth"],
        tls=settings["tls"],
        client_id="",
        keepalive=PUBLISH_TIMEOUT_SECONDS,
    )


_publisher: Optional[Publisher] = None


def set_publisher(publisher: Optional[Publisher]) -> None:
    global _publisher
    _publisher = publisher


def publish(topic: str, payload: str) -> None:
    (_publisher or _paho_publish)(topic, payload)


def _client(settings: dict) -> Any:
    from paho.mqtt import client as paho

    client = paho.Client(paho.CallbackAPIVersion.VERSION2)

    if settings["auth"]:
        client.username_pw_set(settings["auth"]["username"], settings["auth"]["password"])
    if settings["tls"]:
        client.tls_set_context(settings["tls"])

    return client


def _session(on_ready: Callable[[Any, threading.Event], None], timeout: float) -> List[str]:
    """
    Connect and call on_ready(client, done) once the broker accepts us; the
    session ends when `done` is set, at the first message of a subscription,
    or at the timeout. Returns the messages received. Raises MqttError when
    the broker refuses, cannot be reached or does not answer.
    """
    settings = broker()
    client = _client(settings)
    done = threading.Event()
    messages: List[str] = []
    connected: List[bool] = []
    refused: List[str] = []

    def on_connect(client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code.is_failure:
            refused.append(str(reason_code))
            done.set()
            return
        connected.append(True)
        on_ready(client, done)

    def on_message(client: Any, userdata: Any, message: Any) -> None:
        messages.append(message.payload.decode("utf-8", "replace"))
        done.set()

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(settings["hostname"], settings["port"], keepalive=PUBLISH_TIMEOUT_SECONDS)
    except (OSError, ValueError) as exc:
        raise MqttError(f"Broker unreachable: {exc}") from exc

    client.loop_start()

    try:
        done.wait(timeout)
    finally:
        client.disconnect()
        client.loop_stop()

    if refused:
        raise MqttError(f"The broker refused the connection: {refused[0]}.")
    if not connected:
        raise MqttError("The broker did not answer in time.")

    return messages


def check_broker(timeout: float = STATE_TIMEOUT_SECONDS) -> None:
    """
    Connect once with the current settings. Raises MqttNotConfigured or
    MqttError with the reason.
    """
    _session(lambda client, done: done.set(), timeout)


def request_state(watch: str, ask: str, payload: str, timeout: float = STATE_TIMEOUT_SECONDS) -> Optional[str]:
    """
    Subscribe to `watch`, publish `payload` on `ask`, and return the first
    message on `watch` (a retained state counts), or None after the timeout.
    """

    def ready(client: Any, done: threading.Event) -> None:
        client.subscribe(watch, qos=1)
        client.publish(ask, payload, qos=1)

    messages = _session(ready, timeout)
    return messages[0] if messages else None


__all__ = [
    "MqttError",
    "MqttNotConfigured",
    "broker",
    "check_broker",
    "publish",
    "request_state",
    "set_publisher",
]
