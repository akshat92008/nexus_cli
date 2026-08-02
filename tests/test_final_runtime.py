"""Regression coverage for the integrated Nexus final runtime."""

from __future__ import annotations
from nexus.execution_engine import ExecutionEngine

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from nexus.behavioral import DatabaseVerifier, ProbeStatus, SecurityScanner
from nexus.benchmark import BenchmarkSuite
from nexus.runtime.kernel import ExecutionResult, ReviewOutcome, TaskDagKernel, TaskOutcome, classify_failure
from nexus.planner import (
    Difficulty,
    ExecutionPlan,
    IntentType,
    PlanStep,
    PlanType,
)
from nexus.policy import PermissionDecision, PolicyLoader
from nexus.project_memory import ProjectMemory
from nexus.context_engine import ContextEngine
from nexus.run_catalog import RunCatalog
from nexus.run_state import RunLedger, RunStatus
from nexus.sandbox import CommandSpec, SandboxBackend, SandboxRunner
from nexus.skills.loader import SkillLoader, SkillRegistry
from nexus.workspace import GitWorktreeSession


def _plan(steps: list[PlanStep]) -> ExecutionPlan:
    return ExecutionPlan(
        id="final-plan",
        goal="Implement and verify the final runtime",
        intent=IntentType.BUILD,
        difficulty=Difficulty.COMPLEX,
        plan_type=PlanType.PLANNED,
        steps=steps,
        acceptance_criteria=["All tasks and checks pass"],
        retry_policy={"per_task": 1, "total_repairs": 2},
    )


def test_sandbox_uses_typed_argv_and_reports_unenforced_network(tmp_path, monkeypatch):
    monkeypatch.setattr(SandboxRunner, "_backend_cache", SandboxBackend.RESTRICTED)
    result = SandboxRunner(tmp_path).run(
        CommandSpec.create(
            [sys.executable, "-c", "print('typed-ok')"],
            tmp_path,
            timeout_seconds=10,
        )
    )
    assert result.success
    assert result.stdout == "typed-ok"
    assert result.argv[:2] == [sys.executable, "-c"]
    assert not result.network_enforced
    assert "network=policy-only" in result.format_tool_output()


def test_sandbox_can_fail_closed_without_os_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(SandboxRunner, "_backend_cache", SandboxBackend.RESTRICTED)
    result = SandboxRunner(tmp_path).run(
        CommandSpec.create(
            ["echo", "must-not-run"],
            tmp_path,
            require_os_isolation=True,
        )
    )
    assert not result.success
    assert result.backend == SandboxBackend.BLOCKED
    assert "No supported OS sandbox" in result.blocked_reason


def test_execution_engine_runs_dag_repairs_and_independent_review(tmp_path):
    plan = _plan(
        [
            PlanStep(1, "Implement", "Implement feature", retry_limit=1),
            PlanStep(2, "Verify", "Run checks", depends_on=[1]),
        ]
    )
    ledger = RunLedger("dag-session", tmp_path, root=tmp_path / "state")
    ledger.begin("implement feature", plan=plan)
    calls = []

    def execute(step):
        calls.append(step.id)
        if step.id == 1:
            return TaskOutcome(False, "syntax failed", output="SyntaxError: invalid syntax")
        return TaskOutcome(True, "checks passed", evidence_ids=["check-1"])

    def repair(step, _outcome, failure, attempt):
        assert step.id == 1
        assert failure.value == "syntax"
        assert attempt == 1
        return TaskOutcome(True, "minimal repair passed", evidence_ids=["repair-1"])

    result = TaskDagKernel(plan, ledger).run_dag(
        execute,
        repair=repair,
        reviewer=lambda _plan: ReviewOutcome(True, "independent review passed"),
    )
    assert result.succeeded
    assert calls == [1, 2]
    assert result.repairs == 1
    assert plan.steps[0].attempts == 2
    assert (
        json.loads((ledger.turn_dir / "tasks.json").read_text())["tasks"][1]["status"]
        == "completed"
    )


def test_execution_engine_rejects_cycles(tmp_path):
    plan = _plan(
        [
            PlanStep(1, "A", "A", depends_on=[2]),
            PlanStep(2, "B", "B", depends_on=[1]),
        ]
    )
    ledger = RunLedger("cycle-session", tmp_path, root=tmp_path / "state")
    ledger.begin("cycle", plan=plan)
    with pytest.raises(ValueError, match="cycle"):
        TaskDagKernel(plan, ledger).run_dag(lambda _step: TaskOutcome(True, "ok"))

def test_benchmark_manifest_is_versioned_and_shell_free():
    manifest = Path(__file__).parents[1] / "benchmarks" / "core.json"
    suite = BenchmarkSuite.load(manifest)
    assert suite.tasks[0].category == "bug-repair"
    assert suite.tasks[0].verification == (("python", "verify.py"),)
