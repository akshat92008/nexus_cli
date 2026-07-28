"""
File Change History — tracks every file modification for undo/diff support.

Every write_file, edit_file, patch_file, and multi_edit is recorded here
so the user can review what changed and revert if needed.
"""

import os
import json
import difflib
import shutil
from datetime import datetime
from pathlib import Path
from nexus.paths import nexus_home
from typing import Optional


HISTORY_DIR = nexus_home() / "history"


class FileHistory:
    """Tracks file changes per session for undo and diff operations."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = nexus_home() / "history" / self.session_id
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.changes: list[dict] = []
        self._load_changes()

    def _changes_file(self) -> Path:
        return self.session_dir / "changes.json"

    def _load_changes(self):
        """Load changes from disk if they exist."""
        cf = self._changes_file()
        if cf.exists():
            try:
                with open(cf, "r") as f:
                    self.changes = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.changes = []

    def _save_changes(self):
        """Persist changes list to disk."""
        with open(self._changes_file(), "w") as f:
            json.dump(self.changes, f, indent=2)

    def snapshot_before_write(self, filepath: str) -> str | None:
        """
        Capture the current state of a file before it's modified.
        Returns the snapshot path, or None if the file doesn't exist yet.
        """
        p = Path(filepath).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return None

        # Save a copy
        snap_name = f"{len(self.changes):04d}_{p.name}"
        snap_path = self.session_dir / snap_name
        try:
            shutil.copy2(str(p), str(snap_path))
            return str(snap_path)
        except (OSError, shutil.SameFileError):
            return None

    def record_change(
        self,
        filepath: str,
        tool_name: str,
        snapshot_path: str | None = None,
        description: str = "",
    ):
        """Record a file change in the history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "filepath": str(Path(filepath).expanduser().resolve()),
            "tool": tool_name,
            "snapshot_path": snapshot_path,
            "description": description,
            "is_new_file": snapshot_path is None,
        }
        self.changes.append(entry)
        self._save_changes()

    def get_last_change(self) -> dict | None:
        """Get the most recent file change."""
        return self.changes[-1] if self.changes else None

    def get_recent_changes(self, n: int = 10) -> list[dict]:
        """Get the N most recent changes."""
        return self.changes[-n:]

    def undo_last_change(self) -> tuple[bool, str]:
        """
        Undo the most recent file change.
        Returns (success, message).
        """
        if not self.changes:
            return False, "No changes to undo."

        last = self.changes[-1]
        filepath = last["filepath"]
        snapshot = last.get("snapshot_path")

        if last["is_new_file"]:
            # File was newly created — delete it
            try:
                p = Path(filepath)
                if p.exists():
                    p.unlink()
                self.changes.pop()
                self._save_changes()
                return True, f"Deleted newly created file: {filepath}"
            except OSError as e:
                return False, f"Failed to delete {filepath}: {e}"
        elif snapshot and Path(snapshot).exists():
            # Restore from snapshot
            try:
                shutil.copy2(snapshot, filepath)
                self.changes.pop()
                self._save_changes()
                return True, f"Restored {Path(filepath).name} to previous version"
            except OSError as e:
                return False, f"Failed to restore {filepath}: {e}"
        else:
            self.changes.pop()
            self._save_changes()
            return False, "Snapshot not available — change record removed but file not restored."

    def undo_changes(self, count: int = 1) -> tuple[bool, str]:
        """Undo up to *count* operations, newest first, with a complete result list."""
        try:
            count = max(1, int(count))
        except (TypeError, ValueError):
            return False, "Undo count must be a positive integer."
        messages = []
        all_ok = True
        for _ in range(min(count, len(self.changes))):
            ok, message = self.undo_last_change()
            all_ok = all_ok and ok
            messages.append(message)
        if not messages:
            return False, "No changes to undo."
        return all_ok, f"Undid {len(messages)} operation(s):\n" + "\n".join(f"  {m}" for m in messages)

    def get_recent_diffs(self, count: int = 10) -> str:
        """Render diffs for the most recent operations without changing history."""
        if not self.changes:
            return "No file changes in this session."
        original = self.changes
        rendered = []
        for change in original[-max(1, count):]:
            self.changes = [change]
            rendered.append(self.get_last_diff() or "(diff unavailable)")
        self.changes = original
        return "\n\n".join(rendered)

    def get_last_diff(self) -> str | None:
        """
        Show a unified diff of the last file change.
        Returns the diff string, or None if not possible.
        """
        if not self.changes:
            return None

        last = self.changes[-1]
        filepath = last["filepath"]
        snapshot = last.get("snapshot_path")

        current_path = Path(filepath)
        if not current_path.exists():
            return f"File no longer exists: {filepath}"

        if last["is_new_file"]:
            # Show entire file as "added"
            try:
                with open(current_path, "r", encoding="utf-8", errors="replace") as f:
                    new_lines = f.readlines()
                diff = difflib.unified_diff(
                    [],
                    new_lines,
                    fromfile="/dev/null",
                    tofile=str(current_path.name),
                    lineterm="",
                )
                return "\n".join(diff) or "(empty file created)"
            except OSError:
                return None

        if not snapshot or not Path(snapshot).exists():
            return "Snapshot not available for diff."

        try:
            with open(snapshot, "r", encoding="utf-8", errors="replace") as f:
                old_lines = f.readlines()
            with open(current_path, "r", encoding="utf-8", errors="replace") as f:
                new_lines = f.readlines()

            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{current_path.name}",
                tofile=f"b/{current_path.name}",
                lineterm="",
            )
            result = "\n".join(diff)
            return result if result else "(no differences)"
        except OSError:
            return None

    def get_change_summary(self) -> str:
        """Get a summary of all changes in this session."""
        if not self.changes:
            return "No file changes in this session."

        lines = [f"📋 {len(self.changes)} file change(s) in this session:\n"]
        for i, change in enumerate(self.changes, 1):
            p = Path(change["filepath"])
            action = "created" if change["is_new_file"] else "modified"
            tool = change["tool"]
            ts = change["timestamp"].split("T")[1][:8]
            lines.append(f"  {i}. [{ts}] {action} {p.name} via {tool}")

        return "\n".join(lines)


# Global instance — created when the agent starts
_global_history: FileHistory | None = None


def get_history() -> FileHistory:
    """Get or create the global file history instance."""
    global _global_history
    if _global_history is None:
        _global_history = FileHistory()
    return _global_history


def init_history(session_id: str | None = None) -> FileHistory:
    """Initialize a new history session."""
    global _global_history
    _global_history = FileHistory(session_id)
    return _global_history
