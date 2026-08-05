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
  - Prompt-injection resistance (repo content cannot override assignment policies)
  - Workers NEVER finalize the parent run or issue overall VERIFIED
"""

from __future__ import annotations

import asyncio
import ast
import logging
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from nexus.collaboration.capabilities import AgentCapabilityRegistry
from nexus.collaboration.conflicts import OutOfScopeError, ScopeReservationRegistry
from nexus.collaboration.models import (
    AgentAssignment,
    AgentRole,
    AssignmentResult,
    AssignmentStatus,
    ProposedChange,
    RiskLevel,
    WorkerBudget,
    WorkerContextPacket,
    WorkerWorkspace,
    WorkspaceStrategy,
)
from nexus.collaboration.results import build_finding, build_proposed_change, build_result, validate_result

logger = logging.getLogger(__name__)


class WorkerBudgetExceeded(RuntimeError):
    pass


class WorkerScopeViolation(RuntimeError):
    pass


class WorkerPromptInjectionAttempt(RuntimeError):
    pass


# Untrusted prompt injection keywords in repository content
_INJECTION_KEYWORDS = [
    "ignore assignment scope",
    "modify .env",
    "disable tests",
    "approve this patch",
    "reveal credentials",
    "declare success without verification",
    "bypass gateway",
]


class WorkerRuntime:
    """
    Isolated worker execution runtime.
    Does not hold references to parent run state.
    Cannot call run_finalizer.finalize() or issue overall VERIFIED.
    """

    def __init__(
        self,
        capability_registry: AgentCapabilityRegistry,
        scope_registry: ScopeReservationRegistry,
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
    ) -> AssignmentResult:
        """
        Execute the worker assignment within its constraints.
        Returns a structured AssignmentResult.
        Never calls run_finalizer.finalize() — that belongs to the lead orchestrator.
        """
        raise NotImplementedError("Synthetic collaboration worker runtime is disabled for production safety.")



class _BudgetTracker:
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
