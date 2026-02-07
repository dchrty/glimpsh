# glimpsh

A glimpse into a potential future where you navigate multiple terminals with your eyes.

This is a fun experimental project exploring eye-tracked terminal focus. Look at a pane to focus it. Combine with speech-to-text for hands-free coding.

## Vision

Glimpsh is a prototype exploring what becomes possible when lightweight gaze tracking is cheap and ubiquitous. Today's webcam-based eye tracking is imperfect, but it's improving fast.

Gaze won't replace the mouse - it's a complementary input that adds a new dimension to human-computer interaction. Where it shines is **managing many things at scale**. Some power users are fast with keybinds, but gaze adds an intuitive HCI primitive to terminals: your eyes are already looking where you want to act.

Pair gaze with real-time voice transcription and the interaction model shifts: look at an agent, speak a command. As brain interfaces mature, the same patterns will translate directly.

This project exists to explore that future now.

## Quick Start

```bash
git clone https://github.com/dchrty/glimpsh
cd glimpsh
pip install uv
uv sync --extra glimpsh-eyetrax
uv run glimpsh --claude  # or --codex for OpenAI Codex
```


https://github.com/user-attachments/assets/69edcf18-f6ba-49cd-90da-f260030fdc81


## Calibration

On first run, follow the on-screen calibration (look at dots until they disappear).

To recalibrate or fine-tune the eye tracking model:

```bash
uv run glimpsh --recalibrate
```

Or for hands-free AI coding with Claude Code and voice (requires a speech-to-text tool that copies transcriptions to the clipboard — see Voice Input below):

```bash
uv run glimpsh --claude --dangerously-skip-permissions --voice
```

## Gaze Backends

We've started with [glimpsh-eyetrax](https://github.com/dchrty/glimpsh-eyetrax), based on [Chenkai Zhang's EyeTrax](https://github.com/ck-zhang/EyeTrax), for webcam-based gaze tracking. Adapting other gaze servers is relatively easy - just implement the websocket protocol.

## No Webcam?

```bash
uv run glimpsh --gaze test
```

Use `Ctrl+Arrow` keys to simulate eye movement.

## Voice Input

Requires a transcription tool that copies text to the clipboard.

Run with `--voice` to auto-type clipboard changes into the focused pane:

```bash
uv run glimpsh --voice
```

Look at a pane to focus it, then speak. Your dictation tool copies to clipboard, glimpsh types it in.

## Claude Code

Run [Claude Code](https://github.com/anthropics/claude-code) in each pane:

```bash
uv run glimpsh --claude
```

For fully autonomous operation (Claude can run commands without confirmation):

```bash
uv run glimpsh --claude --dangerously-skip-permissions
```

Combine with voice for hands-free AI coding - look at a pane, speak your request:

```bash
uv run glimpsh --claude --dangerously-skip-permissions --voice
```

## Codex

Run [Codex CLI](https://github.com/openai/codex) in each pane:

```bash
uv run glimpsh --codex
```

## License

MIT
