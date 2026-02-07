"""Main application for GlimpSh."""

import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .config import load_config, save_default_config, get_config_path

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def wait_for_websocket(
    url: str,
    timeout: float = 120.0,
    poll_interval: float = 0.5,
    label: str | None = None,
) -> bool:
    """
    Wait for a WebSocket server to be ready by polling the TCP port.

    Shows an animated spinner with *label* while waiting.
    Returns True if server is ready, False if timeout expired.
    """
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8001

    done = threading.Event()
    result: list[bool] = [False]

    def _poll() -> None:
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection((host, port), timeout=1):
                    result[0] = True
                    done.set()
                    return
            except (socket.error, socket.timeout):
                time.sleep(poll_interval)
        done.set()

    thread = threading.Thread(target=_poll, daemon=True)
    thread.start()

    if label and sys.stdout.isatty():
        idx = 0
        while not done.is_set():
            frame = SPINNER_FRAMES[idx % len(SPINNER_FRAMES)]
            sys.stdout.write(f"\r{frame} {label}")
            sys.stdout.flush()
            idx += 1
            done.wait(0.08)
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()
    else:
        done.wait(timeout)

    thread.join()
    return result[0]


def main(args=None) -> int:
    """
    Main entry point for glimpsh CLI.

    Args:
        args: Command line arguments (uses sys.argv if None)

    Returns:
        Exit code
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="glimpsh",
        description="Gaze-controlled terminal grid. Look at a pane to focus it.",
    )

    # Grid configuration
    parser.add_argument(
        "--rows", "-r",
        type=int,
        help="Number of rows in the grid (default: 2)",
    )
    parser.add_argument(
        "--cols", "-c",
        type=int,
        help="Number of columns in the grid (default: 2)",
    )

    # Gaze configuration
    parser.add_argument(
        "--gaze",
        type=str,
        metavar="MODE",
        default=None,
        help="Gaze mode: 'none' (keyboard only), 'test' (Ctrl+Arrow simulation), or provider name from config",
    )

    # Config
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config file",
    )
    parser.add_argument(
        "--configure",
        action="store_true",
        help="Print config file path",
    )

    # Recalibrate
    parser.add_argument(
        "--recalibrate",
        action="store_true",
        help="Force full recalibration of eye tracking",
    )

    # Claude Code mode
    parser.add_argument(
        "--claude",
        action="store_true",
        help="Run Claude Code in each pane",
    )

    # Codex mode
    parser.add_argument(
        "--codex",
        action="store_true",
        help="Run Codex CLI in each pane",
    )

    # Clipboard auto-paste for voice input (Wispr etc.)
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Watch clipboard and auto-type into focused pane (for Wispr/dictation tools)",
    )

    # Debug
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show debug panel with server/client logs",
    )

    # Version
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args, extra = parser.parse_known_args(args)

    # Ensure config exists (create on first run)
    config_path = args.config or get_config_path()
    first_run = not config_path.exists()
    if first_run:
        save_default_config(config_path)
        print(f"Config: {config_path}\n")

    # Handle --configure
    if args.configure:
        print(f"{config_path}")
        return 0

    # Load config
    config = load_config(args.config)

    # Apply config with CLI overrides (needed early for grid mode)
    if args.claude:
        command = "claude --dangerously-skip-permissions"
    elif args.codex:
        command = "codex"
    elif extra:
        command = " ".join(extra)
    else:
        command = config.command
    rows = args.rows if args.rows is not None else config.grid.rows
    cols = args.cols if args.cols is not None else config.grid.cols

    # Determine gaze settings
    gaze_mode = args.gaze  # None, 'none', 'test', or provider name
    gaze_enabled = gaze_mode != "none"
    test_gaze = gaze_mode == "test"
    gaze_server_url = None
    gaze_process = None  # Track subprocess for cleanup

    if gaze_enabled and not test_gaze:
        # Get the provider (by name or default)
        provider_name = gaze_mode  # None means use first provider
        provider = config.gaze.get_provider(provider_name)

        if provider:
            gaze_server_url = provider.url

            # Launch provider if it has a command
            if provider.command:
                cmd_parts = provider.command.split()
                cmd_name = cmd_parts[0]

                # Check if installed
                if not shutil.which(cmd_name):
                    print(f"Gaze provider '{provider.name}' not found: {cmd_name}")
                    print(f"Install with: pip install {cmd_name}")
                    return 1

                # Add grid mode for better cell-based tracking
                cmd_parts.extend(["--grid", f"{rows}x{cols}"])

                # Pass through recalibrate flag
                if args.recalibrate:
                    cmd_parts.append("--recalibrate")

                # Launch in background
                print(f"Starting {provider.name} (grid: {rows}x{cols})...")
                if args.recalibrate:
                    print("Complete the calibration/tuning windows, then glimpsh will start.")

                if platform.system() == "Darwin":
                    print(f"\n{provider.name} needs camera access for eye tracking.")
                    answer = input("Allow camera access? [Y/n] ").strip().lower()
                    if answer and answer not in ("y", "yes"):
                        print("Camera access denied. Use --gaze none for keyboard-only mode.")
                        return 1

                gaze_process = subprocess.Popen(
                    cmd_parts,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # Wait for the WebSocket server to be ready (after calibration/tuning)
                spinner_label = (
                    f"Starting {provider.name} — loading models & camera..."
                )
                if not wait_for_websocket(
                    provider.url, timeout=120.0, label=spinner_label
                ):
                    print(f"Timeout waiting for {provider.name} to start")
                    if gaze_process.poll() is None:
                        gaze_process.terminate()
                    return 1
        elif gaze_mode is not None:
            # User specified a provider that doesn't exist
            print(f"Unknown gaze provider: {gaze_mode}")
            print(f"Available: none, test, {', '.join(p.name for p in config.gaze.providers)}")
            return 1

    # Import here to avoid slow startup for --help/--configure
    from .tui.app import run_tui

    try:
        return run_tui(
            rows=rows,
            cols=cols,
            command=command,
            gaze_server_url=gaze_server_url or "ws://127.0.0.1:8001/",
            dwell_time_ms=config.gaze.dwell_time_ms,
            gaze_enabled=gaze_enabled,
            test_gaze=test_gaze,
            debug=args.debug,
            voice=args.voice,
        )
    finally:
        # Clean up gaze provider subprocess
        if gaze_process is not None:
            gaze_process.terminate()
            try:
                gaze_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                gaze_process.kill()


if __name__ == "__main__":
    sys.exit(main())
