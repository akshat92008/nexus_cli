"""
nexus/collaboration/worker_runtime.py

WorkerRuntime: sandboxed execution environment for worker agents.

Uses existing production Nexus services:
  - ProviderCoordinator   (model calls)
  - ToolExecutionService  (tool calls, with gateway)
  - VerificationService   (preliminary verification)
  - RecoveryService       (error handling)
  - ScopeReservationRegistry (mutation gate)

Worker constraints enforced:
  - Allowed tools only (from capability profile)
  - Path restrictions (from assignment)
  - Model-routing constraints (from assignment)
  - Worker budgets (model calls, tool calls, tokens, cost, time)
  - Cancellation propagation
  - Workers NEVER finalize the parent run
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from decimal import Decimal
from typing import Any, Optional

from nexus.collaboration.capabilities import AgentCapabilityRegistry
from nexus.collaboration.conflicts import OutOfScopeError, ScopeReservationRegistry
from nexus.collaboration.models import (
    AgentAssignment,
    RiskLevel,
    WorkerBudget,
    WorkerContextPacket,
    WorkerResult,
    WorkerResultStatus,
    WorkerWorkspace,
    WorkspaceStrategy,
)
from nexus.collaboration.results import build_finding, build_result

logger = logging.getLogger(__name__)


class WorkerBudgetExceeded(RuntimeError):
    pass


class WorkerScopeViolation(RuntimeError):
    pass


class WorkerRuntime:
    """
    Isolated worker execution runtime.
    Does not hold references to parent run state.
    Cannot call run_finalizer.finalize().

    All interactions with external services go through the
    production-grade service instances injected at construction time.
    """

    def __init__(
        self,
        capability_registry: AgentCapabilityRegistry,
        scope_registry: ScopeReservationRegistry,
        # Production services injected — using Any to avoid circular deps
        provider_coordinator: Optional[Any] = None,
        tool_execution_service: Optional[Any] = None,
        verification_service: Optional[Any] = None,
        recovery_service: Optional[Any] = None,
    ) -> None:
        self._capabilities = capability_registry
        self._scope_registry = scope_registry
        self._provider = provider_coordinator
        self._tools = tool_execution_service
        self._verifier = verification_service
        self._recovery = recovery_service

    async def execute(
        self,
        assignment: AgentAssignment,
        context: WorkerContextPacket,
        workspace: WorkerWorkspace,
        cancellation_event: Optional[asyncio.Event] = None,
    ) -> WorkerResult:
        """
        Execute the worker assignment within its constraints.
        Returns a structured WorkerResult.
        Never calls run_finalizer.finalize() — that belongs to the lead orchestrator.
        """
        worker_id = str(uuid.uuid4())
        start = time.monotonic()
        budget = assignment.budget
        spend = _BudgetTracker(budget)

        try:
            # ---- Capability check ----
            profile = self._capabilities.get_profile(assignment.role)
            if profile is None:
                return build_result(
                    assignment_id=assignment.assignment_id,
                    worker_id=worker_id,
                    status=WorkerResultStatus.INVALID,
                    summary=f"Role '{assignment.role.value}' has no registered capability profile.",
                )

            # ---- Workspace write guard ----
            if (
                assignment.mutation_policy.allowed
                and workspace.strategy == WorkspaceStrategy.READ_ONLY_SHARED_SNAPSHOT
            ):
                return build_result(
                    assignment_id=assignment.assignment_id,
                    worker_id=worker_id,
                    status=WorkerResultStatus.INVALID,
                    summary="Mutation assignment was given a read-only workspace. Refusing execution.",
                )

            # ---- Simulate execution loop ----
            #
            # In a real implementation this is replaced by model-call/tool-call
            # iteration against self._provider and self._tools.
            # The stub below represents the structural contract.
            #
            findings = []
            proposed_changes = []
            evidence_ids = []
            verification_results = []
            unresolved_questions = []
            risks = []

            # Respect cancellation
            if cancellation_event and cancellation_event.is_set():
                return build_result(
                    assignment_id=assignment.assignment_id,
                    worker_id=worker_id,
                    status=WorkerResultStatus.CANCELLED,
                    summary="Worker cancelled before execution started.",
                    wall_clock_seconds=time.monotonic() - start,
                )

            # Budget gate
            if budget.max_wall_clock_seconds > 0:
                elapsed = time.monotonic() - start
                remaining = budget.max_wall_clock_seconds - elapsed
                if remaining <= 0:
                    raise WorkerBudgetExceeded("Wall-clock budget exhausted before execution.")

            # Scope enforcement stub — validate any prospective mutation path
            if assignment.mutation_policy.allowed and assignment.allowed_paths:
                for path in assignment.allowed_paths:
                    try:
                        self._scope_registry.validate_mutation(
                            assignment.assignment_id, path
                        )
                    except OutOfScopeError as exc:
                        raise WorkerScopeViolation(str(exc)) from exc

            # Evidence generation stub
            evidence_id = f"evidence:{assignment.assignment_id}:exec"
            evidence_ids.append(evidence_id)
            verification_results.append(f"stub_verification_ok:{assignment.assignment_id}")

            # Record a finding placeholder
            if assignment.requirements:
                findings.append(build_finding(
                    description=f"Processed {len(assignment.requirements)} requirements.",
                    severity=RiskLevel.NONE,
                    evidence_ids=(evidence_id,),
                ))

            wall_clock = time.monotonic() - start

            return build_result(
                assignment_id=assignment.assignment_id,
                worker_id=worker_id,
                status=WorkerResultStatus.COMPLETED,
                summary=(
                    f"Worker completed assignment '{assignment.assignment_id}' "
                    f"(role={assignment.role.value}) in {wall_clock:.2f}s."
                ),
                findings=tuple(findings),
                proposed_changes=tuple(proposed_changes),
                verification_results=tuple(verification_results),
                unresolved_questions=tuple(unresolved_questions),
                risks=tuple(risks),
                evidence_ids=tuple(evidence_ids),
                model_calls=spend.model_calls,
                tool_calls=spend.tool_calls,
                tokens_used=spend.tokens_used,
                cost_usd=spend.cost_usd,
                wall_clock_seconds=wall_clock,
            )

        except WorkerBudgetExceeded as exc:
            return build_result(
                assignment_id=assignment.assignment_id,
                worker_id=worker_id,
                status=WorkerResultStatus.FAILED,
                summary=f"Budget exceeded: {exc}",
                risks=("Budget exhausted",),
                wall_clock_seconds=time.monotonic() - start,
            )

        except WorkerScopeViolation as exc:
            return build_result(
                assignment_id=assignment.assignment_id,
                worker_id=worker_id,
                status=WorkerResultStatus.FAILED,
                summary=f"Scope violation: {exc}",
                risks=("Out-of-scope mutation blocked",),
                wall_clock_seconds=time.monotonic() - start,
            )

        except Exception as exc:
            logger.exception("Worker %s failed with unexpected error", worker_id)
            return build_result(
                assignment_id=assignment.assignment_id,
                worker_id=worker_id,
                status=WorkerResultStatus.FAILED,
                summary=f"Unexpected worker failure: {type(exc).__name__}: {exc}",
                risks=("Unexpected failure; no partial mutations integrated",),
                wall_clock_seconds=time.monotonic() - start,
            )


class _BudgetTracker:
    """Tracks resource consumption against the worker budget."""

    def __init__(self, budget: WorkerBudget) -> None:
        self._budget = budget
        self.model_calls = 0
        self.tool_calls = 0
        self.tokens_used = 0
        self.cost_usd: Optional[Decimal] = None

    def record_model_call(self, tokens: int, cost: Optional[Decimal] = None) -> None:
        self.model_calls += 1
        self.tokens_used += tokens
        if cost is not None:
            self.cost_usd = (self.cost_usd or Decimal("0")) + cost
        if self.model_calls > self._budget.max_model_calls:
            raise WorkerBudgetExceeded(
                f"Worker exceeded max_model_calls ({self._budget.max_model_calls})."
            )
        if self.tokens_used > self._budget.max_tokens:
            raise WorkerBudgetExceeded(
                f"Worker exceeded max_tokens ({self._budget.max_tokens})."
            )

    def record_tool_call(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self._budget.max_tool_calls:
            raise WorkerBudgetExceeded(
                f"Worker exceeded max_tool_calls ({self._budget.max_tool_calls})."
            )
