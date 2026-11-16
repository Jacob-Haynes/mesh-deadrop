"""Talk to the Meshtastic mesh, either through meshbus (default) or a serial port.

On the shared Pi the blufor-tracker bridge owns the radio's serial port, so
tools use **meshbus**: inbound texts arrive as JSON on MQTT ``meshbus/rx`` and
outbound texts are published to ``meshbus/tx`` (127.0.0.1:1883, guest/guest).

``SerialMeshLink`` opens the radio directly. It is for standalone use when no
bridge is running (``--serial``); never run it alongside mesh-bridge.

Both links have the same interface: ``start()``, ``send(text, to=None,
channel=0)``, ``stop()``, ``connected`` and an ``on_text(InboundText)`` callback.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

TOPIC_TX = "meshbus/tx"
TOPIC_RX = "meshbus/rx"
MAX_TEXT_LEN = 200


@dataclass
class InboundText:
    from_id: str
    text: str
    channel: int = 0
    ts: float = 0.0
    short_name: str = ""
    long_name: str = ""

    @property
    def names(self) -> set[str]:
        """Every identifier this sender may be addressed by (lower case)."""
        return {n.lower() for n in (self.from_id, self.short_name, self.long_name) if n}

    @property
    def display(self) -> str:
        return self.short_name or self.long_name or self.from_id


def parse_rx(payload: bytes | str) -> InboundText | None:
    """Parse a meshbus/rx payload; returns None (and logs) if malformed."""
    try:
        msg = json.loads(payload)
        text = msg["text"]
        from_id = msg["from"]
        if not isinstance(text, str) or not isinstance(from_id, str):
            raise TypeError("text/from must be strings")
    except (ValueError, KeyError, TypeError) as e:
        logger.warning("Ignoring malformed meshbus/rx message: %s", e)
        return None
    return InboundText(
        from_id=from_id,
        text=text,
        channel=int(msg.get("channel") or 0),
        ts=float(msg.get("ts") or time.time()),
        short_name=str(msg.get("from_short") or ""),
        long_name=str(msg.get("from_long") or ""),
    )


def build_tx(text: str, to: str | None, channel: int, source: str) -> str:
    if len(text) > MAX_TEXT_LEN:
        text = text[: MAX_TEXT_LEN - 3] + "..."
    return json.dumps({"text": text, "to": to, "channel": channel, "source": source})


class MeshbusLink:
    """meshbus client over MQTT. Reconnects by itself; safe to start with no broker."""

    def __init__(
        self,
        source: str,
        on_text: Callable[[InboundText], None],
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        import paho.mqtt.client as mqtt

        self._source = source
        self._on_text = on_text
        self._host = host or os.environ.get("MQTT_HOST", "127.0.0.1")
        self._port = int(port or os.environ.get("MQTT_PORT", "1883"))
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{source}-{os.getpid()}",
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(
            username or os.environ.get("MQTT_USER", "guest"),
            password or os.environ.get("MQTT_PASS", "guest"),
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_connect_fail = self._on_connect_fail
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._last_fail_log = 0.0

    @property
    def connected(self) -> bool:
        return self._client.is_connected()

    def start(self):
        logger.info("meshbus: connecting to MQTT %s:%d as source=%s", self._host, self._port, self._source)
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()

    def send(self, text: str, to: str | None = None, channel: int = 0) -> bool:
        if not self._client.is_connected():
            logger.warning("meshbus: not connected, dropping reply to %s", to or "^all")
            return False
        self._client.publish(TOPIC_TX, build_tx(text, to, channel, self._source))
        return True

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC_RX)
            logger.info("meshbus: connected, listening on %s", TOPIC_RX)
        else:
            logger.warning("meshbus: MQTT connect failed: %s", reason_code)

    def _on_connect_fail(self, client, userdata):
        now = time.monotonic()
        if now - self._last_fail_log > 60:
            self._last_fail_log = now
            logger.warning("meshbus: MQTT broker %s:%d not reachable (is mesh-bridge/OTS running?), retrying",
                           self._host, self._port)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.warning("meshbus: MQTT disconnected (%s), will retry", reason_code)

    def _on_message(self, client, userdata, msg):
        inbound = parse_rx(msg.payload)
        if inbound is None:
            return
        try:
            self._on_text(inbound)
        except Exception:
            logger.exception("meshbus: handler failed for message from %s", inbound.from_id)


class SerialMeshLink:
    """Direct serial link to a Meshtastic radio (standalone use only)."""

    def __init__(self, on_text: Callable[[InboundText], None], port: str = "/dev/ttyUSB0"):
        self._on_text = on_text
        self._port = port
        self._interface = None

    @property
    def connected(self) -> bool:
        return self._interface is not None

    def start(self):
        threading.Thread(target=self._connect, daemon=True, name="serial-mesh").start()

    def stop(self):
        if self._interface is not None:
            self._interface.close()

    def _connect(self):
        try:
            import meshtastic.serial_interface
            from pubsub import pub

            self._interface = meshtastic.serial_interface.SerialInterface(self._port)
            pub.subscribe(self._on_receive, "meshtastic.receive.text")
            logger.info("Serial mesh link connected on %s (standalone mode)", self._port)
        except Exception:
            logger.exception("Failed to open Meshtastic radio on %s", self._port)

    def _on_receive(self, packet, interface):
        text = (packet.get("decoded") or {}).get("text", "")
        if not text:
            return
        from_id = str(packet.get("fromId") or f"!{packet.get('from', 0):08x}")
        user = ((getattr(interface, "nodes", None) or {}).get(from_id) or {}).get("user") or {}
        inbound = InboundText(
            from_id=from_id,
            text=text,
            channel=int(packet.get("channel", 0) or 0),
            ts=float(packet.get("rxTime") or time.time()),
            short_name=user.get("shortName", ""),
            long_name=user.get("longName", ""),
        )
        try:
            self._on_text(inbound)
        except Exception:
            logger.exception("Handler failed for message from %s", from_id)

    def send(self, text: str, to: str | None = None, channel: int = 0) -> bool:
        if self._interface is None:
            logger.warning("Serial mesh link not connected, dropping reply")
            return False
        if len(text) > MAX_TEXT_LEN:
            text = text[: MAX_TEXT_LEN - 3] + "..."
        try:
            self._interface.sendText(text, destinationId=to or "^all", channelIndex=channel)
            return True
        except Exception:
            logger.exception("Failed to send to %s", to)
            return False


class LoggingMeshLink:
    """No-radio link for --simulate / --no-mesh: logs what would have been sent."""

    connected = False

    def __init__(self, on_text: Callable[[InboundText], None] | None = None):
        self._on_text = on_text

    def start(self):
        pass

    def stop(self):
        pass

    def send(self, text: str, to: str | None = None, channel: int = 0) -> bool:
        logger.info("Mesh reply (not sent, no radio) to=%s: %s", to or "^all", text)
        return True

    def inject(self, inbound: InboundText):
        """Feed a fake inbound text (used by simulators)."""
        if self._on_text:
            self._on_text(inbound)
