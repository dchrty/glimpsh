"""Main GlimpSh TUI application."""

import asyncio
import subprocess
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.binding import Binding

from .status import GazeStatusBar
from .terminal import TerminalWidget
from .cursor import GazeCursor
from .messages import GazeUpdate, GazeConnected, GazeDisconnected, GazeServerInfo
from .debug import DebugPanel
from .grid_adapter import TerminalGridAdapter
from ..gaze.client import GazeClient, GazeClientConfig
from ..gaze.protocol import GazePoint, ServerInfo
from ..terminal.focus import FocusManager


class GlimpShApp(App):
    """Main GlimpSh application."""

    CSS = """
    Screen {
        layout: vertical;
        layers: base overlay;
    }

    #terminal-grid {
        width: 100%;
        height: 1fr;
        layer: base;
        margin-top: 1;
    }

    TerminalWidget {
        width: 1fr;
        height: 1fr;
    }

    GazeCursor {
        layer: overlay;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        rows: int = 2,
        cols: int = 2,
        command: str = "bash",
        gaze_server_url: str = "ws://127.0.0.1:8001/ws/predict_gaze",
        dwell_time_ms: int = 200,
        gaze_enabled: bool = True,
        test_gaze: bool = False,
        debug: bool = False,
        voice: bool = False,
    ):
        super().__init__()
        self.grid_rows = rows
        self.grid_cols = cols
        self.command = command
        self.gaze_server_url = gaze_server_url
        self.dwell_time_ms = dwell_time_ms
        self.gaze_enabled = gaze_enabled
        self.test_gaze = test_gaze
        self.show_debug = debug
        self._voice_mode = voice

        self._gaze_client: Optional[GazeClient] = None
        self._mock_server: Optional[MockGazeServer] = None
        self._status_bar: Optional[GazeStatusBar] = None
        self._gaze_cursor: Optional[GazeCursor] = None
        self._debug_panel: Optional[DebugPanel] = None
        self._terminals: list[TerminalWidget] = []
        self._focus_manager: Optional[FocusManager] = None
        self._grid_adapter: Optional[TerminalGridAdapter] = None
        self._current_focus: int = 0  # Track for status bar
        self._last_gaze_log: tuple[float, float] = (0, 0)  # For debug throttling
        self._clipboard_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        """Compose the application UI."""
        # Status bar (includes app name and version)
        self._status_bar = GazeStatusBar()
        yield self._status_bar

        # Create grid layout
        grid = Grid(id="terminal-grid")
        grid.styles.grid_size_columns = self.grid_cols
        grid.styles.grid_size_rows = self.grid_rows

        # Create terminal widgets
        self._terminals = []
        for i in range(self.grid_rows * self.grid_cols):
            terminal = TerminalWidget(
                command=self.command,
                id=f"terminal-{i}",
            )
            self._terminals.append(terminal)

        with grid:
            for terminal in self._terminals:
                yield terminal

        # Gaze cursor (shown when gaze is active)
        if self.gaze_enabled:
            self._gaze_cursor = GazeCursor(id="gaze-cursor")
            yield self._gaze_cursor

        # Debug panel (shown when --debug flag)
        if self.show_debug:
            self._debug_panel = DebugPanel(id="debug-panel")
            yield self._debug_panel

    async def on_mount(self) -> None:
        """Set up the application after mounting."""
        # Set up focus management with grid adapter
        if self._terminals:
            self._grid_adapter = TerminalGridAdapter(
                terminals=self._terminals,
                rows=self.grid_rows,
                cols=self.grid_cols,
                on_focus=self._on_focus_changed,
            )

            # Create FocusManager with screen dimensions
            # Account for status bar (1) + grid margin (1) = 2 lines
            screen_width = self.screen.size.width
            screen_height = self.screen.size.height - 2
            self._focus_manager = FocusManager(
                target=self._grid_adapter,
                screen_width=screen_width,
                screen_height=screen_height,
                dwell_time_ms=self.dwell_time_ms,
            )

            # Focus first terminal
            self._grid_adapter.focus_pane(0)

        # Update status bar
        if self._status_bar:
            self._status_bar.set_focused_pane(0, len(self._terminals))

        # Debug startup log
        if self._debug_panel:
            self._debug_log("app", f"glimpsh started (grid={self.grid_rows}x{self.grid_cols})")
            self._debug_log("app", f"Screen: {self.screen.size.width}x{self.screen.size.height}")
            if self._debug_panel._log_file:
                self._debug_log("app", f"Log: {self._debug_panel._log_file}")

        # Start gaze tracking
        if self.gaze_enabled:
            # If test mode, start mock server first
            if self.test_gaze:
                self._start_mock_server()
                self._debug_log("server", f"MockGazeServer started at {self._mock_server.url}")
                # Share debug file with server for broadcast logging
                if self._debug_panel and self._debug_panel._file_handle:
                    self._mock_server._debug_file = self._debug_panel._file_handle

            # Connect to gaze server (real or mock)
            self._start_gaze_client()
        else:
            # Show as disabled in status bar
            if self._status_bar:
                self._status_bar.set_gaze_disabled()
            if self._gaze_cursor:
                self._gaze_cursor.hide()

        # Start clipboard watcher for voice input
        if self._voice_mode:
            self._clipboard_task = asyncio.create_task(self._clipboard_watcher())
            self._debug_log("app", "Voice mode: clipboard watcher started")

    @staticmethod
    def _get_clipboard_cmd() -> list[str]:
        """Return the platform clipboard read command."""
        import platform
        import shutil
        if platform.system() == "Darwin":
            return ["pbpaste"]
        # Linux: prefer xclip, fall back to xsel
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-o"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--output"]
        return []

    def _read_clipboard(self) -> str:
        """Read current clipboard content."""
        cmd = self._get_clipboard_cmd()
        if not cmd:
            return ""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
            return result.stdout
        except Exception:
            return ""

    async def _clipboard_watcher(self) -> None:
        """Watch clipboard and auto-type changes into focused pane."""
        cmd = self._get_clipboard_cmd()
        if not cmd:
            self._debug_log("voice", "No clipboard tool found (need pbpaste, xclip, or xsel)")
            return

        last_content = self._read_clipboard()

        while True:
            await asyncio.sleep(0.3)
            try:
                content = self._read_clipboard()
                if content and content != last_content:
                    last_content = content
                    terminal = self._terminals[self._current_focus]
                    terminal.write_text(content)
                    self._debug_log("voice", f"Pasted {len(content)} chars into pane {self._current_focus}")
                    # Cooldown: ignore follow-up clipboard writes (e.g. Wispr artifacts)
                    await asyncio.sleep(1.5)
                    # Re-snapshot so we don't re-paste the artifact
                    last_content = self._read_clipboard()
            except Exception:
                pass

    def _start_mock_server(self) -> None:
        """Start mock gaze server for testing."""
        # Lazy import - MockGazeServer is in the testing module
        from ..testing import MockGazeServer

        screen_width = self.screen.size.width
        screen_height = self.screen.size.height

        self._mock_server = MockGazeServer(
            host="127.0.0.1",
            port=9999,
            name="MockGaze",
        )
        self._mock_server.state.screen_width = screen_width
        self._mock_server.state.screen_height = screen_height
        self._mock_server.start()

        # Override server URL to point to mock
        self.gaze_server_url = self._mock_server.url

    def _start_gaze_client(self) -> None:
        """Start the gaze tracking client."""
        # Show connecting state immediately
        if self._status_bar:
            self._status_bar.set_connecting()

        config = GazeClientConfig(
            server_url=self.gaze_server_url,
        )

        self._gaze_client = GazeClient(
            config=config,
            on_gaze=self._on_gaze,
            on_connect=self._on_gaze_connect,
            on_disconnect=self._on_gaze_disconnect,
            on_server_info=self._on_server_info,
        )
        # Share debug file with client
        if self._debug_panel and self._debug_panel._file_handle:
            self._gaze_client._debug_file = self._debug_panel._file_handle
        self._gaze_client.start()

    def _on_gaze(self, gaze: GazePoint) -> None:
        """Handle gaze data from server - post message to main thread."""
        self.post_message(GazeUpdate(gaze.x, gaze.y, gaze.cell_row, gaze.cell_col))

    def on_gaze_update(self, message: GazeUpdate) -> None:
        """Handle gaze update message in main thread."""
        x, y = message.x, message.y

        # Convert normalized coordinates (0-1) to terminal cell coordinates
        screen_width = self.screen.size.width
        screen_height = self.screen.size.height
        if x <= 1.0 and y <= 1.0:
            # Normalized coordinates from eyetrax
            x = x * screen_width
            y = y * screen_height

        # Update status bar
        if self._status_bar:
            self._status_bar.update_gaze(x, y)

        # Update cursor position
        if self._gaze_cursor:
            if screen_width > 0 and screen_height > 0:
                x_pct = (x / screen_width) * 100
                y_pct = (y / screen_height) * 100
                self._gaze_cursor.update_position(x_pct, y_pct)
                # Only log if position changed
                last_x, last_y = self._last_gaze_log
                if abs(x - last_x) >= 1 or abs(y - last_y) >= 1:
                    self._debug_log("gaze", f"cursor: x={x:.0f} y={y:.0f} ({x_pct:.1f}%, {y_pct:.1f}%)")
                    self._last_gaze_log = (x, y)

        # Update focus via FocusManager
        if self._focus_manager:
            # Prefer cell info from eyetrax (has hysteresis built-in)
            if message.cell_row is not None and message.cell_col is not None:
                changed = self._focus_manager.update_from_cell(message.cell_row, message.cell_col)
                if changed:
                    self._debug_log("focus", f"Focus change to cell ({message.cell_row}, {message.cell_col})")
            else:
                # Fallback to coordinate-based focusing
                changed = self._focus_manager.update(x, y)
                if changed:
                    self._debug_log("focus", f"Focus change at ({x:.0f}, {y:.0f})")

    def _on_focus_changed(self, index: int) -> None:
        """Callback from FocusManager when focus changes."""
        self._current_focus = index
        if self._status_bar:
            self._status_bar.set_focused_pane(index, len(self._terminals))
        self._debug_log("focus", f"Focus changed to pane {index}")

    def _debug_log(self, source: str, text: str) -> None:
        """Log to debug panel if enabled."""
        if self._debug_panel:
            self._debug_panel.log(source, text)

    def _on_gaze_connect(self) -> None:
        """Handle gaze server connection - post message to main thread."""
        self.post_message(GazeConnected())

    def _on_gaze_disconnect(self) -> None:
        """Handle gaze server disconnection - post message to main thread."""
        self.post_message(GazeDisconnected())

    def _on_server_info(self, info: ServerInfo) -> None:
        """Handle server info message - post message to main thread."""
        self.post_message(GazeServerInfo(info.name, info.version))

    def on_gaze_connected(self, message: GazeConnected) -> None:
        """Handle connection message in main thread."""
        self._debug_log("client", "Connected to gaze server")
        if self._status_bar:
            self._status_bar.set_connected(True)
        if self._gaze_cursor:
            self._gaze_cursor.show()

    def on_gaze_disconnected(self, message: GazeDisconnected) -> None:
        """Handle disconnection message in main thread."""
        self._debug_log("client", "Disconnected from gaze server")
        if self._status_bar:
            self._status_bar.set_connected(False)
            # Show connecting again if still running
            if self._gaze_client and self._gaze_client._running:
                self._status_bar.set_connecting()
        if self._gaze_cursor:
            self._gaze_cursor.hide()

    def on_gaze_server_info(self, message: GazeServerInfo) -> None:
        """Handle server info message in main thread."""
        self._debug_log("server", f"Server: {message.name} v{message.version}")
        if self._status_bar:
            self._status_bar.set_server_name(message.name)

    def on_resize(self, event) -> None:
        """Handle screen resize - update FocusManager dimensions."""
        if self._focus_manager:
            width = self.screen.size.width
            height = self.screen.size.height - 2  # Account for status bar (1) + grid margin (1)
            self._focus_manager.screen_width = width
            self._focus_manager.screen_height = height
            self._focus_manager._inv_screen_width = 1.0 / width if width > 0 else 0.0
            self._focus_manager._inv_screen_height = 1.0 / height if height > 0 else 0.0

        if self._mock_server:
            self._mock_server.state.screen_width = self.screen.size.width
            self._mock_server.state.screen_height = self.screen.size.height

    def on_key(self, event) -> None:
        """Handle key events at app level."""
        # Route Ctrl+Arrow keys to mock server (if running)
        if self._mock_server:
            direction_map = {
                "ctrl+up": "up",
                "ctrl+down": "down",
                "ctrl+left": "left",
                "ctrl+right": "right",
            }
            if event.key in direction_map:
                direction = direction_map[event.key]
                self._mock_server.move_gaze(direction)
                state = self._mock_server.state
                self._debug_log("server", f"move_gaze({direction}) -> ({state.x:.2f}, {state.y:.2f})")
                event.prevent_default()
                event.stop()
                return

    async def action_quit(self) -> None:
        """Quit the application."""
        # Stop clipboard watcher
        if self._clipboard_task:
            self._clipboard_task.cancel()
            self._clipboard_task = None

        # Stop gaze client
        if self._gaze_client:
            self._gaze_client.stop()
            self._gaze_client = None

        # Stop mock server
        if self._mock_server:
            self._mock_server.stop()
            self._mock_server = None

        # Exit
        self.exit()


def run_tui(
    rows: int = 2,
    cols: int = 2,
    command: str = "bash",
    gaze_server_url: str = "ws://127.0.0.1:8001/ws/predict_gaze",
    dwell_time_ms: int = 200,
    gaze_enabled: bool = True,
    test_gaze: bool = False,
    debug: bool = False,
    voice: bool = False,
) -> int:
    """Run the GlimpSh TUI application."""
    app = GlimpShApp(
        rows=rows,
        cols=cols,
        command=command,
        gaze_server_url=gaze_server_url,
        dwell_time_ms=dwell_time_ms,
        gaze_enabled=gaze_enabled,
        test_gaze=test_gaze,
        debug=debug,
        voice=voice,
    )
    app.run()
    return 0
