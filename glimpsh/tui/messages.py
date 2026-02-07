"""Textual messages for gaze events."""

from textual.message import Message


class GazeUpdate(Message):
    """
    Posted when new gaze data arrives from the server.

    Uses __slots__ for minimal allocation overhead on hot path.
    """

    __slots__ = ('x', 'y', 'cell_row', 'cell_col')

    def __init__(self, x: float, y: float, cell_row: int | None = None, cell_col: int | None = None) -> None:
        super().__init__()
        self.x = x
        self.y = y
        self.cell_row = cell_row  # Grid cell row (with hysteresis)
        self.cell_col = cell_col  # Grid cell column (with hysteresis)


class GazeConnected(Message):
    """Posted when gaze server connects."""

    __slots__ = ()


class GazeDisconnected(Message):
    """Posted when gaze server disconnects."""

    __slots__ = ()


class GazeServerInfo(Message):
    """Posted when server sends hello message."""

    __slots__ = ('name', 'version')

    def __init__(self, name: str, version: str = "1.0") -> None:
        super().__init__()
        self.name = name
        self.version = version
