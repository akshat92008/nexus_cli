"""Dependency-aware, resumable execution and focused repair for Nexus plans."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from nexus.planner import ExecutionPlan, PlanStep, TaskStatus
from nexus.run_state import RunLedger


class FailureKind(str, Enum):
    """Deterministic failure classes used to focus repair prompts."""

    SYNTAX = "syntax"
    IMPORT = "import"
    TYPE = "type"
    TEST = "test"
    RUNTIME = "runtime"
    DEPENDENCY = "dependency"
    TIMEOUT = "timeout"
    ENVIRONMENT = "environment"
    SECURITY = "security"
    UNKNOWN = "unknown"


@dataclass
class TaskOutcome:
    """Outcome returned by a task executor or repair callback."""

    success: bool
    summary: str
    evidence_ids: list[str] = field(default_factory=list)
    output: str = ""
    changed_files: list[str] = field(default_factory=list)
    verification_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewOutcome:
    """Independent review result for a completed task or plan."""

    approved: bool
    summary: str
    findings: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Final state of a DAG execution."""

    status: TaskStatus
    completed: list[int]
    failed: list[int]
    blocked: list[int]
    repairs: int
    review: ReviewOutcome | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == TaskStatus.COMPLETED and not self.failed and not self.blocked


StepExecutor = Callable[[PlanStep], TaskOutcome]
StepVerifier = Callable[[PlanStep, TaskOutcome], TaskOutcome]
StepRepairer = Callable[[PlanStep, TaskOutcome, FailureKind, int], TaskOutcome]
PlanReviewer = Callable[[ExecutionPlan], ReviewOutcome]


class ExecutionEngine:
    """Run a typed task DAG with checkpointed state and bounded repairs."""

    def __init__(
        self,
        plan: ExecutionPlan,
        ledger: RunLedger,
        *,
        max_total_repairs: int | None = None,
    ):
        self.plan = plan
        self.ledger = ledger
        configured = int(plan.retry_policy.get("total_repairs", 5))
        self.max_total_repairs = max(0, configured if max_total_repairs is None else max_total_repairs)
        self.repairs = 0

    def run(
        self,
        execute: StepExecutor,
        *,
        verify: StepVerifier | None = None,
        repair: StepRepairer | None = None,
        reviewer: PlanReviewer | None = None,
    ) -> ExecutionResult:
        """Execute all dependency-ready tasks until the DAG completes or blocks."""
        self._validate_graph()
        self.ledger.record_tasks(self.plan.steps)
        self.ledger.append_event(
            "dag_started",
            status="verified",
            detail=f"Starting dependency-aware execution of {len(self.plan.steps)} task(s).",
            metadata={"plan_id": self.plan.id},
        )

        while True:
            ready = self._ready_steps()
            if not ready:
                break
            for step in ready:
                self._run_step(step, execute, verify, repair)
                self.ledger.record_tasks(self.plan.steps)
                self.ledger.record_plan(self.plan)

        self._block_orphans()
        completed = [step.id for step in self.plan.steps if step.status == TaskStatus.COMPLETED]
        failed = [step.id for step in self.plan.steps if step.status == TaskStatus.FAILED]
        blocked = [step.id for step in self.plan.steps if step.status == TaskStatus.BLOCKED]

        review_result = None
        if not failed and not blocked and all(
            step.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for step in self.plan.steps
        ):
            if reviewer is not None:
                review_result = reviewer(self.plan)
                self.ledger.append_event(
                    "independent_review",
                    status="verified" if review_result.approved else "failed",
                    detail=review_result.summary,
                    metadata={
                        "findings": review_result.findings,
                        "evidence_ids": review_result.evidence_ids,
                    },
                )
                if not review_result.approved:
                    self.plan.status = TaskStatus.FAILED
                else:
                    self.plan.status = TaskStatus.COMPLETED
            else:
                self.plan.status = TaskStatus.COMPLETED
        elif failed:
            self.plan.status = TaskStatus.FAILED
        else:
            self.plan.status = TaskStatus.BLOCKED

        self.ledger.record_tasks(self.plan.steps)
        self.ledger.record_plan(self.plan)
        self.ledger.append_event(
            "dag_finished",
            status="verified" if self.plan.status == TaskStatus.COMPLETED else "failed",
            detail=f"DAG finished with status {self.plan.status.value}.",
            metadata={
                "completed": completed,
                "failed": failed,
                "blocked": blocked,
                "repairs": self.repairs,
            },
        )
        return ExecutionResult(
            status=self.plan.status,
            completed=completed,
            failed=failed,
            blocked=blocked,
            repairs=self.repairs,
            review=review_result,
        )

    def _run_step(
        self,
        step: PlanStep,
        execute: StepExecutor,
        verify: StepVerifier | None,
        repair: StepRepairer | None,
    ) -> None:
        step.status = TaskStatus.IN_PROGRESS
        step.started_at = datetime.now(timezone.utc).isoformat()
        step.attempts += 1
        self.ledger.append_event(
            "task_started",
            status="verified",
            detail=step.title,
            metadata={"task_id": step.id, "attempt": step.attempts},
        )
        outcome = execute(step)
        if outcome.success and verify is not None:
            outcome = verify(step, outcome)

        repair_number = 0
        while (
            not outcome.success
            and repair is not None
            and repair_number < step.retry_limit
            and self.repairs < self.max_total_repairs
        ):
            repair_number += 1
            self.repairs += 1
            failure_kind = classify_failure(outcome.output or outcome.summary)
            self.ledger.append_event(
                "repair_started",
                status="verified",
                detail=f"Focused {failure_kind.value} repair for task {step.id}.",
                metadata={
                    "task_id": step.id,
                    "repair": repair_number,
                    "failure_kind": failure_kind.value,
                    "failure": (outcome.output or outcome.summary)[:4000],
                },
            )
            outcome = repair(step, outcome, failure_kind, repair_number)
            step.attempts += 1
            if outcome.success and verify is not None:
                outcome = verify(step, outcome)

        step.result = outcome.summary
        step.error = "" if outcome.success else (outcome.output or outcome.summary)
        step.status = TaskStatus.COMPLETED if outcome.success else TaskStatus.FAILED
        step.completed_at = datetime.now(timezone.utc).isoformat()
        self.ledger.append_event(
            "task_finished",
            status="verified" if outcome.success else "failed",
            detail=outcome.summary,
            metadata={
                "task_id": step.id,
                "attempts": step.attempts,
                "evidence_ids": outcome.evidence_ids,
                "changed_files": outcome.changed_files,
                "verification_commands": outcome.verification_commands,
            },
        )
        if outcome.success:
            self.ledger.checkpoint(
                f"task-{step.id}-verified",
                plan=self.plan,
                metadata={
                    "task_id": step.id,
                    "evidence_ids": outcome.evidence_ids,
                    "changed_files": outcome.changed_files,
                },
            )

    def _ready_steps(self) -> list[PlanStep]:
        status_by_id = {step.id: step.status for step in self.plan.steps}
        return [
            step
            for step in self.plan.steps
            if step.status == TaskStatus.PENDING
            and all(
                status_by_id[dependency] in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
                for dependency in step.depends_on
            )
        ]

    def _block_orphans(self) -> None:
        status_by_id = {step.id: step.status for step in self.plan.steps}
        for step in self.plan.steps:
            if step.status != TaskStatus.PENDING:
                continue
            failed_dependencies = [
                dependency
                for dependency in step.depends_on
                if status_by_id.get(dependency) in (TaskStatus.FAILED, TaskStatus.BLOCKED)
            ]
            if failed_dependencies:
                step.status = TaskStatus.BLOCKED
                step.error = f"Blocked by failed dependencies: {failed_dependencies}"
                step.completed_at = datetime.now(timezone.utc).isoformat()

    def _validate_graph(self) -> None:
        ids = [step.id for step in self.plan.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Task DAG contains duplicate task ids")
        known = set(ids)
        for step in self.plan.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"Task {step.id} depends on unknown task ids: {sorted(missing)}")
            if step.id in step.depends_on:
                raise ValueError(f"Task {step.id} depends on itself")

        visiting: set[int] = set()
        visited: set[int] = set()
        graph = {step.id: step.depends_on for step in self.plan.steps}

        def visit(task_id: int) -> None:
            if task_id in visiting:
                raise ValueError("Task DAG contains a dependency cycle")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in graph[task_id]:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in ids:
            visit(task_id)


_FAILURE_PATTERNS: tuple[tuple[FailureKind, tuple[str, ...]], ...] = (
    (FailureKind.TIMEOUT, ("timed out", "timeout", "deadline exceeded")),
    (FailureKind.SYNTAX, ("syntaxerror", "parse error", "unexpected token", "syntax error")),
    (FailureKind.IMPORT, ("modulenotfound", "importerror", "cannot find module", "unresolved import")),
    (FailureKind.TYPE, ("typeerror", "type error", "mypy", "ts2322", "incompatible type")),
    (FailureKind.TEST, ("assertionerror", "failed test", "tests failed", "assert ")),
    (FailureKind.DEPENDENCY, ("dependency conflict", "no matching distribution", "eresolve")),
    (FailureKind.SECURITY, ("vulnerability", "secret detected", "security policy")),
    (FailureKind.ENVIRONMENT, ("command not found", "not installed", "connection refused")),
    (FailureKind.RUNTIME, ("traceback", "runtimeerror", "exception", "panic:")),
)


def classify_failure(output: str) -> FailureKind:
    """Classify raw failure evidence without asking a model."""
    normalized = re.sub(r"\s+", " ", output.lower())
    for kind, patterns in _FAILURE_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return kind
    return FailureKind.UNKNOWN
