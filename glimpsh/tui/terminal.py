"""Terminal widget using pyte for terminal emulation."""

import asyncio
import fcntl
import os
import pty
import re
import struct
import termios
from typing import Optional

import pyte
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.style import Style

# Filter out escape sequences that pyte doesn't understand
# Kitty keyboard protocol: \x1b[?1u, \x1b[>1u, \x1b[<1u, \x1b[=1u, etc.
_UNSUPPORTED_ESCAPES = re.compile(r"\x1b\[[?>=<]?\d*u")


class TerminalWidget(Widget):
    """A terminal emulator widget."""

    DEFAULT_CSS = """
    TerminalWidget {
        border: solid green;
        border-title-color: transparent;
        background: #1a1a1a;
    }
    TerminalWidget:focus {
        border: solid #00ff00;
    }
    TerminalWidget.-inactive {
        border: solid #444444;
    }
    """

    can_focus = True

    is_focused_pane = reactive(False)

    def __init__(
        self,
        command: str = "bash",
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.command = command
        self._master_fd: Optional[int] = None
        self._pid: Optional[int] = None
        self._screen: Optional[pyte.Screen] = None
        self._stream: Optional[pyte.Stream] = None
        self._read_task: Optional[asyncio.Task] = None

    def on_mount(self) -> None:
        """Start the terminal process when mounted."""
        self._start_process()

    def on_unmount(self) -> None:
        """Clean up when unmounted."""
        self._stop_process()

    def _start_process(self) -> None:
        """Start the shell process."""
        # Create pseudo-terminal
        self._pid, self._master_fd = pty.fork()

        if self._pid == 0:
            # Child process - set up environment and run command
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLORTERM"] = "truecolor"
            os.environ["FORCE_COLOR"] = "1"
            os.environ["CLICOLOR_FORCE"] = "1"
            os.execvp("/bin/bash", ["bash", "-c", self.command])
        else:
            # Parent process
            # Set non-blocking
            flags = fcntl.fcntl(self._master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self._master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Initialize terminal emulator
            self._screen = pyte.Screen(80, 24)
            self._stream = pyte.Stream(self._screen)

            # Start reading from the PTY
            self._read_task = asyncio.create_task(self._read_loop())

            # Set initial size
            self.call_later(self._resize_pty)

    def _stop_process(self) -> None:
        """Stop the shell process."""
        if self._read_task:
            self._read_task.cancel()
            self._read_task = None

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        if self._pid is not None:
            try:
                os.kill(self._pid, 9)
                os.waitpid(self._pid, 0)
            except (OSError, ChildProcessError):
                pass
            self._pid = None

    def _resize_pty(self) -> None:
        """Resize the PTY to match widget size."""
        if self._master_fd is None or self._screen is None:
            return

        # Get widget size (subtract border)
        width = max(self.size.width - 2, 10)
        height = max(self.size.height - 2, 5)

        # Resize screen
        self._screen.resize(height, width)

        # Resize PTY
        try:
            winsize = struct.pack("HHHH", height, width, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def on_resize(self, event) -> None:
        """Handle resize events."""
        self._resize_pty()

    async def _read_loop(self) -> None:
        """Read from PTY and update screen."""
        while self._master_fd is not None:
            try:
                data = os.read(self._master_fd, 65536)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    # Filter out escape sequences pyte doesn't understand
                    text = _UNSUPPORTED_ESCAPES.sub("", text)
                    self._stream.feed(text)
                    self.refresh()
                else:
                    await asyncio.sleep(0.05)  # No data, wait longer
            except BlockingIOError:
                await asyncio.sleep(0.05)  # No data available, wait
            except OSError:
                break
            await asyncio.sleep(0.016)  # ~60fps max refresh rate

    def on_key(self, event) -> None:
        """Handle key events."""
        if self._master_fd is None:
            return

        # Let app-level bindings handle Ctrl+Q, Ctrl+C, and Ctrl+Arrow
        if event.key in ("ctrl+q", "ctrl+c", "ctrl+up", "ctrl+down", "ctrl+left", "ctrl+right"):
            return  # Don't consume, let it bubble up to app

        # Map special keys
        key_map = {
            "enter": "\r",
            "tab": "\t",
            "escape": "\x1b",
            "backspace": "\x7f",
            "delete": "\x1b[3~",
            "up": "\x1b[A",
            "down": "\x1b[B",
            "right": "\x1b[C",
            "left": "\x1b[D",
            "home": "\x1b[H",
            "end": "\x1b[F",
            "pageup": "\x1b[5~",
            "pagedown": "\x1b[6~",
        }

        key = event.key

        if key in key_map:
            data = key_map[key]
        elif event.character:
            data = event.character
        else:
            return

        try:
            os.write(self._master_fd, data.encode())
        except OSError:
            pass

        event.prevent_default()
        event.stop()

    def write_text(self, text: str) -> None:
        """Write text directly to the terminal PTY."""
        if self._master_fd is not None:
            try:
                os.write(self._master_fd, text.encode())
            except OSError:
                pass

    def render(self) -> Text:
        """Render the terminal content with colors."""
        if self._screen is None:
            return Text("Starting...")

        text = Text()

        for y in range(self._screen.lines):
            if y > 0:
                text.append("\n")

            line = self._screen.buffer[y]
            for x in range(self._screen.columns):
                char = line[x]
                char_text = char.data if char.data else " "

                # Build style from pyte character attributes
                style = self._pyte_char_to_style(char)
                text.append(char_text, style=style)

            # Strip trailing spaces for cleaner rendering
            # (but keep the line structure)

        return text

    def _pyte_char_to_style(self, char) -> Style:
        """Convert pyte character attributes to Rich Style."""
        fg = self._pyte_color_to_rich(char.fg, default="white")
        bg = self._pyte_color_to_rich(char.bg, default=None)

        return Style(
            color=fg,
            bgcolor=bg,
            bold=char.bold,
            italic=char.italics,
            underline=char.underscore,
            reverse=char.reverse,
        )

    def _pyte_color_to_rich(self, color, default=None) -> str:
        """Convert pyte color to Rich color string."""
        if color == "default" or color is None:
            return default

        # Standard 16 colors - pyte uses lowercase
        color_map = {
            "black": "black",
            "red": "red",
            "green": "green",
            "brown": "yellow",  # pyte uses "brown" for yellow
            "yellow": "yellow",
            "blue": "blue",
            "magenta": "magenta",
            "cyan": "cyan",
            "white": "white",
            "brightblack": "bright_black",
            "brightred": "bright_red",
            "brightgreen": "bright_green",
            "brightbrown": "bright_yellow",
            "brightyellow": "bright_yellow",
            "brightblue": "bright_blue",
            "brightmagenta": "bright_magenta",
            "brightcyan": "bright_cyan",
            "brightwhite": "bright_white",
        }

        if isinstance(color, str):
            normalized = color.lower()
            if normalized in color_map:
                return color_map[normalized]
            # pyte returns 256/RGB colors as hex WITHOUT # prefix (e.g., "ff8700")
            if len(normalized) == 6 and all(c in "0123456789abcdef" for c in normalized):
                return f"#{normalized}"
            # Pass through colors with # prefix
            if normalized.startswith("#"):
                return normalized
            return default

        # Handle 256 color codes (integers)
        if isinstance(color, int):
            return f"color({color})"

        # Handle RGB tuples
        if isinstance(color, tuple) and len(color) == 3:
            return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

        return default

    def watch_is_focused_pane(self, is_focused: bool) -> None:
        """Update styling when focus changes."""
        if is_focused:
            self.remove_class("-inactive")
        else:
            self.add_class("-inactive")
