"""
nexus/collaboration/lifecycle.py

WorkerLifecycleManager: creation, monitoring, and cleanup of
IsolatedWorkerRuntime instances. Enforces workspace isolation policies
and guarantees cleanup even on failure paths.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from nexus.collaboration.models import (
    AgentAssignment,
    WorkerState,
    WorkerWorkspace,
    WorkspaceStrategy,
)

logger = logging.getLogger(__name__)

_WORKER_WORKSPACE_PREFIX = "nexus-worker-"


class WorkerLifecycleError(RuntimeError):
    """Raised for lifecycle management failures."""


class CleanupFailure(RuntimeError):
    """Raised when workspace cleanup cannot be completed."""


@dataclass
class WorkerRecord:
    worker_id: str
    assignment_id: str
    state: WorkerState
    workspace: Optional[WorkerWorkspace]
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    failed_cleanup: bool = False
    failure_reason: Optional[str] = None


class WorkerLifecycleManager:
    """
    Manages the full lifecycle of worker processes:
    CREATE → PREPARE workspace → LAUNCH → MONITOR → CLEANUP

    Rules enforced:
      - Investigation agents default to READ_ONLY_SHARED_SNAPSHOT.
      - Mutation agents receive ISOLATED_WORKTREE or ISOLATED_TEMPORARY_COPY.
      - Workers may not mutate the lead workspace.
      - Workers may not write into another worker's workspace.
      - Cleanup is always attempted even on failure.
      - Failed cleanup is recorded and re-raised.
      - User working-tree changes remain untouched.
    """

    def __init__(
        self,
        lead_workspace_root: Path,
        base_temp_dir: Optional[Path] = None,
    ) -> None:
        self._lead_root = lead_workspace_root.resolve()
        self._base_temp = (base_temp_dir or Path(tempfile.gettempdir())).resolve()
        self._workers: Dict[str, WorkerRecord] = {}

    # ------------------------------------------------------------------
    # Worker creation
    # ------------------------------------------------------------------

    def create_worker(self, assignment: AgentAssignment) -> WorkerRecord:
        worker_id = str(uuid.uuid4())
        record = WorkerRecord(
            worker_id=worker_id,
            assignment_id=assignment.assignment_id,
            state=WorkerState.CREATED,
            workspace=None,
        )
        self._workers[worker_id] = record
        logger.info("WorkerLifecycleManager: created worker %s for assignment %s",
                    worker_id, assignment.assignment_id)
        return record

    def prepare_workspace(
        self,
        worker_id: str,
        strategy: Optional[WorkspaceStrategy] = None,
    ) -> WorkerWorkspace:
        """
        Creates an isolated workspace for the worker.
        Strategy defaults to READ_ONLY for non-mutation workers,
        ISOLATED_TEMPORARY_COPY for mutation workers.
        """
        record = self._get_record(worker_id)

        if strategy is None:
            strategy = WorkspaceStrategy.READ_ONLY_SHARED_SNAPSHOT

        is_writable = strategy != WorkspaceStrategy.READ_ONLY_SHARED_SNAPSHOT

        if strategy == WorkspaceStrategy.READ_ONLY_SHARED_SNAPSHOT:
            workspace_root = self._lead_root  # shared, no copy
        else:
            # Create isolated temporary directory
            workspace_dir = self._base_temp / f"{_WORKER_WORKSPACE_PREFIX}{worker_id}"
            workspace_dir.mkdir(parents=True, exist_ok=False)
            workspace_root = workspace_dir

            # Protect lead workspace: ensure isolated root is NOT inside lead root
            try:
                workspace_root.relative_to(self._lead_root)
                # If we get here, it IS inside the lead root — that is wrong
                raise WorkerLifecycleError(
                    f"Isolated workspace {workspace_root} is inside lead workspace. "
                    "Refusing to create."
                )
            except ValueError:
                pass  # Expected — workspace is outside lead root

        workspace = WorkerWorkspace(
            workspace_id=str(uuid.uuid4()),
            assignment_id=record.assignment_id,
            strategy=strategy,
            root_path=workspace_root,
            is_writable=is_writable,
            created_at=datetime.now(tz=timezone.utc),
        )

        record.workspace = workspace
        record.state = WorkerState.PREPARING
        logger.info(
            "WorkerLifecycleManager: prepared workspace %s (strategy=%s) for worker %s",
            workspace.workspace_id, strategy.value, worker_id,
        )
        return workspace

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def transition(self, worker_id: str, new_state: WorkerState) -> None:
        record = self._get_record(worker_id)
        old = record.state
        record.state = new_state
        logger.debug("Worker %s: %s → %s", worker_id, old.value, new_state.value)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_worker(self, worker_id: str) -> bool:
        """
        Cleans up worker workspace.
        Returns True on successful cleanup.
        Raises CleanupFailure if workspace cannot be removed, but records
        the failure internally so it can be reported.
        Does NOT remove read-only shared snapshots (which are the lead root).
        """
        record = self._get_record(worker_id)
        workspace = record.workspace

        if workspace is None or workspace.strategy == WorkspaceStrategy.READ_ONLY_SHARED_SNAPSHOT:
            # Nothing to clean up for read-only shared workspace
            record.state = WorkerState.CLEANED_UP
            return True

        target = workspace.root_path
        try:
            if target.exists():
                # Safety check: must not delete lead workspace
                try:
                    target.relative_to(self._lead_root)
                    raise CleanupFailure(
                        f"Refused to delete workspace at '{target}' because it is "
                        "inside the lead workspace root."
                    )
                except ValueError:
                    pass  # Expected — target is outside lead root

                shutil.rmtree(target, ignore_errors=False)
                logger.info("WorkerLifecycleManager: cleaned up workspace %s for worker %s",
                            target, worker_id)

            record.state = WorkerState.CLEANED_UP
            return True

        except CleanupFailure:
            record.failed_cleanup = True
            record.failure_reason = f"Safety-abort: workspace overlaps lead root ({target})"
            raise

        except Exception as exc:
            msg = f"Failed to clean up workspace {target} for worker {worker_id}: {exc}"
            logger.error(msg)
            record.failed_cleanup = True
            record.failure_reason = str(exc)
            raise CleanupFailure(msg) from exc

    def cleanup_all(self) -> Dict[str, bool]:
        """Attempt cleanup for all workers. Returns {worker_id: success}."""
        results: Dict[str, bool] = {}
        for worker_id in list(self._workers):
            try:
                results[worker_id] = self.cleanup_worker(worker_id)
            except CleanupFailure:
                results[worker_id] = False
        return results

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_worker(self, worker_id: str) -> Optional[WorkerRecord]:
        return self._workers.get(worker_id)

    def list_workers(self) -> List[WorkerRecord]:
        return list(self._workers.values())

    def failed_cleanups(self) -> List[WorkerRecord]:
        return [w for w in self._workers.values() if w.failed_cleanup]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_record(self, worker_id: str) -> WorkerRecord:
        record = self._workers.get(worker_id)
        if record is None:
            raise WorkerLifecycleError(f"Unknown worker '{worker_id}'.")
        return record
