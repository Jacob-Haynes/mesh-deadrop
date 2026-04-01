"""FastAPI status dashboard for the dead drop."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Set by __main__.py
store = None

_clients: set[WebSocket] = set()


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
    _clients -= dead


async def periodic_broadcast():
    """Broadcast status updates every 2 seconds."""
    while True:
        await broadcast_status()
        await asyncio.sleep(2)
