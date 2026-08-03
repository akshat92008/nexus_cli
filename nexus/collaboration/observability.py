"""
nexus/collaboration/observability.py

Structured event emission for all collaboration lifecycle events.
Events are lightweight, auditable, and redact sensitive content by default.
Source code is not included in events.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

COLLABORATION_STARTED = "CollaborationStarted"
DELEGATION_ASSESSED = "DelegationAssessed"
ASSIGNMENT_CREATED = "AssignmentCreated"
ASSIGNMENT_VALIDATED = "AssignmentValidated"
WORKER_PREPARED = "WorkerPrepared"
WORKER_STARTED = "WorkerStarted"
WORKER_CONTEXT_REQUESTED = "WorkerContextRequested"
WORKER_BLOCKED = "WorkerBlocked"
WORKER_RESULT_SUBMITTED = "WorkerResultSubmitted"
WORKER_RESULT_REVIEWED = "WorkerResultReviewed"
WORKER_ACCEPTED = "WorkerAccepted"
WORKER_REJECTED = "WorkerRejected"
MUTATION_SCOPE_RESERVED = "MutationScopeReserved"
MUTATION_SCOPE_RELEASED = "MutationScopeReleased"
PARALLEL_GROUP_STARTED = "ParallelGroupStarted"
PARALLEL_GROUP_COMPLETED = "ParallelGroupCompleted"
SEMANTIC_CONFLICT_DETECTED = "SemanticConflictDetected"
INTEGRATION_STARTED = "IntegrationStarted"
ASSIGNMENT_INTEGRATED = "AssignmentIntegrated"
INTEGRATION_FAILED = "IntegrationFailed"
CENTRAL_VERIFICATION_STARTED = "CentralVerificationStarted"
CENTRAL_VERIFICATION_COMPLETED = "CentralVerificationCompleted"
WORKER_CANCELLED = "WorkerCancelled"
COLLABORATION_COMPLETED = "CollaborationCompleted"
COLLABORATION_FAILED = "CollaborationFailed"


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CollaborationEvent:
    event_id: str
    event_type: str
    parent_run_id: str
    collaboration_id: str
    worker_id: Optional[str]
    assignment_id: Optional[str]
    state: Optional[str]
    model_tier: Optional[str]
    budget_usage: Dict[str, Any]
    timing_ms: float
    evidence_ids: Tuple[str, ...]
    error_summary: Optional[str]   # Redacted — no stack traces with secrets
    timestamp: datetime


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------


class CollaborationEventEmitter:
    """
    Emits structured, privacy-safe collaboration events.
    Handlers are registered at runtime (e.g., for logging, telemetry, UI).
    """

    def __init__(self) -> None:
        self._handlers: List[Callable[[CollaborationEvent], None]] = []
        self._log_handler_registered = False

    def register_handler(self, handler: Callable[[CollaborationEvent], None]) -> None:
        self._handlers.append(handler)

    def register_logger(self) -> None:
        """Register a basic logging handler (idempotent)."""
        if not self._log_handler_registered:
            self._handlers.append(_log_event)
            self._log_handler_registered = True

    def emit(
        self,
        event_type: str,
        parent_run_id: str,
        collaboration_id: str,
        worker_id: Optional[str] = None,
        assignment_id: Optional[str] = None,
        state: Optional[str] = None,
        model_tier: Optional[str] = None,
        budget_usage: Optional[Dict[str, Any]] = None,
        timing_ms: float = 0.0,
        evidence_ids: Tuple[str, ...] = (),
        error: Optional[Exception] = None,
    ) -> CollaborationEvent:
        error_summary: Optional[str] = None
        if error is not None:
            # Redact: only type + first 120 chars, no tracebacks with secrets
            raw = f"{type(error).__name__}: {error}"
            error_summary = raw[:120]

        event = CollaborationEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            parent_run_id=parent_run_id,
            collaboration_id=collaboration_id,
            worker_id=worker_id,
            assignment_id=assignment_id,
            state=state,
            model_tier=model_tier,
            budget_usage=budget_usage or {},
            timing_ms=timing_ms,
            evidence_ids=evidence_ids,
            error_summary=error_summary,
            timestamp=datetime.now(tz=timezone.utc),
        )

        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("CollaborationEventEmitter: handler %s failed", handler)

        return event


def _log_event(event: CollaborationEvent) -> None:
    logger.info(
        "[%s] event=%s run=%s collab=%s worker=%s assign=%s",
        event.timestamp.isoformat(),
        event.event_type,
        event.parent_run_id,
        event.collaboration_id,
        event.worker_id or "-",
        event.assignment_id or "-",
    )
