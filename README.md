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
| `DROP <recipient> <message>` | Store a message for recipient |
| `PICKUP` | Retrieve all messages addressed to you |
| `STATUS` | Check how many messages are waiting for you |

Responses:
- `MSG <sender> <message>` — a stored message
- `OK <n> messages stored/waiting`
- `ERR <reason>`

## Hardware

- Raspberry Pi 5
- Meshtastic radio (serial USB)

## Install

```bash
sudo bash deploy/install.sh
```

## Usage

```bash
# Standalone
sudo pi-profiles deadrop

# Manual (simulation mode)
source .venv/bin/activate
python -m deadrop --simulate
```

## Web Dashboard

Browse to `http://<pi-ip>:8070` for the status dashboard showing registered nodes, message counts, and delivery status.

## Security

V1 uses Meshtastic channel encryption for transport security. The dead drop stores messages in plaintext on the Pi. End-to-end encryption (sender encrypts with recipient's public key) is planned for v2.
