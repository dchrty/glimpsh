"""Configuration management for GlimpSh."""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


def _default_shell() -> str:
    """Return the user's default shell."""
    shell = os.environ.get("SHELL")
    if shell:
        return os.path.basename(shell)
    return "zsh" if platform.system() == "Darwin" else "bash"


@dataclass
class GridConfig:
    """Grid layout configuration."""

    rows: int = 2
    cols: int = 2


@dataclass
class GazeProvider:
    """Configuration for a gaze tracking provider."""

    name: str
    url: str
    command: Optional[str] = None  # Command to launch the provider


@dataclass
class GazeConfig:
    """Gaze tracking configuration."""

    dwell_time_ms: int = 200
    providers: list[GazeProvider] = field(default_factory=list)

    def get_provider(self, name: Optional[str] = None) -> Optional[GazeProvider]:
        """Get a provider by name, or the first one if no name given."""
        if not self.providers:
            return None
        if name is None:
            return self.providers[0]
        for p in self.providers:
            if p.name == name:
                return p
        return None


@dataclass
class Config:
    """Main application configuration."""

    grid: GridConfig = field(default_factory=GridConfig)
    gaze: GazeConfig = field(default_factory=GazeConfig)
    command: str = field(default_factory=_default_shell)


def get_config_path() -> Path:
    """Get the configuration file path."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg_config) / "glimpsh" / "config.yaml"


def _default_providers() -> list[GazeProvider]:
    """Return default gaze providers."""
    return [
        GazeProvider(
            name="eyetrax",
            url="ws://127.0.0.1:8001/",
            command="eyetrax --filter kalman",
        ),
    ]


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = get_config_path()

    config = Config()
    config.gaze.providers = _default_providers()

    if not config_path.exists():
        return config

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not load config from {config_path}: {e}")
        return config

    # Parse grid config
    if "grid" in data:
        grid_data = data["grid"]
        config.grid = GridConfig(
            rows=grid_data.get("rows", 2),
            cols=grid_data.get("cols", 2),
        )

    # Parse gaze config
    if "gaze" in data:
        gaze_data = data["gaze"]
        config.gaze.dwell_time_ms = gaze_data.get("dwell_time_ms", 200)

        # Parse providers
        if "providers" in gaze_data:
            providers = []
            for name, pdata in gaze_data["providers"].items():
                providers.append(GazeProvider(
                    name=name,
                    url=pdata.get("url", ""),
                    command=pdata.get("command"),
                ))
            if providers:
                config.gaze.providers = providers

    # Parse command
    if "command" in data:
        config.command = data["command"]

    return config


def save_default_config(config_path: Optional[Path] = None) -> None:
    """Save a default configuration file."""
    if config_path is None:
        config_path = get_config_path()

    config_path.parent.mkdir(parents=True, exist_ok=True)

    default_config = """\
# GlimpSh Configuration
# Edit these values and restart glimpsh to apply changes.

# Command to run in each pane (defaults to your $SHELL)
# command: zsh

# To run Claude Code in every pane:
#   command: "claude --dangerously-skip-permissions"
# Or from the CLI:
#   glimpsh claude --dangerously-skip-permissions

grid:
  rows: 2
  cols: 2

gaze:
  # How long to look at a pane before it focuses (milliseconds)
  dwell_time_ms: 200

  # Gaze tracking providers (first one is used by default)
  providers:
    eyetrax:
      url: "ws://127.0.0.1:8001/"
      command: "eyetrax --filter kalman"  # launched automatically if not running
"""

    with open(config_path, "w") as f:
        f.write(default_config)
