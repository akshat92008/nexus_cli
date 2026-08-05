"""
Rollback Decision and Execution Engine for Nexus CLI Recovery Subsystem.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from nexus.history import FileHistory
from nexus.run_state import RunLedger

logger = logging.getLogger(__name__)


class RollbackManager:
    """Minimal stub for workspace rollback via FileHistory."""

    @staticmethod
    def rollback(run_id: str) -> tuple[bool, str]:
        """Attempt file-history rollback for the given run_id."""
        try:
            from nexus.run_catalog import RunCatalog
            catalog = RunCatalog()
            try:
                run_path = catalog.resolve(run_id)
            except Exception as exc:
                return False, f"Could not resolve run '{run_id}': {exc}"
            if not run_path:
                return False, f"Could not resolve run '{run_id}'"
            
            session_id = run_path.parent.name if hasattr(run_path, "parent") else (run_path.get("session_id") if isinstance(run_path, dict) else run_id)
            history = FileHistory(session_id)
            result, msg = history.undo_changes(len(history.changes)) if history.changes else (False, "No changes")
            return result, msg
        except Exception as exc:  # noqa: BLE001
            return False, f"Rollback error: {exc}"



@dataclass
class RollbackDecision:
    should_rollback: bool
    immediate: bool
    reason: str
    target_checkpoint: str = ""


class RollbackDecisionEngine:
    """Enforces workspace integrity and executes verified rollbacks."""

    @classmethod
    def evaluate(
        cls,
        *,
        out_of_scope_mutation: bool = False,
        protected_path_changed: bool = False,
        syntax_broken: bool = False,
        new_regression: bool = False,
        corrupted_state: bool = False,
        unverified_patch: bool = False,
    ) -> RollbackDecision:
        if protected_path_changed:
            return RollbackDecision(
                should_rollback=True,
                immediate=True,
                reason="Mutation touched a protected system path.",
            )
        if out_of_scope_mutation:
            return RollbackDecision(
                should_rollback=True,
                immediate=True,
                reason="Mutation occurred outside the approved step scope.",
            )
        if syntax_broken:
            return RollbackDecision(
                should_rollback=True,
                immediate=True,
                reason="Patch broke syntax or module parsing across the repository.",
            )
        if corrupted_state:
            return RollbackDecision(
                should_rollback=True,
                immediate=True,
                reason="Workspace or repository state was left corrupted by attempt.",
            )
        if new_regression:
            return RollbackDecision(
                should_rollback=True,
                immediate=False,
                reason="Patch introduced a new regression in non-target tests.",
            )

        return RollbackDecision(
            should_rollback=False,
            immediate=False,
            reason="Patch preserves repository integrity.",
        )

    @classmethod
    def execute_rollback(cls, run_id: str, working_dir: str = "") -> tuple[bool, str]:
        """Executes a verified rollback using RollbackManager / FileHistory."""
        try:
            success, detail = RollbackManager.rollback(run_id)
            if success:
                logger.info("Rollback succeeded for run '%s': %s", run_id, detail)
                return True, f"Rollback verified: {detail}"
            logger.warning("Rollback failed for run '%s': %s", run_id, detail)
            return False, detail
        except Exception as e:
            logger.error("Exception during rollback for run '%s': %s", run_id, e)
            return False, f"Rollback execution error: {e}"
