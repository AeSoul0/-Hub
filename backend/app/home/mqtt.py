"""
@file backend/app/home/mqtt.py
@description Publish one message to the home MQTT broker.

AEHUB_MQTT_URL: mqtt://host:1883 or mqtts://host:8883 (TLS with the system
CA store). AEHUB_MQTT_USERNAME and, from the keyring, AEHUB_MQTT_PASSWORD.
Messages go out with QoS 1: publish() returns once the broker has them.
Tests replace the publisher with set_publisher().
"""

from __future__ import annotations

import os
import ssl
from typing import Callable, Optional
from urllib.parse import urlsplit


PUBLISH_TIMEOUT_SECONDS = 10

Publisher = Callable[[str, str], None]


class MqttNotConfigured(RuntimeError):
    pass


def broker() -> dict:
    url = os.getenv("AEHUB_MQTT_URL", "").strip()

    if not url:
        raise MqttNotConfigured("No MQTT broker: set AEHUB_MQTT_URL (e.g. mqtt://192.168.1.10:1883).")

    parts = urlsplit(url)

    if parts.scheme not in ("mqtt", "mqtts") or not parts.hostname:
        raise MqttNotConfigured("AEHUB_MQTT_URL must look like mqtt://host:1883 or mqtts://host:8883.")

    secure = parts.scheme == "mqtts"
    username = os.getenv("AEHUB_MQTT_USERNAME", "").strip() or None
    password = os.getenv("AEHUB_MQTT_PASSWORD", "") or None

    return {
        "hostname": parts.hostname,
        "port": parts.port or (8883 if secure else 1883),
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


__all__ = ["MqttNotConfigured", "broker", "publish", "set_publisher"]
