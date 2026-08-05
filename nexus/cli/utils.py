import argparse
import json
import os
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from nexus import __version__, ui
from nexus.agent import Agent
from nexus.doctor import run_doctor
from nexus.memory import ConversationMemory
from nexus.models import DEFAULT_MODEL, resolve_model
from nexus.policy import get_mode_policy
from nexus.run_catalog import RunCatalog
from nexus.tools import get_history, tool_get_project_structure

def _extension_state_dir(working_dir: str = "") -> Path | None:
    """Return an optional command-local extension state directory."""
    if not working_dir:
        return None
    path = Path(working_dir).expanduser().resolve() / ".nexus" / "extensions"
    path.mkdir(parents=True, exist_ok=True)
    return path

def _extension_registry(working_dir: str = ""):
    from nexus.platform.registry import PlatformExtensionRegistry

    state_dir = _extension_state_dir(working_dir)
    return PlatformExtensionRegistry(
        working_dir=working_dir,
        extensions_dir=(state_dir / "installed") if state_dir else None,
    )

def _state_dir_from_working_dir(working_dir: str, name: str) -> Path | None:
    if not working_dir:
        return None
    path = Path(working_dir).expanduser().resolve() / ".nexus" / name
    path.mkdir(parents=True, exist_ok=True)
    return path

