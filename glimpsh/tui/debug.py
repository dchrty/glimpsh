"""Debug panel for showing server/client logs."""

import os
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.widgets import RichLog
from textual.containers import Container
from textual.message import Message
from rich.text import Text


class DebugLog(Message):
    """Message to add a log entry."""

    __slots__ = ('source', 'text')

    def __init__(self, source: str, text: str) -> None:
        super().__init__()
        self.source = source
        self.text = text


# Source colors for log entries
SOURCE_COLORS = {
    "server": "#00ff00",
    "client": "#00aaff",
    "gaze": "#ffaa00",
    "focus": "#ff00ff",
    "app": "#ffffff",
}


def get_log_dir() -> Path:
    """Get the log directory following XDG spec."""
    # Use XDG_DATA_HOME or default to ~/.local/share
    xdg_data = os.environ.get("XDG_DATA_HOME", "")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    return base / "glimpsh" / "logs"


def get_session_log_path() -> Path:
    """Get a unique log file path for this session."""
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return log_dir / f"glimpsh-{timestamp}.log"


class DebugPanel(Container):
    """Scrollable debug panel showing logs."""

    DEFAULT_CSS = """
    DebugPanel {
        dock: bottom;
        width: 100%;
        height: 8;
        background: #1a1a2e;
        border-top: solid #444466;
    }
    DebugPanel:focus-within {
        border-top: solid #6666aa;
    }
    DebugPanel RichLog {
        background: #1a1a2e;
        scrollbar-size: 1 1;
    }
    """

    def __init__(
        self,
        max_lines: int = 500,
        id: Optional[str] = None,
    ) -> None:
        super().__init__(id=id)
        self._max_lines = max_lines
        self._rich_log: Optional[RichLog] = None
        self._log_file: Optional[Path] = None
        self._file_handle = None
        self._text_buffer: deque[str] = deque(maxlen=max_lines)

    def on_mount(self) -> None:
        """Open log file on mount."""
        try:
            self._log_file = get_session_log_path()
            self._file_handle = open(self._log_file, "a")
            self._file_handle.write(f"# glimpsh debug log started {datetime.now().isoformat()}\n")
            self._file_handle.flush()
        except Exception:
            self._file_handle = None

    def on_unmount(self) -> None:
        """Close log file on unmount."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    def compose(self):
        """Create the RichLog widget."""
        self._rich_log = RichLog(
            highlight=True,
            markup=True,
            max_lines=self._max_lines,
            auto_scroll=True,
        )
        yield self._rich_log

    def log(self, source: str, text: str) -> None:
        """Add a log entry with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        plain_line = f"{ts} [{source[:6]:6}] {text}"

        # Store in text buffer for copy
        self._text_buffer.append(plain_line)

        # Write to file
        if self._file_handle:
            try:
                self._file_handle.write(f"{plain_line}\n")
                self._file_handle.flush()
            except Exception:
                pass

        # Write to UI
        if self._rich_log:
            color = SOURCE_COLORS.get(source, "#888888")
            log_text = Text()
            log_text.append(f"{ts} ", style="#666666")
            log_text.append(f"[{source[:6]:6}] ", style=color)
            log_text.append(text, style="#cccccc")
            self._rich_log.write(log_text)

    def on_debug_log(self, message: DebugLog) -> None:
        """Handle debug log messages."""
        self.log(message.source, message.text)
