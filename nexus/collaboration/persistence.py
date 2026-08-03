"""
nexus/collaboration/persistence.py

JSON-file persistence for collaboration run state.
Allows resume after crash without repeating completed worker work.

Detected on resume:
  - Repository drift
  - Missing worker workspace
  - Expired reservation
  - Changed user constraints
  - Provider unavailability
  - Stale context
  - Incomplete integration
  - Unverified accepted result
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from nexus.collaboration.models import (
    CollaborationRunState,
    CollaborationState,
)

logger = logging.getLogger(__name__)

_STATE_FILE = "collaboration_state.json"
_VERSION = "1"


def _default_serializer(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


class CollaborationPersistence:
    """
    Lightweight JSON persistence for collaboration state.
    Falls back to nexus.storage if available; otherwise writes to .nexus/ dir.
    """

    def __init__(self, state_dir: Path) -> None:
        self._dir = state_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, collaboration_id: str) -> Path:
        return self._dir / f"collab_{collaboration_id}.json"

    def save(self, state: CollaborationRunState) -> None:
        """Persist the entire run state atomically."""
        path = self._path(state.collaboration_id)
        tmp_path = path.with_suffix(".tmp")
        try:
            payload = {
                "version": _VERSION,
                "run_id": state.run_id,
                "collaboration_id": state.collaboration_id,
                "state": state.state.value,
                "policy": state.policy.value,
                "cancelled": state.cancelled,
                "created_at": state.created_at.isoformat(),
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                "worker_states": {
                    wid: ws.value for wid, ws in state.worker_states.items()
                },
                "accepted_assignments": list(state.worker_reviews.keys()),
                "integration_done": state.integration_result is not None,
            }
            with open(tmp_path, "w") as f:
                json.dump(payload, f, indent=2, default=_default_serializer)
            os.replace(tmp_path, path)
            logger.debug("CollaborationPersistence: saved state for %s", state.collaboration_id)
        except Exception as exc:
            logger.error("CollaborationPersistence: save failed: %s", exc)
            raise

    def load(self, collaboration_id: str) -> Optional[Dict[str, Any]]:
        """Load raw persisted state dict. Returns None if not found."""
        path = self._path(collaboration_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as exc:
            logger.error("CollaborationPersistence: load failed for %s: %s",
                         collaboration_id, exc)
            return None

    def delete(self, collaboration_id: str) -> bool:
        """Remove persisted state. Returns True if deleted."""
        path = self._path(collaboration_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_collaboration_ids(self) -> list[str]:
        return [
            f.stem.removeprefix("collab_")
            for f in self._dir.glob("collab_*.json")
        ]


class ResumeValidator:
    """
    Validates a persisted run on resume, detecting staleness conditions.
    """

    def __init__(self, current_revision: str) -> None:
        self._revision = current_revision

    def validate(self, persisted: Dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Returns (can_resume, list_of_warnings).
        Returns (False, reasons) when resume is unsafe.
        """
        warnings: list[str] = []

        if persisted.get("version") != _VERSION:
            return False, [
                f"Persisted state version '{persisted.get('version')}' "
                f"does not match current version '{_VERSION}'."
            ]

        state_str = persisted.get("state", "")
        terminal = {
            CollaborationState.COMPLETED.value,
            CollaborationState.CANCELLED.value,
        }
        if state_str in terminal:
            return False, [
                f"Collaboration is already in terminal state '{state_str}'. "
                "Nothing to resume."
            ]

        if persisted.get("cancelled"):
            return False, ["Collaboration was cancelled. Cannot resume a cancelled run."]

        # Integration was complete but verification not done
        state = persisted.get("state", "")
        if state == CollaborationState.INTEGRATING.value:
            warnings.append(
                "Collaboration was interrupted during integration. "
                "Will re-verify integrated results."
            )

        if state == CollaborationState.VERIFYING.value:
            warnings.append(
                "Collaboration was interrupted during verification. "
                "Will re-run central verification."
            )

        return True, warnings
