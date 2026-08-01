"""
Recovery & Rollback Subsystem for Nexus CLI.
"""

import os

from nexus.history import FileHistory
from nexus.run_catalog import RunCatalog
from nexus.run_state import RunLedger


class RollbackManager:
    """Manages restoring workspaces to the exact state before an agent run."""

    @classmethod
    def rollback(cls, run_id: str) -> tuple[bool, str]:
        """
        Reverts file changes made during a specific run.
        Only the most recent turn in a session can be safely rolled back.
        """
        catalog = RunCatalog()
        try:
            turn_dir = catalog.resolve(run_id)
        except Exception as e:
            return False, f"Could not resolve run '{run_id}': {e}"

        session_id = turn_dir.parent.name
        latest_turns = sorted(path for path in turn_dir.parent.glob("turn-*") if path.is_dir())
        if not latest_turns or latest_turns[-1] != turn_dir:
            return False, "Only the latest turn in a session can be rolled back safely."

        inspected = catalog.inspect(run_id)
        metadata = inspected.get("final_report", {}).get("metadata", {})

        history = FileHistory(session_id)
        start = int(metadata.get("history_start", 0))
        end = int(metadata.get("history_end", len(history.changes)))

        if end != len(history.changes):
            return (
                False,
                "This is not the most recent applied run in the session; rolling it back would overwrite later work.",
            )

        count = max(0, end - start)
        if count == 0:
            return False, "The selected run has no applied file changes."

        success, detail = history.undo_changes(count)
        if not success:
            return False, detail

        request = inspected.get("request", {})
        ledger = RunLedger(
            session_id,
            request.get("working_dir") or os.getcwd(),
        )
        ledger.resume_summary()
        ledger.mark_rolled_back(detail)

        return True, detail
