"""The page uses the shared ISR kit look (ui-kit/UI-SPEC.md): links isr-ui.css/js, serves exact copies."""

import hashlib

from fastapi.testclient import TestClient

from deadrop.web import app as web_module

KIT_SHA256 = {
    "isr-ui.css": "4e19df9824145ead677fc30dfa28eb802294151ee16e3c4046545c6d9ce89666",
    "isr-ui.js": "a0b67a8409914a0376be7e2f51d7d4cca0fd86f7ab7ea25f048aa855cb9b1fb9",
}


def _client():
    return TestClient(web_module.create_app())


def test_page_links_the_kit_and_has_one_header_pill():
    html = _client().get("/").text
    assert '<link rel="stylesheet" href="/static/isr-ui.css">' in html
    assert '<script src="/static/isr-ui.js"></script>' in html
    assert html.index("isr-ui.css") < html.index("<style>")  # kit first, own layout after
    assert html.count('id="isr-status"') == 1 and 'id="isr-kit-link"' in html
    assert html.count("isr-btn primary") <= 1
    assert "Courier New" not in html and "#00ff41" not in html  # old look gone


def test_served_kit_files_are_byte_identical():
    c = _client()
    for name, sha in KIT_SHA256.items():
        r = c.get(f"/static/{name}")
        assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == sha, name


def test_compose_drop_stores_like_a_radio_drop(tmp_path, monkeypatch):
    from deadrop.store import MessageStore

    monkeypatch.delenv("DEADROP_WEB_SENDER", raising=False)
    web_module.store = MessageStore(db_path=str(tmp_path / "m.db"))
    c = _client()
    r = c.post("/api/drop", json={"recipient": "Bravo2", "body": "Meet at  checkpoint bravo 0600"})
    assert r.status_code == 200 and r.json()["sender"] == "HQ"
    (m,) = web_module.store.get_messages_for({"bravo2"})
    assert (m["sender"], m["body"]) == ("HQ", "Meet at checkpoint bravo 0600")
    assert c.get("/api/messages").json()[0]["recipient"] == "Bravo2"
    assert "body" not in c.get("/api/messages").json()[0]  # text still never shown on the page
    assert c.post("/api/drop", json={"recipient": "two words", "body": "x"}).status_code == 400
    assert c.post("/api/drop", json={"recipient": "Bravo2", "body": " "}).status_code == 400
    assert c.post("/api/drop", json={"recipient": "Bravo2", "body": "x" * 181}).status_code == 400
