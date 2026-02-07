"""Gaze cursor overlay widget."""

from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text


# Breathing pulse animation (larger unicode characters)
PULSE_FRAMES = [
    "·", "•", "●", "◉", "◎", "○", "◎", "◉", "●", "•", "·"
]

# Bright colors for each frame (gradient cycle)
PULSE_COLORS = [
    "#00ff88",  # green
    "#00ffcc",  # teal
    "#00ddff",  # cyan
    "#00aaff",  # light blue
    "#aa88ff",  # purple
    "#ff66ff",  # magenta
    "#ff6688",  # pink
    "#ff4444",  # red
    "#ff8800",  # orange
    "#ffcc00",  # yellow
    "#88ff00",  # lime
]


class GazeCursor(Widget):
    """
    A gaze cursor that floats over the terminal grid.

    Renders as an animated spinner at the gaze position.
    """

    DEFAULT_CSS = """
    GazeCursor {
        layer: overlay;
        width: 1;
        height: 1;
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
        content-align: center middle;
    }
    """

    can_focus = False  # Don't steal focus from terminals

    # Position as percentages (0-100)
    gaze_x_pct = reactive(50.0)
    gaze_y_pct = reactive(50.0)
    visible = reactive(True)
    frame_index = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._frames = PULSE_FRAMES
        self._animation_timer = None

    def on_mount(self) -> None:
        """Start animation when mounted."""
        self._start_animation()

    def on_unmount(self) -> None:
        """Stop animation when unmounted."""
        self._stop_animation()

    def _start_animation(self) -> None:
        """Start the animation timer."""
        if self._animation_timer is None:
            # Breathing animation
            self._animation_timer = self.set_interval(0.12, self._next_frame)

    def _stop_animation(self) -> None:
        """Stop the animation timer."""
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None

    def _next_frame(self) -> None:
        """Advance to next animation frame."""
        if self.visible:
            self.frame_index = (self.frame_index + 1) % len(self._frames)

    def render(self) -> Text:
        """Render the gaze cursor."""
        if not self.visible:
            return Text("")

        char = self._frames[self.frame_index]
        color = PULSE_COLORS[self.frame_index % len(PULSE_COLORS)]
        return Text(char, style=f"bold {color}")

    def update_position(self, x_pct: float, y_pct: float) -> None:
        """
        Update cursor position.

        Args:
            x_pct: X position as percentage (0-100)
            y_pct: Y position as percentage (0-100)
        """
        self.gaze_x_pct = max(0, min(100, x_pct))
        self.gaze_y_pct = max(0, min(100, y_pct))
        self._update_offset()

    def _update_offset(self) -> None:
        """Update the widget offset based on gaze position."""
        if self.parent is None:
            return

        # Get parent size
        try:
            parent_width = self.screen.size.width
            parent_height = self.screen.size.height
        except Exception:
            return

        # Calculate pixel position
        x = int((self.gaze_x_pct / 100) * parent_width)
        y = int((self.gaze_y_pct / 100) * parent_height)

        # Clamp to screen bounds
        x = max(0, min(parent_width - 1, x))
        y = max(1, min(parent_height - 1, y))  # Account for status bar

        # Update position using CSS offset
        self.styles.offset = (x, y)
        self.refresh()

    def watch_gaze_x_pct(self, value: float) -> None:
        """React to x position changes."""
        self._update_offset()

    def watch_gaze_y_pct(self, value: float) -> None:
        """React to y position changes."""
        self._update_offset()

    def watch_frame_index(self, value: int) -> None:
        """React to frame changes by refreshing."""
        self.refresh()

    def show(self) -> None:
        """Show the cursor."""
        self.visible = True
        self._start_animation()

    def hide(self) -> None:
        """Hide the cursor."""
        self.visible = False
        self._stop_animation()
