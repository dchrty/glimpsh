# Gaze Server Protocol

glimpsh connects to any gaze server that implements this simple WebSocket protocol.

## Design Philosophy

This protocol is intentionally minimal. For terminal focus, we only need: **where on screen is the user looking?**

Future versions may draw from [Tobii Pro SDK](https://developer.tobiipro.com/commonconcepts/gaze.html) and [OpenXR](https://registry.khronos.org/OpenXR/specs/1.0/man/html/XrSystemEyeGazeInteractionPropertiesEXT.html) for richer data (per-eye tracking, validity codes, etc). Compatible with [glimpsh-eyetrax](https://github.com/dchrty/glimpsh-eyetrax).

## Connection

- **Transport**: WebSocket
- **Endpoint**: Any WebSocket URL (configure providers in config file)
- **Default**: `ws://127.0.0.1:8001/`

The endpoint path is configurable. Use whatever path your gaze server exposes.

## Message Flow

```
Client                              Server
  |                                   |
  |-------- WebSocket connect ------->|
  |                                   |
  |<----------- hello ----------------|  (server identifies itself)
  |                                   |
  |<----------- gaze point -----------|  (continuous stream)
  |<----------- gaze point -----------|
  |<----------- gaze point -----------|
  |             ...                   |
```

## Messages

All messages are JSON. The server sends messages; the client only listens.

### Hello (server → client)

Sent once on connection. Identifies the server.

```json
{
  "type": "hello",
  "name": "MyGazeServer",
  "version": "1.0"
}
```

| Field     | Type   | Required | Description           |
|-----------|--------|----------|-----------------------|
| `type`    | string | yes      | Must be `"hello"`     |
| `name`    | string | yes      | Server name           |
| `version` | string | no       | Server version        |

### Gaze Point (server → client)

Sent continuously at your tracking rate (e.g., 30-60 Hz).

```json
{
  "x_px": 1024,
  "y_px": 512
}
```

| Field        | Type   | Required | Description                      |
|--------------|--------|----------|----------------------------------|
| `x_px`       | number | yes*     | X coordinate in screen pixels    |
| `y_px`       | number | yes*     | Y coordinate in screen pixels    |
| `x`          | number | yes*     | Alternative: X coordinate        |
| `y`          | number | yes*     | Alternative: Y coordinate        |
| `timestamp`  | number | no       | Unix timestamp in seconds        |
| `confidence` | number | no       | Tracking confidence (0.0 - 1.0)  |
| `seq`        | number | no       | Sequence number for debugging    |

*Use either `x_px`/`y_px` or `x`/`y`. Pixel coordinates preferred.

### Error (server → client)

Optional. Report errors to the client.

```json
{
  "error": "Camera disconnected"
}
```

## Binary Format (Alternative)

For lower latency, servers may send binary messages instead of JSON:

| Bytes | Type           | Description        |
|-------|----------------|--------------------|
| 0-3   | float32 LE     | X coordinate       |
| 4-7   | float32 LE     | Y coordinate       |
| 8-11  | float32 LE     | Timestamp (optional) |
| 12-15 | float32 LE     | Confidence (optional) |

Minimum 8 bytes (x, y). Maximum 16 bytes (x, y, timestamp, confidence).

## Example Server (Python)

Minimal gaze server using `websockets`:

```python
import asyncio
import json
from websockets.server import serve

async def handle_client(websocket):
    # Send hello
    await websocket.send(json.dumps({
        "type": "hello",
        "name": "MyGazeServer",
        "version": "1.0"
    }))

    # Stream gaze points (replace with your eye tracker)
    while True:
        x, y = get_gaze_position()  # Your eye tracking code
        await websocket.send(json.dumps({
            "x_px": x,
            "y_px": y
        }))
        await asyncio.sleep(1/60)  # 60 Hz

async def main():
    async with serve(handle_client, "127.0.0.1", 8001):
        await asyncio.Future()  # Run forever

asyncio.run(main())
```

## Testing

Use glimpsh's built-in test mode to verify without hardware:

```bash
glimpsh --gaze test
```

This enables keyboard simulation: use `Ctrl+Arrow` keys to move the simulated gaze point.
