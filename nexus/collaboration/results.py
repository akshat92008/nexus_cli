"""
nexus/collaboration/results.py

Worker result schema, validation, and status tracking.

Workers must not submit unrestricted prose as their only output.
All results must pass schema and evidence validation before acceptance.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional, Tuple

from nexus.collaboration.models import (
    ProposedChange,
    ResourceUsage,
    RiskLevel,
    WorkerFinding,
    WorkerResult,
    WorkerResultStatus,
)

# ---------------------------------------------------------------------------
# Result validation
# ---------------------------------------------------------------------------


class ResultValidationError(ValueError):
    """Raised when a WorkerResult fails schema or evidence validation."""


def validate_result(result: WorkerResult) -> None:
    """
    Validates that a WorkerResult satisfies the minimum contract.
    Raises ResultValidationError on failure.
    """
    if not result.assignment_id:
        raise ResultValidationError("WorkerResult.assignment_id is required.")

    if not result.worker_id:
        raise ResultValidationError("WorkerResult.worker_id is required.")

    if not result.summary or len(result.summary.strip()) < 10:
        raise ResultValidationError(
            "WorkerResult.summary must be a substantive description (≥10 chars)."
        )

    if result.status == WorkerResultStatus.COMPLETED:
        # Completed results must have evidence
        if not result.evidence_ids:
            raise ResultValidationError(
                "COMPLETED result must provide at least one evidence_id."
            )
        # Completed results must have proposed changes or findings
        if not result.proposed_changes and not result.findings:
            raise ResultValidationError(
                "COMPLETED result must include proposed_changes or findings."
            )
        # Proposed changes need diff references for mutation workers
        for change in result.proposed_changes:
            if not change.path:
                raise ResultValidationError(
                    f"ProposedChange '{change.change_id}' missing required 'path'."
                )

    if result.status == WorkerResultStatus.INVALID:
        # Always rejected — no further validation needed
        return

    # Cost must be a ResourceUsage
    if not isinstance(result.cost, ResourceUsage):
        raise ResultValidationError("WorkerResult.cost must be a ResourceUsage instance.")


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def build_finding(
    description: str,
    severity: RiskLevel,
    evidence_ids: Tuple[str, ...] = (),
    affected_paths: Tuple[str, ...] = (),
) -> WorkerFinding:
    return WorkerFinding(
        finding_id=str(uuid.uuid4()),
        description=description,
        severity=severity,
        evidence_ids=evidence_ids,
        affected_paths=affected_paths,
    )


def build_proposed_change(
    path: str,
    description: str,
    diff_reference: Optional[str] = None,
    transaction_ref: Optional[str] = None,
) -> ProposedChange:
    return ProposedChange(
        change_id=str(uuid.uuid4()),
        path=path,
        description=description,
        diff_reference=diff_reference,
        transaction_ref=transaction_ref,
    )


def build_result(
    assignment_id: str,
    worker_id: str,
    status: WorkerResultStatus,
    summary: str,
    findings: Tuple[WorkerFinding, ...] = (),
    proposed_changes: Tuple[ProposedChange, ...] = (),
    transaction_reference: Optional[str] = None,
    verification_results: Tuple[str, ...] = (),
    unresolved_questions: Tuple[str, ...] = (),
    risks: Tuple[str, ...] = (),
    evidence_ids: Tuple[str, ...] = (),
    model_calls: int = 0,
    tool_calls: int = 0,
    tokens_used: int = 0,
    cost_usd: Optional[Decimal] = None,
    wall_clock_seconds: float = 0.0,
) -> WorkerResult:
    return WorkerResult(
        assignment_id=assignment_id,
        worker_id=worker_id,
        status=status,
        summary=summary,
        findings=findings,
        proposed_changes=proposed_changes,
        transaction_reference=transaction_reference,
        verification_results=verification_results,
        unresolved_questions=unresolved_questions,
        risks=risks,
        evidence_ids=evidence_ids,
        cost=ResourceUsage(
            model_calls=model_calls,
            tool_calls=tool_calls,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            wall_clock_seconds=wall_clock_seconds,
        ),
    )
