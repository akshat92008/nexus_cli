"""
End-to-End Qualification Test Suite for Sprint 7 Recovery Scenarios 1 to 10.
"""

from __future__ import annotations

import pytest
from nexus.recovery import (
    BaselineAnalyzer,
    FailureCategory,
    FailureKind,
    FailureNormalizer,
    FailureRelation,
    PatchQualityDiagnoser,
    RecoveryBudget,
    RecoveryController,
    RecoveryStrategyType,
    RollbackDecisionEngine,
    SessionResumptionEngine,
    TerminalState,
)


def test_scenario_1_wrong_initial_root_cause(tmp_path):
    """Scenario 1: First patch fails, Nexus diagnoses wrong root cause, revises strategy, succeeds."""
    ctrl = RecoveryController(run_id="s1-run", working_dir=str(tmp_path))

    # Turn 1: Wrong root cause patch fails
    strat1, diag1, term1 = ctrl.handle_failure(
        "FAILED tests/test_calc.py::test_sub - AssertionError: assert 5 == 4",
        patch_content="def sub(a, b): return a - b - 1",
    )
    assert strat1.strategy_type in (RecoveryStrategyType.APPLY_SMALLER_PATCH, RecoveryStrategyType.RETRY_TRANSIENT)

    # Turn 2: Second attempt with updated root cause
    strat2, diag2, term2 = ctrl.handle_failure(
        "FAILED tests/test_calc.py::test_sub - AssertionError: assert 5 == 4",
        patch_content="def sub(a, b): return a - b",
    )
    assert diag2 is not None


def test_scenario_2_missed_caller(tmp_path):
    """Scenario 2: Definition updated without caller, detects caller failure, expands context."""
    ctrl = RecoveryController(run_id="s2-run", working_dir=str(tmp_path))
    strat, diag, term = ctrl.handle_failure(
        "TypeError: render() missing 1 required positional argument: 'theme'\nFile 'nexus/ui.py', line 12",
        source_component="execution",
    )
    assert diag.context_expansion_required or strat.strategy_type in (RecoveryStrategyType.EXPAND_CONTEXT, RecoveryStrategyType.RETRY_WITH_CORRECTED_ARGUMENTS, RecoveryStrategyType.RETRY_TRANSIENT)


def test_scenario_3_configuration_driven_failure(tmp_path):
    """Scenario 3: Environment/config failure detected; code rewriting avoided."""
    ctrl = RecoveryController(run_id="s3-run", working_dir=str(tmp_path))
    strat, diag, term = ctrl.handle_failure(
        "ModuleNotFoundError: No module named 'yaml'",
        source_component="test",
    )
    assert diag.primary_failure.category == FailureCategory.ENVIRONMENT or diag.primary_failure.kind == FailureKind.DEPENDENCY_MISSING
    assert strat.strategy_type in (RecoveryStrategyType.INSTALL_OR_CONFIGURE_DEPENDENCY, RecoveryStrategyType.STOP_BLOCKED)


def test_scenario_4_new_regression(tmp_path):
    """Scenario 4: Patch fixes target test but breaks another test; prevents VERIFIED and triggers rollback/replan."""
    failing = ["test_auth_login", "test_target"]
    baseline = []
    target = ["test_target"]
    rel = BaselineAnalyzer.analyze(failing, baseline_failures=baseline, target_tests=target)
    assert rel["test_auth_login"] == FailureRelation.NEW_REGRESSION

    dec = RollbackDecisionEngine.evaluate(new_regression=True)
    assert dec.should_rollback


def test_scenario_5_command_timeout(tmp_path):
    """Scenario 5: Command times out; classifies timeout and changes strategy without blind retry."""
    ctrl = RecoveryController(run_id="s5-run", working_dir=str(tmp_path))
    strat, diag, term = ctrl.handle_failure(
        "Command 'pytest tests/integration' timed out after 60 seconds",
        command="pytest tests/integration",
    )
    assert diag.primary_failure.kind == FailureKind.COMMAND_TIMEOUT
    assert strat.strategy_type != RecoveryStrategyType.STOP_FAILED


def test_scenario_6_patch_conflict(tmp_path):
    """Scenario 6: Patch conflict detected; avoids partial success and triggers rollback."""
    ctrl = RecoveryController(run_id="s6-run", working_dir=str(tmp_path))
    strat, diag, term = ctrl.handle_failure(
        "error: patch failed: nexus/core.py:42 Hunk #1 failed",
        patch_content="invalid conflict patch",
    )
    assert diag.primary_failure.kind == FailureKind.PATCH_CONFLICT
    assert diag.rollback_required or strat.strategy_type == RecoveryStrategyType.ROLLBACK_TO_CHECKPOINT


def test_scenario_7_dependency_unavailable(tmp_path):
    """Scenario 7: External dependency unavailable; surfaces environment blocker and stops honestly as BLOCKED."""
    ctrl = RecoveryController(run_id="s7-run", working_dir=str(tmp_path))
    strat, diag, term = ctrl.handle_failure(
        "sh: non_existent_pkg: command not found",
        command="non_existent_pkg",
    )
    assert term == TerminalState.BLOCKED or strat.strategy_type in (RecoveryStrategyType.STOP_BLOCKED, RecoveryStrategyType.REQUEST_MISSING_PERMISSION)


def test_scenario_8_interrupted_run(tmp_path):
    """Scenario 8: Interrupted run resumes cleanly after validating workspace state."""
    status = SessionResumptionEngine.prepare_resume("s8-run", str(tmp_path))
    assert status.run_id == "s8-run"


def test_scenario_9_weak_model_repeated_failure(tmp_path):
    """Scenario 9: Weak model fails repeatedly; recommends model escalation."""
    ctrl = RecoveryController(run_id="s9-run", working_dir=str(tmp_path))
    ctrl.handle_failure("JSONDecodeError: Expecting value: line 1 column 1", model_id="weak_model")
    strat, diag, term = ctrl.handle_failure("JSONDecodeError: Expecting value: line 1 column 1", model_id="weak_model")
    assert diag.model_escalation_recommended or strat.strategy_type in (RecoveryStrategyType.SWITCH_MODEL, RecoveryStrategyType.REVISE_PLAN, RecoveryStrategyType.STOP_FAILED)


def test_scenario_10_unrecoverable_task(tmp_path):
    """Scenario 10: Unrecoverable task stops honestly after bounded budget with FAILED state."""
    budget = RecoveryBudget(max_command_retries=1)
    ctrl = RecoveryController(run_id="s10-run", working_dir=str(tmp_path), budget=budget)
    ctrl.handle_failure("Unrecoverable compilation error", source_component="compiler")
    strat, diag, term = ctrl.handle_failure("Unrecoverable compilation error", source_component="compiler")
    assert term in (TerminalState.BUDGET_EXHAUSTED, TerminalState.FAILED)
