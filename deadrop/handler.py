"""Parse incoming Meshtastic commands and dispatch responses."""

from __future__ import annotations

import logging
import queue
import random
import threading
import time

from deadrop.mesh_link import InboundText

logger = logging.getLogger(__name__)

# meshbus allows a short burst then ~1 msg / 3 s per tool; pace replies to stay under it
REPLY_INTERVAL = 3.2
MAX_PICKUP = 5  # messages delivered per PICKUP; the rest stay queued for the next one


class DeadDropHandler:
    """Handles DROP/PICKUP/STATUS commands from mesh text messages.

    ``link`` is any mesh link (meshbus, serial or logging) with ``send(text, to)``.
    A recipient can be addressed by node id (``!a1b2c3d4``), short name or long name;
    PICKUP/STATUS match on all three.
    """

    TX_PREFIX = ""  # contract C4.3: "[SIM] " on mesh texts made from simulated activity

    def __init__(self, store, link=None, reply_interval: float = REPLY_INTERVAL):
        self._store = store
        self._link = link
        self._reply_interval = reply_interval
        self._replies: queue.Queue[tuple[str, str]] = queue.Queue()
        self._running = False

    def set_link(self, link):
        self._link = link

    def start(self):
        self._running = True
        threading.Thread(target=self._reply_loop, daemon=True, name="deadrop-replies").start()

    def stop(self):
        self._running = False

    def on_text(self, msg: InboundText):
        text = msg.text.strip()
        if not text:
            return

        sender = msg.display
        self._store.update_node(sender)
        upper = text.upper()

        if upper.startswith("DROP "):
            self._handle_drop(msg, text[5:])
        elif upper == "PICKUP":
            self._handle_pickup(msg)
        elif upper == "STATUS":
            self._handle_status(msg)

    def _handle_drop(self, msg: InboundText, rest: str):
        parts = rest.strip().split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            self._send(msg.from_id, "ERR usage: DROP <recipient> <message>")
            return

        recipient, body = parts[0], parts[1].strip()
        self._store.store_message(msg.display, recipient, body)
        logger.info("Stored message from %s to %s", msg.display, recipient)
        self._send(msg.from_id, f"OK message for {recipient} stored")

    def _handle_pickup(self, msg: InboundText):
        messages = self._store.get_messages_for(msg.names)
        if not messages:
            self._send(msg.from_id, "OK 0 messages waiting")
            return

        for m in messages[:MAX_PICKUP]:
            self._send(msg.from_id, f"MSG {m['sender']} {m['body']}")
            self._store.mark_delivered(m["id"])
        remaining = len(messages) - MAX_PICKUP
        if remaining > 0:
            self._send(msg.from_id, f"OK {remaining} more waiting, send PICKUP again")

    def _handle_status(self, msg: InboundText):
        count = self._store.pending_count_for(msg.names)
        self._send(msg.from_id, f"OK {count} messages waiting")

    def _send(self, dest_id: str, text: str):
        if self.TX_PREFIX and not text.startswith(self.TX_PREFIX):
            text = self.TX_PREFIX + text
        if not self._running:
            self._deliver(dest_id, text)
        else:
            self._replies.put((dest_id, text))

    def _deliver(self, dest_id: str, text: str):
        if self._link is None:
            logger.info("Response (no link): %s -> %s", dest_id, text)
            return
        self._link.send(text, to=dest_id)

    def _reply_loop(self):
        while self._running:
            try:
                dest_id, text = self._replies.get(timeout=1.0)
            except queue.Empty:
                continue
            self._deliver(dest_id, text)
            time.sleep(self._reply_interval)


class SimulatedHandler(DeadDropHandler):
    """Generates fake drop/pickup activity for testing (no radio). Replies start "[SIM] "."""

    TX_PREFIX = "[SIM] "

    NODES = ["Alpha1", "Bravo2", "Charlie3", "Delta4"]
    MESSAGES = [
        "Meet at checkpoint bravo 0600",
        "Intel package ready for pickup",
        "Route clear, proceed north",
        "Resupply at grid 51.150 -1.749",
        "Comms window 2200-2230",
        "Package delivered",
        "Eyes on target, standby",
        "Extraction point confirmed",
    ]

    def start(self):
        super().start()
        threading.Thread(target=self._simulate_loop, daemon=True, name="deadrop-sim").start()
        logger.info("Simulation mode — generating fake dead drop activity")

    def _simulate_loop(self):
        nodes = {name: f"!{abs(hash(name)) & 0xFFFFFFFF:08x}" for name in self.NODES}
        while self._running:
            time.sleep(random.uniform(3, 8))
            sender = random.choice(self.NODES)
            action = random.choice(["drop", "pickup", "status"])
            if action == "drop":
                recipient = random.choice([n for n in self.NODES if n != sender])
                text = f"DROP {recipient} {random.choice(self.MESSAGES)}"
            else:
                text = action.upper()
            logger.info("SIM: %s sends %r", sender, text)
            self.on_text(InboundText(from_id=nodes[sender], text=text, short_name=sender, ts=time.time()))
