"""FastAPI status dashboard for the dead drop."""

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Set by __main__.py
store = None
link = None

_clients: set[WebSocket] = set()

MAX_BODY = 180  # leaves room for "MSG <sender> " in a 200-character mesh text
MAX_RECIPIENT = 40


def web_sender() -> str:
    """Who web-composed drops are from (DEADROP_WEB_SENDER, default HQ)."""
    return os.environ.get("DEADROP_WEB_SENDER", "").strip() or "HQ"


def create_app():
    app = FastAPI(title="Mesh Dead Drop")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (STATIC_DIR / "index.html").read_text()

    @app.get("/api/stats")
    async def stats():
        if store is None:
            return {"total": 0, "delivered": 0, "pending": 0, "nodes": 0}
        return store.get_stats()

    @app.get("/api/health")
    async def health():
        return {
            "mesh_link": type(link).__name__ if link is not None else None,
            "mesh_connected": bool(getattr(link, "connected", False)),
        }

    @app.get("/api/nodes")
    async def nodes():
        if store is None:
            return []
        return store.get_node_list()

    @app.get("/api/messages")
    async def messages():
        if store is None:
            return []
        return store.get_recent_messages()

    @app.post("/api/drop")
    async def drop(payload: dict = Body(...)):
        """Leave a message from the web page, exactly like a radio "DROP <recipient> <message>":
        it waits in the store until the recipient sends PICKUP. Nothing is transmitted now."""
        if store is None:
            raise HTTPException(503, "Message store not ready")
        recipient = str(payload.get("recipient", "")).strip()
        body = " ".join(str(payload.get("body", "")).split())
        if not recipient or " " in recipient or len(recipient) > MAX_RECIPIENT:
            raise HTTPException(400, "Enter one recipient name, no spaces")
        if not body:
            raise HTTPException(400, "Enter a message")
        if len(body) > MAX_BODY:
            raise HTTPException(400, f"Keep the message under {MAX_BODY} characters")
        msg_id = store.store_message(web_sender(), recipient, body)
        logger.info("Stored web message from %s to %s", web_sender(), recipient)
        return {"id": msg_id, "sender": web_sender(), "recipient": recipient}

    @app.websocket("/ws/status")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        _clients.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            _clients.discard(ws)

    return app


async def broadcast_status():
    """Push stats to all connected WebSocket clients."""
    if store is None:
        return
    data = json.dumps(store.get_stats())
    dead = set()
    for ws in _clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


async def periodic_broadcast():
    """Broadcast status updates every 2 seconds."""
    while True:
        await broadcast_status()
        await asyncio.sleep(2)
