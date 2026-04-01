"""Entry point: python -m deadrop"""

import argparse
import asyncio
import logging

import uvicorn


def parse_args():
    parser = argparse.ArgumentParser(description="Meshtastic Dead Drop")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Meshtastic serial port")
    parser.add_argument("--web-port", type=int, default=8070, help="Web dashboard port")
    parser.add_argument("--db-path", default="/opt/mesh-deadrop/messages.db", help="SQLite database path")
    parser.add_argument("--simulate", action="store_true", help="Run with simulated activity")
    return parser.parse_args()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("deadrop")
    args = parse_args()

    from deadrop.store import MessageStore

    store = MessageStore(db_path=args.db_path)

    # Start handler
    if args.simulate:
        from deadrop.handler import SimulatedHandler
        handler = SimulatedHandler(store)
        handler.start()
    else:
        from deadrop.handler import DeadDropHandler
        handler = DeadDropHandler(store)
        handler.start(args.port)

    # Web dashboard
    from deadrop.web import app as web_module

    web_module.store = store
    app = web_module.create_app()

    log.info("Mesh Dead Drop started — Dashboard at http://0.0.0.0:%d", args.web_port)

    loop = asyncio.new_event_loop()

    async def run_web():
        config = uvicorn.Config(
            app, host="0.0.0.0", port=args.web_port, log_level="warning", loop="asyncio",
        )
        server = uvicorn.Server(config)
        broadcast_task = asyncio.create_task(web_module.periodic_broadcast())
        try:
            await server.serve()
        finally:
            broadcast_task.cancel()

    try:
        loop.run_until_complete(run_web())
    except KeyboardInterrupt:
        log.info("Shutting down")


if __name__ == "__main__":
    main()
