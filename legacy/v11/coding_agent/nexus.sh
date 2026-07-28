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
    pip install -q -r "$SCRIPT_DIR/requirements.txt"
    echo "✅ Setup complete!"
    echo ""
else
    source "$VENV_DIR/bin/activate"
fi

# Load env vars
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

python3 "$SCRIPT_DIR/run.py" "$@"
