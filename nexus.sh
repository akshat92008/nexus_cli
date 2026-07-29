#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  NexusAI Launcher — v2.0
#  Automatically activates the venv and launches the agent.
#  Supports both CLI and Web modes.
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Auto-create venv if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "⚡ Setting up NexusAI for the first time..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -q "$SCRIPT_DIR"
    echo "✅ Setup complete!"
    echo ""
else
    source "$VENV_DIR/bin/activate"
fi

export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
python3 -m nexus.cli "$@"
