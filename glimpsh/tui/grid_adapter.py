"""Adapter to make TerminalWidget grid implement FocusTarget protocol."""

from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .terminal import TerminalWidget


class TerminalGridAdapter:
    """
    Adapts a list of TerminalWidgets to the FocusTarget protocol.

    This allows FocusManager to control TUI terminal focus using the same
    dwell-time logic used for tmux panes.

    Performance: Uses __slots__ and pre-computed inverse for hot path.
    """

    __slots__ = ('_terminals', '_rows', '_cols', '_on_focus', '_inv_cols', '_inv_rows')

    def __init__(
        self,
        terminals: List["TerminalWidget"],
        rows: int,
        cols: int,
        on_focus: Optional[Callable[[int], None]] = None,
    ) -> None:
        """
        Initialize the adapter.

        Args:
            terminals: List of TerminalWidget instances
            rows: Number of rows in the grid
            cols: Number of columns in the grid
            on_focus: Optional callback when focus changes
        """
        self._terminals = terminals
        self._rows = rows
        self._cols = cols
        self._on_focus = on_focus
        # Pre-compute inverse for faster pane lookup
        self._inv_cols = 1.0 / cols if cols > 0 else 0.0
        self._inv_rows = 1.0 / rows if rows > 0 else 0.0

    @property
    def pane_count(self) -> int:
        """Total number of terminal panes."""
        return len(self._terminals)

    @property
    def rows(self) -> int:
        """Number of rows in the grid."""
        return self._rows

    @property
    def cols(self) -> int:
        """Number of columns in the grid."""
        return self._cols

    def focus_pane(self, index: int) -> None:
        """
        Focus the terminal at the given index.

        Updates is_focused_pane on all terminals and calls Textual focus().
        """
        if index < 0 or index >= len(self._terminals):
            return

        # Update all terminals' focused state
        for i, terminal in enumerate(self._terminals):
            terminal.is_focused_pane = (i == index)

        # Focus the target terminal
        self._terminals[index].focus()

        # Notify callback
        if self._on_focus:
            self._on_focus(index)

    def get_pane_at_position(self, x_ratio: float, y_ratio: float) -> Optional[int]:
        """
        Get terminal index at normalized coordinates (0-1).

        Uses pre-computed inverse for faster calculation.
        """
        # Bounds check
        if not (0.0 <= x_ratio <= 1.0 and 0.0 <= y_ratio <= 1.0):
            return None

        # Calculate grid cell using multiplication (faster than division)
        col = int(x_ratio * self._cols)
        row = int(y_ratio * self._rows)

        # Clamp to valid range (handles edge case of ratio == 1.0)
        if col >= self._cols:
            col = self._cols - 1
        if row >= self._rows:
            row = self._rows - 1

        index = row * self._cols + col
        if index >= len(self._terminals):
            return None

        return index
