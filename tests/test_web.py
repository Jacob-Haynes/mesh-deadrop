import asyncio

from fastapi.testclient import TestClient

from deadrop.store import MessageStore
from deadrop.web import app as web_module


def test_api_and_broadcast_survive_dead_client(tmp_path):
    web_module.store = MessageStore(db_path=str(tmp_path / "m.db"))
    client = TestClient(web_module.create_app())
    assert client.get("/api/stats").json()["total"] == 0
    assert client.get("/api/health").status_code == 200

    class DeadWS:
        async def send_text(self, data):
            raise RuntimeError("closed")

    web_module._clients.add(DeadWS())
    asyncio.run(web_module.broadcast_status())  # used to raise UnboundLocalError
    assert not web_module._clients
