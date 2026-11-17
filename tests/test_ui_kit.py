"""The page uses the shared ISR kit look (ui-kit/UI-SPEC.md): links isr-ui.css/js, serves exact copies."""

import hashlib

from fastapi.testclient import TestClient

from deadrop.web import app as web_module

KIT_VERSION = 2
KIT_SHA256 = {  # ui-kit v2 (isr-ui.css/js line 1 says v2)
    "isr-ui.css": "ed601e0494d7b8c93f246205d53a03916b15ceb7eb3a54526a6cd4a447879ec7",
    "isr-ui.js": "191f2b6dce0c52a760a8fdeddf4d5f127399d7d3e1684dcc26a5dbe78874d274",
    "fonts/OFL-BarlowCondensed.txt": "186d750eb496a4c17a76385f82be6aea2ac1cf2de074a811d63786cf374ea73f",
    "fonts/OFL-IBMPlexMono.txt": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    "fonts/barlow-condensed-500.woff2": "31ff5e6e96a096fde4d78bc838719e69b093db2d0b062b96e423c065a6d1b2b1",
    "fonts/barlow-condensed-600.woff2": "5bc49d41f32810a114765314392332ce2acae2276635eee265a50319a12c1b49",
    "fonts/ibm-plex-mono-400.woff2": "52de70091213c9eab340e2a7ac59e7b6b2b94e089bf69ef38479b22cfde4274c",
    "fonts/ibm-plex-mono-500.woff2": "f17f51948d10b67d907393ccbac551912f2c2bd2c5af19be3aabe2f456f8fe54",
}


def _client():
    return TestClient(web_module.create_app())


def test_page_links_the_kit_and_has_one_header_pill():
    html = _client().get("/").text
    assert f'<link rel="stylesheet" href="/static/isr-ui.css?v={KIT_VERSION}">' in html
    assert f'<script src="/static/isr-ui.js?v={KIT_VERSION}"></script>' in html
    assert html.index("isr-ui.css") < html.index("<style>")  # kit first, own layout after
    assert html.count('id="isr-status"') == 1 and 'id="isr-kit-link"' in html
    assert html.count("isr-btn primary") <= 1
    assert "Courier New" not in html and "#00ff41" not in html  # old look gone
    page_css = html[html.index("<style>"):html.index("</style>")]
    assert "#" not in page_css.replace("#isr", "")  # no colours of our own: kit variables only
    assert ">ISR " not in html and " ISR<" not in html  # ISTAR in anything a person reads


def test_served_kit_files_are_byte_identical():
    c = _client()
    for name, sha in KIT_SHA256.items():
        r = c.get(f"/static/{name}")
        assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == sha, name
    assert f"v{KIT_VERSION}" in c.get("/static/isr-ui.css").text.splitlines()[0]


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
