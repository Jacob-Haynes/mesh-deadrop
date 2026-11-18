# Mesh Dead Drop

Meshtastic store-and-forward message relay for Raspberry Pi 5. Nodes that come within radio range can drop encrypted messages for specific recipients. Messages are stored until the recipient comes in range and requests pickup.

## How It Works

```
Node A (sender) → radio → Pi (dead drop) → stores message
                                                 ↓
Node B (recipient) → radio → Pi → delivers stored messages
```

## Protocol

Send text messages to the dead drop node:

| Command | Description |
|---------|-------------|
| `DROP <recipient> <message>` | Store a message for recipient (node id like `!a1b2c3d4`, short name or long name with no spaces) |
| `PICKUP` | Retrieve all messages addressed to you |
| `STATUS` | Check how many messages are waiting for you |

Responses:
- `MSG <sender> <message>` — a stored message
- `OK message for <recipient> stored` / `OK <n> messages waiting`
- `ERR <reason>`

A recipient's PICKUP/STATUS matches messages addressed to their node id, short name or long name (case-insensitive). PICKUP delivers up to 5 messages at a time, spaced ~3 s apart to respect mesh airtime. It says how many are left.

## Hardware and Radio Access

- Raspberry Pi 5
- Meshtastic radio on USB, **owned by the [blufor-tracker](https://github.com/Jacob-Haynes/blufor-tracker) bridge (`mesh-bridge`)**

Only one process can open the radio's serial port. On the shared Pi the dead drop reaches the mesh through **meshbus**: MQTT on `127.0.0.1:1883`. It reads `meshbus/rx` and replies on `meshbus/tx`. So `mesh-bridge` (and OpenTAKServer, whose RabbitMQ is the broker) must be running. If the broker is not up yet the dead drop keeps retrying, and the dashboard still works.

For standalone use with no bridge, open the radio directly with `--serial [PORT]`. Never do this while `mesh-bridge` is running.

## Install

```bash
sudo bash deploy/install.sh
```

Safe to re-run. It installs to `/opt/mesh-deadrop`, stores data in `/var/lib/mesh-deadrop/messages.db` and config in `/etc/mesh-deadrop.env` (see `deploy/mesh-deadrop.env.example`). It does not enable the service at boot; pi-profiles starts it.

## Usage

```bash
# On the Pi (opentakserver + mesh-bridge + mesh-deadrop)
sudo pi-profiles mesh-deadrop

# Manual
source .venv/bin/activate
python -m deadrop --simulate                 # fake activity, no radio; replies start "[SIM] "
python -m deadrop                            # meshbus (needs mesh-bridge)
python -m deadrop --serial /dev/ttyUSB0      # standalone, radio direct
```

To test meshbus end to end on a laptop, run any MQTT broker plus `python -m bridge.mqtt_shim --simulate` from blufor-tracker. It sends fake `DROP`/`PICKUP` texts.

## Heartbeat

Every 10 s the dead drop publishes a retained JSON message to `isrkit/heartbeat/mesh-deadrop` (`status` ok/degraded, `mode` cpu/simulate) for the launcher. `host` is `ISR_HOST` if set, else the lowercased short hostname. It publishes `stopped` on a clean exit; `HEARTBEAT=0` turns it off.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt   # versions are capped at the ones tested
python -m pytest
```

## Web Dashboard

Browse to `http://<pi-ip>:8070`. The page lists messages (who to whom, waiting or delivered; the text is never shown) and has a **Send** box that leaves a message for a recipient, exactly like a radio `DROP`. The recipient collects it with `PICKUP`. Web messages are from `DEADROP_WEB_SENDER` (default `HQ`). API: `POST /api/drop` `{"recipient": "Bravo2", "body": "..."}` (one-word recipient, up to 180 characters).

## Security

V1 uses Meshtastic channel encryption for transport security. The dead drop stores messages in plaintext on the Pi. End-to-end encryption (sender encrypts with recipient's public key) is planned for v2.

## License

MIT. See [LICENSE](LICENSE).
