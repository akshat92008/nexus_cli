"""
nexus/collaboration/review.py

ResultReviewService: validates every worker result before it can
be accepted for integration.

A worker result CANNOT be accepted because the worker reports success.
All claims must be independently verified.
"""

from __future__ import annotations

import uuid
from typing import List, Sequence

from nexus.collaboration.models import (
    AgentAssignment,
    ReviewFinding,
    ReviewFindingCategory,
    RiskLevel,
    WorkerResult,
    WorkerResultStatus,
    WorkerReview,
)
from nexus.collaboration.results import ResultValidationError, validate_result

# ---------------------------------------------------------------------------
# Review service
# ---------------------------------------------------------------------------


class ResultReviewService:
    """
    Policy-driven review of worker results.
    Returns WorkerReview containing accept/reject decision and structured findings.

    Performance target: < 50 ms per review excluding I/O.
    """

    def __init__(
        self,
        known_repository_revision: str,
        allowed_path_prefixes: Sequence[str] = (),
    ) -> None:
        self._revision = known_repository_revision
        self._allowed_prefixes = tuple(allowed_path_prefixes)

    def review(
        self,
        result: WorkerResult,
        assignment: AgentAssignment,
        current_revision: str,
    ) -> WorkerReview:
        findings: List[ReviewFinding] = []
        missing_evidence: List[str] = []
        required_revisions: List[str] = []

        # ----------------------------------------------------------------
        # 1. Schema validation (untrusted input)
        # ----------------------------------------------------------------
        try:
            validate_result(result)
        except ResultValidationError as exc:
            findings.append(ReviewFinding(
                finding_id=str(uuid.uuid4()),
                category=ReviewFindingCategory.ASSIGNMENT_NONCOMPLIANCE,
                description=f"Schema validation failed: {exc}",
                severity=RiskLevel.HIGH,
            ))

        # ----------------------------------------------------------------
        # 2. Assignment compliance
        # ----------------------------------------------------------------
        if result.assignment_id != assignment.assignment_id:
            findings.append(ReviewFinding(
                finding_id=str(uuid.uuid4()),
                category=ReviewFindingCategory.ASSIGNMENT_NONCOMPLIANCE,
                description=(
                    f"Result assignment_id '{result.assignment_id}' does not match "
                    f"expected '{assignment.assignment_id}'."
                ),
                severity=RiskLevel.CRITICAL,
            ))

        # ----------------------------------------------------------------
        # 3. Scope compliance — unplanned files
        # ----------------------------------------------------------------
        allowed_paths_strs = {str(p) for p in assignment.allowed_paths}
        prohibited_paths_strs = {str(p) for p in assignment.prohibited_paths}

        for change in result.proposed_changes:
            path = change.path
            if path in prohibited_paths_strs:
                findings.append(ReviewFinding(
                    finding_id=str(uuid.uuid4()),
                    category=ReviewFindingCategory.SCOPE_VIOLATION,
                    description=f"Change targets prohibited path: {path}",
                    severity=RiskLevel.CRITICAL,
                ))
            elif allowed_paths_strs and not any(
                path.startswith(ap) for ap in allowed_paths_strs
            ):
                findings.append(ReviewFinding(
                    finding_id=str(uuid.uuid4()),
                    category=ReviewFindingCategory.UNPLANNED_FILE,
                    description=f"Change targets unplanned file outside allowed scope: {path}",
                    severity=RiskLevel.HIGH,
                ))

        # ----------------------------------------------------------------
        # 4. Evidence completeness
        # ----------------------------------------------------------------
        if result.status == WorkerResultStatus.COMPLETED and not result.evidence_ids:
            missing_evidence.append("No evidence_ids provided for COMPLETED result.")

        # Check required evidence per verification_requirements
        for req in assignment.verification_requirements:
            matched = any(req.lower() in ev.lower() for ev in result.evidence_ids)
            if not matched:
                missing_evidence.append(
                    f"Verification requirement '{req}' not satisfied by any evidence_id."
                )

        # ----------------------------------------------------------------
        # 5. Unsupported claims — success claim without verification proof
        # ----------------------------------------------------------------
        if (
            result.status == WorkerResultStatus.COMPLETED
            and not result.verification_results
        ):
            findings.append(ReviewFinding(
                finding_id=str(uuid.uuid4()),
                category=ReviewFindingCategory.UNSUPPORTED_CLAIM,
                description=(
                    "Worker reports COMPLETED but provides no verification_results. "
                    "Success claim is unsupported."
                ),
                severity=RiskLevel.HIGH,
            ))

        # ----------------------------------------------------------------
        # 6. Repository revision compatibility
        # ----------------------------------------------------------------
        if current_revision != self._revision:
            findings.append(ReviewFinding(
                finding_id=str(uuid.uuid4()),
                category=ReviewFindingCategory.ASSIGNMENT_NONCOMPLIANCE,
                description=(
                    f"Repository revision mismatch: worker context was built at "
                    f"'{self._revision}', current is '{current_revision}'. "
                    "Worker output may be stale."
                ),
                severity=RiskLevel.MEDIUM,
            ))
            required_revisions.append(
                "Re-validate changes against current repository revision."
            )

        # ----------------------------------------------------------------
        # 7. Mutation policy check
        # ----------------------------------------------------------------
        if result.proposed_changes and not assignment.mutation_policy.allowed:
            findings.append(ReviewFinding(
                finding_id=str(uuid.uuid4()),
                category=ReviewFindingCategory.POLICY_VIOLATION,
                description=(
                    "Worker submitted proposed_changes but assignment mutation_policy "
                    "disallows mutation."
                ),
                severity=RiskLevel.CRITICAL,
            ))

        # ----------------------------------------------------------------
        # 8. Security-risk signals in result findings
        # ----------------------------------------------------------------
        for finding in result.findings:
            if finding.severity in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                findings.append(ReviewFinding(
                    finding_id=str(uuid.uuid4()),
                    category=ReviewFindingCategory.SECURITY_RISK,
                    description=(
                        f"Worker finding '{finding.finding_id}' carries "
                        f"{finding.severity.value} severity: {finding.description}"
                    ),
                    severity=finding.severity,
                ))

        # ----------------------------------------------------------------
        # Determine acceptance
        # ----------------------------------------------------------------
        blocking_categories = {
            ReviewFindingCategory.SCOPE_VIOLATION,
            ReviewFindingCategory.POLICY_VIOLATION,
            ReviewFindingCategory.ASSIGNMENT_NONCOMPLIANCE,
        }
        blocking_severities = {RiskLevel.CRITICAL}

        has_blocking = any(
            f.category in blocking_categories or f.severity in blocking_severities
            for f in findings
        )

        has_missing_evidence = bool(missing_evidence)
        has_unsupported_claims = any(
            f.category == ReviewFindingCategory.UNSUPPORTED_CLAIM for f in findings
        )

        accepted = (
            not has_blocking
            and not has_missing_evidence
            and not has_unsupported_claims
            and result.status in (
                WorkerResultStatus.COMPLETED,
                WorkerResultStatus.PARTIAL,
            )
        )

        integration_eligible = accepted and result.status == WorkerResultStatus.COMPLETED

        return WorkerReview(
            assignment_id=assignment.assignment_id,
            accepted=accepted,
            findings=tuple(findings),
            missing_evidence=tuple(missing_evidence),
            required_revisions=tuple(required_revisions),
            integration_eligible=integration_eligible,
        )
