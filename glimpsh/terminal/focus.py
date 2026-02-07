"""Focus management - mapping gaze coordinates to panes."""

import time
from typing import Callable, Optional, Protocol, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .grid import TmuxGrid


class FocusTarget(Protocol):
    """
    Protocol for anything that can receive gaze-based focus.

    Implementations: TmuxGrid, TerminalGridAdapter
    """
    __slots__ = ()

    @property
    def pane_count(self) -> int:
        """Total number of focusable panes."""
        ...

    @property
    def rows(self) -> int:
        """Number of rows in the grid."""
        ...

    @property
    def cols(self) -> int:
        """Number of columns in the grid."""
        ...

    def focus_pane(self, index: int) -> None:
        """Focus the pane at the given index."""
        ...

    def get_pane_at_position(self, x_ratio: float, y_ratio: float) -> Optional[int]:
        """
        Get pane index at normalized coordinates (0-1).

        Returns None if coordinates are out of bounds.
        """
        ...


class FocusManager:
    """
    Manages focus switching based on gaze position.

    Implements dwell-time based focus switching to prevent accidental
    focus changes from brief glances.

    Performance: Uses __slots__ and direct attribute access on hot path.
    """

    __slots__ = (
        'target', 'screen_width', 'screen_height', 'dwell_time_ms',
        'on_focus_change', '_current_focus', '_candidate_focus',
        '_candidate_start_time', '_inv_screen_width', '_inv_screen_height',
    )

    def __init__(
        self,
        target: FocusTarget,
        screen_width: int,
        screen_height: int,
        dwell_time_ms: int = 200,
        on_focus_change: Optional[Callable[[Optional[int], int], None]] = None,
    ):
        """
        Initialize the focus manager.

        Args:
            target: FocusTarget implementation (TmuxGrid, TerminalGridAdapter, etc.)
            screen_width: Screen width in pixels (for coordinate mapping)
            screen_height: Screen height in pixels (for coordinate mapping)
            dwell_time_ms: Time in ms before focus switches
            on_focus_change: Callback when focus changes (old_idx, new_idx)
        """
        self.target = target
        self.screen_width = screen_width
        self.screen_height = screen_height
        # Pre-compute inverse for faster division in hot path
        self._inv_screen_width = 1.0 / screen_width if screen_width > 0 else 0.0
        self._inv_screen_height = 1.0 / screen_height if screen_height > 0 else 0.0
        self.dwell_time_ms = dwell_time_ms
        self.on_focus_change = on_focus_change

        self._current_focus: Optional[int] = 0
        self._candidate_focus: Optional[int] = None
        self._candidate_start_time: Optional[float] = None

    @property
    def current_focus(self) -> Optional[int]:
        """Get the currently focused pane index."""
        return self._current_focus

    def pane_at(self, x: float, y: float) -> Optional[int]:
        """Get the pane index at the given screen coordinates."""
        # Use pre-computed inverse for faster division
        x_ratio = x * self._inv_screen_width
        y_ratio = y * self._inv_screen_height
        return self.target.get_pane_at_position(x_ratio, y_ratio)

    def update(self, x: float, y: float) -> bool:
        """
        Update focus based on gaze position.

        Args:
            x: Gaze X coordinate (screen pixels)
            y: Gaze Y coordinate (screen pixels)

        Returns:
            True if focus changed, False otherwise
        """
        pane_idx = self.pane_at(x, y)

        # Gaze is outside screen bounds
        if pane_idx is None:
            self._candidate_focus = None
            self._candidate_start_time = None
            return False

        # Already focused on this pane
        if pane_idx == self._current_focus:
            self._candidate_focus = None
            self._candidate_start_time = None
            return False

        now = time.time() * 1000  # Convert to ms

        # New candidate pane
        if pane_idx != self._candidate_focus:
            self._candidate_focus = pane_idx
            self._candidate_start_time = now
            return False

        # Check if dwell time has elapsed
        if self._candidate_start_time is not None:
            elapsed = now - self._candidate_start_time
            if elapsed >= self.dwell_time_ms:
                old_focus = self._current_focus
                self._current_focus = pane_idx
                self._candidate_focus = None
                self._candidate_start_time = None

                # Focus the target pane
                self.target.focus_pane(pane_idx)

                # Notify callback
                if self.on_focus_change:
                    self.on_focus_change(old_focus, pane_idx)

                return True

        return False

    def update_from_cell(self, row: int, col: int) -> bool:
        """
        Update focus based on grid cell (with hysteresis already applied by eyetrax).

        Uses dwell time to ensure intentional focus - hysteresis prevents
        boundary flickering, dwell time prevents accidental focus from brief glances.

        Args:
            row: Grid row (0-indexed)
            col: Grid column (0-indexed)

        Returns:
            True if focus changed, False otherwise
        """
        # Convert row/col to pane index (row-major order)
        cols = self.target.cols
        pane_idx = row * cols + col

        # Validate index
        if pane_idx < 0 or pane_idx >= self.target.pane_count:
            self._candidate_focus = None
            self._candidate_start_time = None
            return False

        # Already focused on this pane
        if pane_idx == self._current_focus:
            self._candidate_focus = None
            self._candidate_start_time = None
            return False

        now = time.time() * 1000  # Convert to ms

        # New candidate pane
        if pane_idx != self._candidate_focus:
            self._candidate_focus = pane_idx
            self._candidate_start_time = now
            return False

        # Check if dwell time has elapsed
        if self._candidate_start_time is not None:
            elapsed = now - self._candidate_start_time
            if elapsed >= self.dwell_time_ms:
                old_focus = self._current_focus
                self._current_focus = pane_idx
                self._candidate_focus = None
                self._candidate_start_time = None

                # Focus the target pane
                self.target.focus_pane(pane_idx)

                # Notify callback
                if self.on_focus_change:
                    self.on_focus_change(old_focus, pane_idx)

                return True

        return False

    def focus_pane(self, index: int) -> bool:
        """
        Manually focus a specific pane.

        Args:
            index: Pane index to focus

        Returns:
            True if focus changed, False otherwise
        """
        if index < 0 or index >= self.target.pane_count:
            return False

        if index == self._current_focus:
            return False

        old_focus = self._current_focus
        self._current_focus = index
        self._candidate_focus = None
        self._candidate_start_time = None

        # Focus the target pane
        self.target.focus_pane(index)

        # Notify callback
        if self.on_focus_change:
            self.on_focus_change(old_focus, index)

        return True

    def get_dwell_progress(self) -> Tuple[Optional[int], float]:
        """
        Get the current dwell progress.

        Returns:
            Tuple of (candidate_pane_index, progress_0_to_1)
        """
        if self._candidate_focus is None or self._candidate_start_time is None:
            return None, 0.0

        now = time.time() * 1000
        elapsed = now - self._candidate_start_time
        progress = min(1.0, elapsed / self.dwell_time_ms)

        return self._candidate_focus, progress
