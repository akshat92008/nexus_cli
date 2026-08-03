"""
nexus/collaboration/delegation.py

DelegationPlanner: evidence-based decision on whether a task
benefits from multi-agent collaboration. Returns a DelegationAssessment
without making any mutations.

Heuristics used:
  - Number of independent workstreams
  - Repository package count
  - Estimated files affected
  - Language diversity
  - Context size vs model budget
  - Independent verification value
  - Security sensitivity
  - Dependency coupling
  - Time / financial / token budget
  - Worker-isolation availability
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

from nexus.collaboration.models import (
    CollaborationBudget,
    CollaborationPolicyProfile,
    DelegationAssessment,
)


@dataclass
class TaskCharacteristics:
    """Caller-provided signals describing the engineering task."""
    task_id: str
    description: str
    estimated_files_affected: int
    packages_involved: Sequence[str]
    languages_involved: Sequence[str]
    independent_workstreams: Sequence[str]
    sequential_dependencies: Sequence[str]
    estimated_context_tokens: int
    requires_security_review: bool
    requires_architecture_review: bool
    dependency_coupling_score: float   # 0.0 = independent, 1.0 = fully coupled
    time_budget_seconds: Optional[int]
    financial_budget_usd: Optional[float]
    local_only: bool
    worker_isolation_available: bool


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

_MINIMUM_FILES_FOR_PARALLELISM = 5
_MINIMUM_WORKSTREAMS = 2
_COORDINATION_COST_PER_WORKER = 0.10      # fraction of expected benefit
_MAX_COUPLING_FOR_PARALLEL = 0.4
_MINIMUM_CONTEXT_TOKENS_FOR_PARTITION = 8_000


class DelegationPlanner:
    """
    Determines whether collaboration adds measurable value.
    Performance target: < 100 ms excluding I/O.
    """

    def __init__(
        self,
        policy: CollaborationPolicyProfile = CollaborationPolicyProfile.DISABLED,
        budget: Optional[CollaborationBudget] = None,
    ) -> None:
        self._policy = policy
        self._budget = budget

    def assess(
        self,
        task: TaskCharacteristics,
        evidence_ids: Sequence[str] = (),
    ) -> DelegationAssessment:
        start = time.monotonic()

        # --- Fast path: policy hard-disables collaboration ---
        if self._policy == CollaborationPolicyProfile.DISABLED:
            return DelegationAssessment(
                collaboration_recommended=False,
                expected_benefit=0.0,
                coordination_cost=0.0,
                parallelizable_work=(),
                sequential_dependencies=tuple(task.sequential_dependencies),
                risks=("Collaboration policy is DISABLED.",),
                maximum_workers=0,
                evidence_ids=tuple(evidence_ids),
            )

        risks: List[str] = []

        # --- Guard rails ---
        if not task.worker_isolation_available:
            risks.append("Worker isolation is not available in this environment.")
            return self._no_collaboration(
                "Worker isolation unavailable.",
                task,
                risks,
                evidence_ids,
            )

        if task.local_only and self._policy == CollaborationPolicyProfile.CONTROLLED_PARALLEL:
            risks.append("Local-only mode limits model routing for parallel workers.")

        if self._budget and self._budget.maximum_workers <= 1:
            return self._no_collaboration(
                "Budget limits maximum_workers to 1.",
                task,
                risks,
                evidence_ids,
            )

        # --- Benefit signals ---
        benefit = 0.0
        parallelizable: List[str] = list(task.independent_workstreams)

        # Multiple packages or workstreams
        if len(task.packages_involved) >= 2:
            benefit += 0.25
        if len(task.independent_workstreams) >= _MINIMUM_WORKSTREAMS:
            benefit += 0.30

        # Large number of files means partition is worthwhile
        if task.estimated_files_affected >= _MINIMUM_FILES_FOR_PARALLELISM:
            benefit += 0.15

        # Language diversity → cross-language specialist
        if len(set(task.languages_involved)) >= 2:
            benefit += 0.10

        # Context too large for one model: partition wins
        if task.estimated_context_tokens >= _MINIMUM_CONTEXT_TOKENS_FOR_PARTITION:
            benefit += 0.10

        # Independent review adds safety without coordination cost
        if task.requires_security_review:
            benefit += 0.15
            parallelizable.append("security_review")
        if task.requires_architecture_review:
            benefit += 0.10
            parallelizable.append("architecture_review")

        # --- Cost signals ---
        num_workers = min(
            max(1, len(parallelizable)),
            self._budget.maximum_workers if self._budget else 4,
        )
        # Investigation-only mode cannot run mutation workers
        if self._policy == CollaborationPolicyProfile.INVESTIGATION_ONLY:
            num_workers = min(num_workers, 3)

        coordination_cost = num_workers * _COORDINATION_COST_PER_WORKER

        # High coupling kills parallel benefit
        if task.dependency_coupling_score > _MAX_COUPLING_FOR_PARALLEL:
            risks.append(
                f"Dependency coupling score {task.dependency_coupling_score:.2f} "
                f"exceeds threshold {_MAX_COUPLING_FOR_PARALLEL}. Sequential execution preferred."
            )
            return self._no_collaboration(
                "Task coupling too high for safe parallelism.",
                task,
                risks,
                evidence_ids,
            )

        # Insufficient benefit
        net_benefit = benefit - coordination_cost
        recommended = (
            net_benefit > 0
            and len(parallelizable) >= _MINIMUM_WORKSTREAMS
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > 100:
            risks.append(
                f"DelegationPlanner exceeded 100 ms target ({elapsed_ms:.1f} ms). "
                "Review signal complexity."
            )

        return DelegationAssessment(
            collaboration_recommended=recommended,
            expected_benefit=round(benefit, 3),
            coordination_cost=round(coordination_cost, 3),
            parallelizable_work=tuple(parallelizable),
            sequential_dependencies=tuple(task.sequential_dependencies),
            risks=tuple(risks),
            maximum_workers=num_workers if recommended else 0,
            evidence_ids=tuple(evidence_ids),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _no_collaboration(
        reason: str,
        task: TaskCharacteristics,
        risks: List[str],
        evidence_ids: Sequence[str],
    ) -> DelegationAssessment:
        risks_full = [reason] + [r for r in risks if r != reason]
        return DelegationAssessment(
            collaboration_recommended=False,
            expected_benefit=0.0,
            coordination_cost=0.0,
            parallelizable_work=(),
            sequential_dependencies=tuple(task.sequential_dependencies),
            risks=tuple(risks_full),
            maximum_workers=0,
            evidence_ids=tuple(evidence_ids),
        )
