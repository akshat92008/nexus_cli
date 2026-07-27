#!/usr/bin/env zsh
# Launch_Fable_Engine.command - Executable launcher for JARVIS Nova 1.5b & GPT-5.6 Sol Engine
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"
python3 cli.py
