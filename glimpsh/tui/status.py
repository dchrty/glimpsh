"""Status bar widget showing gaze server status and coordinates."""

from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text

from .. import __version__


class GazeStatusBar(Widget):
    """Status bar showing gaze server connection and coordinates."""

    DEFAULT_CSS = """
    GazeStatusBar {
        dock: top;
        height: 1;
        width: 100%;
        background: #333333;
        color: #ffffff;
        padding: 0 1;
    }
    """

    can_focus = False  # Don't steal focus from terminals

    connected = reactive(False)
    connecting = reactive(False)
    server_name = reactive("")
    gaze_disabled = reactive(False)
    gaze_x = reactive(0)
    gaze_y = reactive(0)
    focused_pane = reactive(0)
    total_panes = reactive(0)

    def render(self) -> Text:
        """Render the status bar."""
        text = Text()

        # App name
        text.append(" glimpsh ", style="bold #00ff00")
        text.append("│ ", style="#666666")

        # Connection status
        if self.gaze_disabled:
            text.append("○ ", style="#666666")
            text.append("Gaze: Disabled", style="#666666")
        elif self.connected:
            text.append("● ", style="bold #00ff00")
            if self.server_name:
                text.append(f"Gaze: {self.server_name}", style="#aaaaaa")
            else:
                text.append("Gaze: Connected", style="#aaaaaa")
        elif self.connecting:
            text.append("◌ ", style="bold #ffaa00")
            text.append("Gaze: Connecting...", style="#888888")
        else:
            text.append("○ ", style="bold #ff4444")
            text.append("Gaze: Disconnected", style="#888888")

        text.append(" │ ", style="#666666")

        # Coordinates (hide if gaze disabled)
        if self.gaze_disabled:
            text.append("               ", style="#666666")
        else:
            text.append(f"X: {self.gaze_x:4.0f}  Y: {self.gaze_y:4.0f}", style="#aaaaaa")

        text.append(" │ ", style="#666666")

        # Focused pane
        text.append(f"Pane: {self.focused_pane + 1}/{self.total_panes}", style="#aaaaaa")

        text.append(" │ ", style="#666666")

        # Help hint
        text.append("Ctrl+Q:Quit", style="#666666")

        # Right-align version
        current_len = len(text.plain)
        width = self.size.width if self.size.width > 0 else 80
        version_str = f"v{__version__}"
        padding = width - current_len - len(version_str) - 1
        if padding > 0:
            text.append(" " * padding)
        text.append(version_str, style="bold #888888")

        return text

    def update_gaze(self, x: float, y: float) -> None:
        """Update gaze coordinates."""
        self.gaze_x = x
        self.gaze_y = y

    def set_connected(self, connected: bool) -> None:
        """Set connection status."""
        self.connected = connected
        if connected:
            self.connecting = False

    def set_connecting(self) -> None:
        """Set connecting state."""
        self.connecting = True
        self.connected = False

    def set_server_name(self, name: str) -> None:
        """Set the server name to display."""
        self.server_name = name

    def set_focused_pane(self, index: int, total: int) -> None:
        """Set focused pane info."""
        self.focused_pane = index
        self.total_panes = total

    def set_gaze_disabled(self) -> None:
        """Mark gaze as disabled."""
        self.gaze_disabled = True
