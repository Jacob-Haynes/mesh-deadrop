"""Parse incoming Meshtastic commands and dispatch responses."""

import logging
import random
import threading
import time

logger = logging.getLogger(__name__)


class DeadDropHandler:
    """Handles DROP/PICKUP/STATUS commands from Meshtastic text messages."""

    def __init__(self, store, interface=None):
        self._store = store
        self._interface = interface

    def set_interface(self, interface):
        self._interface = interface

    def start(self, port: str = "/dev/ttyUSB0"):
        try:
            import meshtastic.serial_interface
            from pubsub import pub

            self._interface = meshtastic.serial_interface.SerialInterface(port)
            pub.subscribe(self._on_receive, "meshtastic.receive.text")
            logger.info("Dead drop handler connected on %s", port)
        except Exception:
            logger.exception("Failed to connect to Meshtastic on %s", port)

    def _on_receive(self, packet, interface):
        decoded = packet.get("decoded", {})
        text = decoded.get("text", "").strip()
        if not text:
            return

        from_id = str(packet.get("fromId", packet.get("from", "unknown")))
        # Use long name or short name if available
        from_node = packet.get("_callsign", from_id)
        self._store.update_node(from_node)

        upper = text.upper()

        if upper.startswith("DROP "):
            self._handle_drop(from_node, from_id, text[5:])
        elif upper == "PICKUP":
            self._handle_pickup(from_node, from_id)
        elif upper == "STATUS":
            self._handle_status(from_node, from_id)

    def _handle_drop(self, sender: str, sender_id: str, rest: str):
        parts = rest.strip().split(" ", 1)
        if len(parts) < 2:
            self._send(sender_id, "ERR usage: DROP <recipient> <message>")
            return

        recipient = parts[0]
        body = parts[1]
        self._store.store_message(sender, recipient, body)
        logger.info("Stored message from %s to %s", sender, recipient)
        self._send(sender_id, "OK 1 messages stored")

    def _handle_pickup(self, callsign: str, sender_id: str):
        messages = self._store.get_messages(callsign)
        if not messages:
            self._send(sender_id, "OK 0 messages waiting")
            return

        for msg in messages:
            text = f"MSG {msg['sender']} {msg['body']}"
            self._send(sender_id, text)
            self._store.mark_delivered(msg["id"])
            time.sleep(1)  # Rate limit for mesh bandwidth

    def _handle_status(self, callsign: str, sender_id: str):
        count = self._store.pending_count(callsign)
        self._send(sender_id, f"OK {count} messages waiting")

    def _send(self, dest_id: str, text: str):
        if self._interface is None:
            logger.info("Response (no interface): %s -> %s", dest_id, text)
            return
        try:
            self._interface.sendText(text, destinationId=dest_id)
        except Exception:
            logger.exception("Failed to send response to %s", dest_id)


class SimulatedHandler(DeadDropHandler):
    """Generates fake drop/pickup activity for testing."""

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

    def __init__(self, store):
        super().__init__(store, interface=None)

    def start(self, port: str = ""):
        threading.Thread(target=self._simulate_loop, daemon=True).start()
        logger.info("Simulation mode — generating fake dead drop activity")

    def _simulate_loop(self):
        # Register all nodes
        for node in self.NODES:
            self._store.update_node(node)

        while True:
            time.sleep(random.uniform(3, 8))

            action = random.choice(["drop", "pickup", "status"])
            sender = random.choice(self.NODES)

            if action == "drop":
                recipient = random.choice([n for n in self.NODES if n != sender])
                body = random.choice(self.MESSAGES)
                self._store.store_message(sender, recipient, body)
                self._store.update_node(sender)
                logger.info("SIM: %s dropped message for %s", sender, recipient)

            elif action == "pickup":
                messages = self._store.get_messages(sender)
                for msg in messages:
                    self._store.mark_delivered(msg["id"])
                self._store.update_node(sender)
                logger.info("SIM: %s picked up %d messages", sender, len(messages))

            else:
                count = self._store.pending_count(sender)
                self._store.update_node(sender)
                logger.info("SIM: %s checked status — %d waiting", sender, count)
