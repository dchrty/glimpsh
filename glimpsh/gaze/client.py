"""WebSocket client for gaze server connection."""

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from .protocol import GazePoint, MessageType, ServerInfo, parse_message


@dataclass
class GazeClientConfig:
    """Configuration for the gaze client."""

    server_url: str = "ws://127.0.0.1:8001/ws/predict_gaze"
    reconnect_delay: float = 0.5  # Fast reconnect for responsiveness


class GazeClient:
    """
    WebSocket client for receiving gaze data from a gaze server.

    Runs in a background thread and calls the callback with smoothed gaze points.
    """

    def __init__(
        self,
        config: Optional[GazeClientConfig] = None,
        on_gaze: Optional[Callable[[GazePoint], None]] = None,
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        on_server_info: Optional[Callable[[ServerInfo], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.config = config or GazeClientConfig()
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_server_info = on_server_info
        self.on_error = on_error

        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.on_gaze = on_gaze

        # Latest gaze point (thread-safe access)
        self._latest_gaze: Optional[GazePoint] = None
        self._gaze_lock = threading.Lock()

    @property
    def connected(self) -> bool:
        """Check if connected to the gaze server."""
        return self._connected

    @property
    def latest_gaze(self) -> Optional[GazePoint]:
        """Get the latest gaze point (thread-safe)."""
        with self._gaze_lock:
            return self._latest_gaze

    def start(self) -> None:
        """Start the gaze client in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the gaze client gracefully."""
        self._running = False

        # Give the connection loop a moment to exit cleanly
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        self._loop = None

    def _run_loop(self) -> None:
        """Run the asyncio event loop in the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._connect_loop())
        except Exception as e:
            if self.on_error:
                self.on_error(f"Event loop error: {e}")
        finally:
            self._loop.close()
            self._loop = None

    async def _connect_loop(self) -> None:
        """Main connection loop with auto-reconnect."""
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                if self._running:
                    if self.on_error:
                        self.on_error(f"Connection error: {e}")
                    await asyncio.sleep(self.config.reconnect_delay)

    async def _connect(self) -> None:
        """Connect to the gaze server and receive messages."""
        try:
            async with websockets.connect(
                self.config.server_url,
                close_timeout=0.5,
            ) as ws:
                self._connected = True
                if self.on_connect:
                    self.on_connect()

                try:
                    while self._running:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                            self._handle_message(message)
                        except asyncio.TimeoutError:
                            continue  # Check _running flag
                except ConnectionClosed:
                    pass
                finally:
                    self._connected = False
                    if self.on_disconnect:
                        self.on_disconnect()

        except Exception as e:
            self._connected = False
            raise

    def _handle_message(self, raw_message) -> None:
        """Handle a message from the gaze server."""
        try:
            msg = parse_message(raw_message)

            if msg.type == MessageType.HELLO and msg.server_info:
                if self.on_server_info:
                    self.on_server_info(msg.server_info)

            elif msg.type == MessageType.GAZE_POINT and msg.gaze_point:
                gaze = msg.gaze_point

                # Store latest gaze
                with self._gaze_lock:
                    old_gaze = self._latest_gaze
                    self._latest_gaze = gaze

                # Debug: log only when position changes
                if hasattr(self, '_debug_file') and self._debug_file:
                    if old_gaze is None or abs(gaze.x - old_gaze.x) >= 1 or abs(gaze.y - old_gaze.y) >= 1:
                        from datetime import datetime
                        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        self._debug_file.write(f"{ts} [recv  ] px=({gaze.x:.0f},{gaze.y:.0f})\n")
                        self._debug_file.flush()

                # Call callback
                if self.on_gaze:
                    self.on_gaze(gaze)

            elif msg.type == MessageType.ERROR:
                if self.on_error:
                    self.on_error(msg.error or "Unknown error")

        except Exception as e:
            if self.on_error:
                self.on_error(f"Message handling error: {e}")


class MockGazeClient:
    """
    Mock gaze client for testing without a gaze server.

    Simulates gaze movement in a circular pattern.
    """

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        on_gaze: Optional[Callable[[GazePoint], None]] = None,
        speed: float = 0.5,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.on_gaze = on_gaze
        self.speed = speed

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._angle = 0.0

    @property
    def connected(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the mock gaze client."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the mock gaze client."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run_loop(self) -> None:
        """Generate mock gaze points."""
        import math

        cx = self.screen_width / 2
        cy = self.screen_height / 2
        rx = self.screen_width * 0.3
        ry = self.screen_height * 0.3

        while self._running:
            self._angle += self.speed * 0.1

            x = cx + rx * math.cos(self._angle)
            y = cy + ry * math.sin(self._angle)

            gaze = GazePoint(x=x, y=y, timestamp=time.time())

            if self.on_gaze:
                self.on_gaze(gaze)

            time.sleep(1 / 60)  # ~60 Hz
