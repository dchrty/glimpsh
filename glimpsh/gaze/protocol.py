"""Gaze server protocol - server-agnostic message format."""

import struct
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Union


class MessageType(Enum):
    """Types of gaze messages."""

    GAZE_POINT = "gaze_point"
    CALIBRATION_START = "calibration_start"
    CALIBRATION_END = "calibration_end"
    ERROR = "error"
    STATUS = "status"
    HELLO = "hello"  # Server identification


@dataclass
class GazePoint:
    """A single gaze point with coordinates."""

    x: float  # X coordinate in pixels
    y: float  # Y coordinate in pixels
    timestamp: float  # Timestamp in seconds
    confidence: float = 1.0  # Tracking confidence (0-1)
    seq: int = 0  # Sequence number for debugging
    cell_row: Optional[int] = None  # Grid cell row (with hysteresis)
    cell_col: Optional[int] = None  # Grid cell column (with hysteresis)

    @classmethod
    def from_dict(cls, data: dict) -> "GazePoint":
        """Create GazePoint from a dictionary."""
        # Parse optional cell info from grid mode
        cell_row = None
        cell_col = None
        if "cell" in data and data["cell"]:
            cell_row = data["cell"].get("row")
            cell_col = data["cell"].get("col")

        return cls(
            x=float(data.get("x_px", data.get("x", 0))),
            y=float(data.get("y_px", data.get("y", 0))),
            timestamp=float(data.get("timestamp", 0)),
            confidence=float(data.get("confidence", 1.0)),
            seq=int(data.get("seq", 0)),
            cell_row=cell_row,
            cell_col=cell_col,
        )

    @classmethod
    def from_binary(cls, data: bytes) -> "GazePoint":
        """
        Create GazePoint from binary data.

        Expected format: 2 floats (x, y) as little-endian 32-bit floats (8 bytes total)
        or 3 floats (x, y, timestamp) as 12 bytes
        or 4 floats (x, y, timestamp, confidence) as 16 bytes
        """
        import time

        if len(data) >= 16:
            x, y, timestamp, confidence = struct.unpack("<ffff", data[:16])
        elif len(data) >= 12:
            x, y, timestamp = struct.unpack("<fff", data[:12])
            confidence = 1.0
        elif len(data) >= 8:
            x, y = struct.unpack("<ff", data[:8])
            timestamp = time.time()
            confidence = 1.0
        else:
            raise ValueError(f"Invalid binary gaze data length: {len(data)}")

        return cls(x=x, y=y, timestamp=timestamp, confidence=confidence)


@dataclass
class ServerInfo:
    """Information about the gaze server."""

    name: str
    version: str = "1.0"

    @classmethod
    def from_dict(cls, data: dict) -> "ServerInfo":
        return cls(
            name=data.get("name", "Unknown"),
            version=data.get("version", "1.0"),
        )


@dataclass
class GazeMessage:
    """A message from the gaze server."""

    type: MessageType
    gaze_point: Optional[GazePoint] = None
    error: Optional[str] = None
    status: Optional[str] = None
    server_info: Optional[ServerInfo] = None


def parse_message(data: Union[bytes, dict, str]) -> GazeMessage:
    """
    Parse a message from the gaze server.

    Supports:
    - Binary data (8-16 bytes of floats)
    - JSON dict with x_px, y_px or x, y fields
    - JSON string (will be parsed)
    """
    import json

    # Handle binary data
    if isinstance(data, bytes):
        try:
            gaze_point = GazePoint.from_binary(data)
            return GazeMessage(type=MessageType.GAZE_POINT, gaze_point=gaze_point)
        except Exception as e:
            return GazeMessage(type=MessageType.ERROR, error=str(e))

    # Handle string (parse as JSON)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            return GazeMessage(type=MessageType.ERROR, error=f"Invalid JSON: {e}")

    # Handle dict
    if isinstance(data, dict):
        # Check for hello/server info
        if "type" in data and data["type"] == "hello":
            server_info = ServerInfo.from_dict(data)
            return GazeMessage(type=MessageType.HELLO, server_info=server_info)

        # Check for error
        if "error" in data:
            return GazeMessage(type=MessageType.ERROR, error=data["error"])

        # Check for status
        if "status" in data and "x_px" not in data and "x" not in data:
            return GazeMessage(type=MessageType.STATUS, status=data["status"])

        # Check for gaze point
        if "x_px" in data or "x" in data:
            gaze_point = GazePoint.from_dict(data)
            return GazeMessage(type=MessageType.GAZE_POINT, gaze_point=gaze_point)

        return GazeMessage(type=MessageType.ERROR, error=f"Unknown message format: {data}")

    return GazeMessage(type=MessageType.ERROR, error=f"Unknown data type: {type(data)}")


def normalize_to_screen(
    gaze: GazePoint,
    screen_width: int,
    screen_height: int,
) -> Tuple[int, int]:
    """
    Convert gaze coordinates to screen pixels.

    If coordinates are already in pixels (>1), returns them as-is.
    If coordinates are normalized (0-1), converts to screen pixels.
    """
    x, y = gaze.x, gaze.y

    # Check if already in pixel coordinates
    if x > 1 or y > 1:
        return int(x), int(y)

    # Convert from normalized to pixels
    return int(x * screen_width), int(y * screen_height)
