"""
nexus/collaboration/coordination.py

CoordinationBus: orchestrator-mediated message routing between workers.

Rules:
  - All messages are validated against the schema.
  - Workers cannot message each other directly.
  - Messages must not contain credentials.
  - Communication budgets are enforced.
  - Repeated equivalent requests are detected.
  - All messages are auditable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from nexus.collaboration.models import (
    CoordinationMessage,
    CoordinationMessageType,
)

logger = logging.getLogger(__name__)

# Tokens that must not appear in coordination messages
_CREDENTIAL_PATTERNS = (
    "api_key", "secret", "password", "token", "bearer",
    "private_key", "client_secret", "auth",
)

_MAX_CONTENT_SIZE = 32_768  # characters


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _content_contains_credentials(content: Mapping[str, Any]) -> bool:
    raw = json.dumps(content, default=str).lower()
    return any(pat in raw for pat in _CREDENTIAL_PATTERNS)


def _content_fingerprint(content: Mapping[str, Any]) -> str:
    raw = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _message_valid(msg: CoordinationMessage) -> Tuple[bool, str]:
    """Returns (valid, rejection_reason)."""
    if not msg.assignment_id:
        return False, "message missing assignment_id."
    if not msg.sender_id:
        return False, "message missing sender_id."
    if not msg.recipient_id:
        return False, "message missing recipient_id."
    if _content_contains_credentials(msg.content):
        return False, "message content appears to contain credentials. Rejected."
    raw_size = len(json.dumps(dict(msg.content), default=str))
    if raw_size > _MAX_CONTENT_SIZE:
        return False, f"message content exceeds maximum size ({raw_size} > {_MAX_CONTENT_SIZE})."
    return True, ""


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------


class DirectPeerMessageBlocked(RuntimeError):
    """Raised when a worker attempts direct peer messaging."""


class CoordinationBudgetExceeded(RuntimeError):
    """Raised when per-worker or global communication budget is exceeded."""


class DuplicateMessageDetected(RuntimeError):
    """Raised when an equivalent message has already been sent recently."""


class CoordinationBus:
    """
    Single-channel message router.
    Workers must address the orchestrator (ORCHESTRATOR_ID constant).
    The orchestrator may forward content to specific workers.

    Performance target: < 20 ms per message.
    """

    ORCHESTRATOR_ID = "orchestrator"

    def __init__(
        self,
        max_messages_per_worker: int = 50,
        max_global_messages: int = 500,
        on_message: Optional[Callable[[CoordinationMessage], None]] = None,
    ) -> None:
        self._max_per_worker = max_messages_per_worker
        self._max_global = max_global_messages
        self._on_message = on_message

        self._inbox: Dict[str, List[CoordinationMessage]] = defaultdict(list)
        self._audit_log: List[CoordinationMessage] = []
        self._worker_counts: Dict[str, int] = defaultdict(int)
        self._seen_fingerprints: Dict[str, set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(
        self,
        sender_id: str,
        recipient_id: str,
        message_type: CoordinationMessageType,
        assignment_id: str,
        content: Mapping[str, Any],
        evidence_ids: Tuple[str, ...] = (),
    ) -> CoordinationMessage:
        """
        Route a message through the orchestrator.
        Raises if:
          - A non-orchestrator sender addresses a non-orchestrator recipient directly.
          - Content contains credentials.
          - Budget exceeded.
          - Duplicate detected.
        """
        # Enforce orchestrator-mediated routing
        if (
            sender_id != self.ORCHESTRATOR_ID
            and recipient_id != self.ORCHESTRATOR_ID
        ):
            raise DirectPeerMessageBlocked(
                f"Worker '{sender_id}' attempted direct message to '{recipient_id}'. "
                "All messages must route through the orchestrator."
            )

        msg = CoordinationMessage(
            message_id=str(uuid.uuid4()),
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            assignment_id=assignment_id,
            content=content,
            evidence_ids=evidence_ids,
            timestamp=datetime.now(tz=timezone.utc),
        )

        valid, reason = _message_valid(msg)
        if not valid:
            raise ValueError(f"Coordination message rejected: {reason}")

        # Budget checks
        if len(self._audit_log) >= self._max_global:
            raise CoordinationBudgetExceeded(
                f"Global coordination message limit ({self._max_global}) exceeded."
            )

        if self._worker_counts[sender_id] >= self._max_per_worker:
            raise CoordinationBudgetExceeded(
                f"Worker '{sender_id}' exceeded per-worker message limit "
                f"({self._max_per_worker})."
            )

        # Duplicate detection
        fp = _content_fingerprint(content)
        if fp in self._seen_fingerprints[sender_id]:
            raise DuplicateMessageDetected(
                f"Worker '{sender_id}' sent a duplicate message (fingerprint={fp})."
            )
        self._seen_fingerprints[sender_id].add(fp)

        # Deliver
        self._inbox[recipient_id].append(msg)
        self._audit_log.append(msg)
        self._worker_counts[sender_id] += 1

        logger.debug(
            "CoordinationBus: %s → %s [%s] assignment=%s",
            sender_id, recipient_id, message_type.value, assignment_id,
        )

        if self._on_message:
            self._on_message(msg)

        return msg

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def drain(self, recipient_id: str) -> List[CoordinationMessage]:
        """Pop all messages for a recipient."""
        messages = list(self._inbox[recipient_id])
        self._inbox[recipient_id].clear()
        return messages

    def peek(self, recipient_id: str) -> List[CoordinationMessage]:
        """Read without consuming."""
        return list(self._inbox[recipient_id])

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def full_audit_log(self) -> List[CoordinationMessage]:
        return list(self._audit_log)

    def messages_for_assignment(self, assignment_id: str) -> List[CoordinationMessage]:
        return [m for m in self._audit_log if m.assignment_id == assignment_id]

    def worker_message_count(self, worker_id: str) -> int:
        return self._worker_counts[worker_id]
