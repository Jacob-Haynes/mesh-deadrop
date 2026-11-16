import json

import pytest

from deadrop.handler import MAX_PICKUP, DeadDropHandler
from deadrop.mesh_link import InboundText, build_tx, parse_rx
from deadrop.store import MessageStore


class FakeLink:
    def __init__(self):
        self.sent = []

    def send(self, text, to=None, channel=0):
        self.sent.append((to, text))
        return True


@pytest.fixture
def setup(tmp_path):
    store = MessageStore(db_path=str(tmp_path / "db" / "messages.db"))
    link = FakeLink()
    handler = DeadDropHandler(store, link)  # not started: replies are sent synchronously
    return store, link, handler


def alpha(text):
    return InboundText(from_id="!a1a1a1a1", text=text, short_name="A1", long_name="Alpha 1")


def bravo(text):
    return InboundText(from_id="!b2b2b2b2", text=text, short_name="B2", long_name="Bravo 2")


def test_drop_then_pickup_by_short_name(setup):
    store, link, h = setup
    h.on_text(alpha("DROP b2 meet at the bridge 0600"))
    assert link.sent[-1] == ("!a1a1a1a1", "OK message for b2 stored")
    h.on_text(bravo("status"))
    assert link.sent[-1] == ("!b2b2b2b2", "OK 1 messages waiting")
    h.on_text(bravo("PICKUP"))
    assert link.sent[-1] == ("!b2b2b2b2", "MSG A1 meet at the bridge 0600")
    h.on_text(bravo("PICKUP"))
    assert link.sent[-1] == ("!b2b2b2b2", "OK 0 messages waiting")


def test_pickup_matches_node_id_and_long_name(setup):
    store, link, h = setup
    h.on_text(alpha("DROP !b2b2b2b2 by id"))
    h.on_text(alpha("DROP bravo 2 not a long-name match"))  # recipient is the first word only
    store.store_message("A1", "Bravo 2", "by long name")
    h.on_text(bravo("PICKUP"))
    bodies = [t for to, t in link.sent if to == "!b2b2b2b2"]
    assert "MSG A1 by id" in bodies
    assert "MSG A1 by long name" in bodies
    assert not any("not a long-name" in b for b in bodies)


def test_pickup_caps_messages_per_request(setup):
    store, link, h = setup
    for i in range(MAX_PICKUP + 2):
        store.store_message("A1", "B2", f"m{i}")
    h.on_text(bravo("PICKUP"))
    sent = [t for to, t in link.sent]
    assert sent[:MAX_PICKUP] == [f"MSG A1 m{i}" for i in range(MAX_PICKUP)]
    assert sent[-1] == "OK 2 more waiting, send PICKUP again"
    assert store.pending_count_for({"b2"}) == 2


def test_drop_usage_error(setup):
    _, link, h = setup
    h.on_text(alpha("DROP onlyrecipient"))
    assert link.sent[-1][1].startswith("ERR usage")


def test_ignores_other_text(setup):
    _, link, h = setup
    h.on_text(alpha("hello everyone"))
    assert link.sent == []


def test_meshbus_rx_parse_and_tx_build():
    msg = parse_rx(json.dumps({"from": "!b2b2b2b2", "text": "PICKUP", "channel": 0, "ts": 1,
                               "from_short": "B2"}))
    assert msg.names == {"!b2b2b2b2", "b2"}
    assert parse_rx(b"garbage") is None
    assert parse_rx(json.dumps({"text": "no from"})) is None
    tx = json.loads(build_tx("x" * 300, "!b2b2b2b2", 0, "mesh-deadrop"))
    assert len(tx["text"]) == 200 and tx["to"] == "!b2b2b2b2" and tx["source"] == "mesh-deadrop"


def test_paced_reply_loop(setup):
    store, link, h = setup
    h._reply_interval = 0
    h.start()
    try:
        h.on_text(alpha("STATUS"))
        import time
        for _ in range(50):
            if link.sent:
                break
            time.sleep(0.02)
        assert link.sent == [("!a1a1a1a1", "OK 0 messages waiting")]
    finally:
        h.stop()
