"""Mock gaze server for testing - implements the glimpsh gaze protocol."""

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Optional, Set

import websockets
from websockets.server import serve, WebSocketServerProtocol


@dataclass
class GazeState:
    """Shared gaze state that can be updated externally."""
    x: float = 0.5  # Normalized 0-1
    y: float = 0.5  # Normalized 0-1
    screen_width: int = 1920
    screen_height: int = 1080
    step: float = 0.08  # Larger step for visible movement

    def move(self, direction: str) -> None:
        """Move gaze in a direction."""
        if direction == "up":
            self.y = max(0.0, self.y - self.step)
        elif direction == "down":
            self.y = min(1.0, self.y + self.step)
        elif direction == "left":
            self.x = max(0.0, self.x - self.step)
        elif direction == "right":
            self.x = min(1.0, self.x + self.step)

    def to_pixels(self) -> tuple[int, int]:
        """Convert normalized coords to screen pixels."""
        return (
            int(self.x * self.screen_width),
            int(self.y * self.screen_height)
        )


class MockGazeServer:
    """
    A WebSocket server that implements the glimpsh gaze protocol.

    Protocol spec:
    - Endpoint: ws://{host}:{port}/ws/gaze
    - First message: {"type": "hello", "name": "...", "version": "..."}
    - Gaze messages: {"x_px": 1024, "y_px": 512}

    For testing, the server accepts control input via the shared
    GazeState object, which can be updated externally.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9999,
        broadcast_interval: float = 0.033,  # ~30Hz
        name: str = "MockGaze",
        version: str = "1.0",
    ):
        self.host = host
        self.port = port
        self.broadcast_interval = broadcast_interval
        self.name = name
        self.version = version
        self.state = GazeState()
        self._clients: Set[WebSocketServerProtocol] = set()
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._seq = 0  # Message sequence number for debugging
        self._debug_file = None  # Optional debug file handle

    @property
    def url(self) -> str:
        """Get the WebSocket URL for this server."""
        return f"ws://{self.host}:{self.port}/ws/gaze"

    def start(self) -> None:
        """Start the server in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

        # Wait for server to be ready
        import time
        for _ in range(50):  # 5 second timeout
            if self._server is not None:
                break
            time.sleep(0.1)

    def stop(self) -> None:
        """Stop the server gracefully."""
        self._running = False

        # Close all client connections
        if self._loop and self._clients:
            for client in list(self._clients):
                try:
                    self._loop.call_soon_threadsafe(client.close)
                except Exception:
                    pass

        # Wait for server thread to exit
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        self._server = None
        self._loop = None

    def move_gaze(self, direction: str) -> None:
        """Move the gaze position (called from main thread)."""
        self.state.move(direction)

    def _run_server(self) -> None:
        """Run the WebSocket server (in background thread)."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self) -> None:
        """Start serving and broadcasting."""
        async with serve(
            self._handle_client,
            self.host,
            self.port,
            process_request=self._process_request,
        ) as server:
            self._server = server

            # Start broadcast loop
            broadcast_task = asyncio.create_task(self._broadcast_loop())

            # Run until stopped
            while self._running:
                await asyncio.sleep(0.1)

            broadcast_task.cancel()
            try:
                await broadcast_task
            except asyncio.CancelledError:
                pass

    async def _process_request(self, path, request_headers):
        """Validate the request path."""
        if path != "/ws/gaze":
            return (404, [], b"Not Found")
        return None  # Continue with WebSocket handshake

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a client connection."""
        try:
            # Send hello message with server info FIRST (before adding to broadcast list)
            hello = json.dumps({
                "type": "hello",
                "name": self.name,
                "version": self.version,
            })
            await websocket.send(hello)

            # Send initial gaze position
            await self._send_gaze(websocket)

            # NOW add to broadcast list for ongoing updates
            self._clients.add(websocket)

            # Keep connection alive until server stops
            while self._running:
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue  # Check _running flag
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    async def _broadcast_loop(self) -> None:
        """Broadcast gaze position to all clients."""
        while self._running:
            try:
                if self._clients:
                    await self._broadcast_gaze()
            except Exception:
                pass
            await asyncio.sleep(self.broadcast_interval)

    async def _broadcast_gaze(self) -> None:
        """Send current gaze to all clients."""
        clients = list(self._clients)
        if not clients:
            return

        x_px, y_px = self.state.to_pixels()

        self._seq += 1
        message = json.dumps({"x_px": x_px, "y_px": y_px, "seq": self._seq})

        # Send to all clients
        for client in clients:
            try:
                await client.send(message)
            except Exception:
                self._clients.discard(client)

    async def _send_gaze(self, websocket: WebSocketServerProtocol) -> None:
        """Send current gaze to a specific client."""
        x_px, y_px = self.state.to_pixels()
        self._seq += 1
        message = json.dumps({"x_px": x_px, "y_px": y_px, "seq": self._seq})
        await websocket.send(message)
