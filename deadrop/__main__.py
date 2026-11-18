"""Entry point: python -m deadrop"""

import argparse
import asyncio
import logging
import os
import signal
import sys

import uvicorn


def parse_args():
    env = os.environ.get
    parser = argparse.ArgumentParser(
        description="Meshtastic Dead Drop. Uses the mesh through meshbus (blufor-tracker bridge) by default."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--serial", nargs="?", const="/dev/ttyUSB0", default=env("DEADROP_SERIAL") or None, metavar="PORT",
        help="Standalone: open the radio directly on PORT (default /dev/ttyUSB0). "
             "Do not use while mesh-bridge is running.",
    )
    mode.add_argument("--simulate", action="store_true", help="Run with simulated activity (no radio)")
    parser.add_argument("--port", dest="legacy_port", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--web-port", type=int, default=int(env("WEB_PORT", "8070")), help="Web dashboard port")
    parser.add_argument("--db-path", default=env("DEADROP_DB", "/var/lib/mesh-deadrop/messages.db"),
                        help="SQLite database path")
    parser.add_argument("--mqtt-host", default=env("MQTT_HOST", "127.0.0.1"), help="meshbus MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=int(env("MQTT_PORT", "1883")), help="meshbus MQTT port")
    args = parser.parse_args()
    if args.legacy_port and not args.serial:
        # Old invocations used --port for the serial device
        args.serial = args.legacy_port
    return args


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("deadrop")
    args = parse_args()
    # uvicorn re-raises SIGTERM after its own shutdown; turn it into a normal exit so the
    # finally blocks run (heartbeat publishes "stopped" instead of the broker's "error" will)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    from deadrop.handler import DeadDropHandler, SimulatedHandler
    from deadrop.mesh_link import LoggingMeshLink, MeshbusLink, SerialMeshLink
    from deadrop.store import MessageStore

    store = MessageStore(db_path=args.db_path)

    if args.simulate:
        handler = SimulatedHandler(store)
        link = LoggingMeshLink(handler.on_text)
    else:
        handler = DeadDropHandler(store)
        if args.serial:
            log.info("Standalone serial mode on %s", args.serial)
            link = SerialMeshLink(handler.on_text, port=args.serial)
        else:
            link = MeshbusLink("mesh-deadrop", handler.on_text, host=args.mqtt_host, port=args.mqtt_port)
    handler.set_link(link)
    link.start()
    handler.start()

    # Web dashboard
    from deadrop.web import app as web_module

    web_module.store = store
    web_module.link = link
    app = web_module.create_app()

    from deadrop.heartbeat import Heartbeat

    def heartbeat_state():
        if args.simulate:
            return "simulate", "ok", "simulated activity, no radio"
        stats = store.get_stats()
        detail = f"{type(link).__name__}; {stats['pending']} pending, {stats['nodes']} nodes"
        if not link.connected:
            return "cpu", "degraded", detail + "; mesh link down"
        return "cpu", "ok", detail

    heartbeat = Heartbeat("mesh-deadrop", heartbeat_state, port=args.web_port).start()

    log.info("Mesh Dead Drop started — Dashboard at http://0.0.0.0:%d", args.web_port)

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
        asyncio.run(run_web())
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        heartbeat.stop()
        handler.stop()
        link.stop()


if __name__ == "__main__":
    main()
