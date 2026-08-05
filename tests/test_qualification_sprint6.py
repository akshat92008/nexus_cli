"""Sprint 6 End-to-End Qualification Scenarios."""

import pytest
from pathlib import Path
from nexus.planning.engine import PlanningEngine
from nexus.planning.task_contract import TaskType, RiskLevel
from nexus.planning.critic import CritiqueDecision


@pytest.fixture
def engine(tmp_path):
    return PlanningEngine(workspace_root=tmp_path)


def test_scenario_1_bounded_python_bug(engine):
    request = "Fix null pointer exception in context manager cache load"
    context = {
        "relevant_files": ["nexus/context_manager.py"],
        "tests": ["tests/test_api_resilience.py"],
    }
    contract = engine.interpret_task(request, context)
    assert contract.task_type == TaskType.BUG_REPAIR

    plan = engine.create_engineering_plan(contract, context)
    assert any("context_manager.py" in str(target) for s in plan.steps for target in s.intended_targets)

    critique, exec_contract = engine.critique_and_finalize(plan, contract, context)
    assert critique.decision in (CritiqueDecision.APPROVE, CritiqueDecision.APPROVE_WITH_WARNINGS)
    assert exec_contract is not None


def test_scenario_2_cross_file_api_change(engine):
    request = "Update signature of execute_tool across all provider interfaces"
    context = {
        "relevant_files": ["nexus/tool_executor.py", "nexus/providers/base.py", "nexus/providers/hosted.py"],
        "tests": ["tests/test_tools.py"],
    }
    contract = engine.interpret_task(request, context)
    plan = engine.create_engineering_plan(contract, context)

    assert len(plan.affected_scope) >= 2
    critique, exec_contract = engine.critique_and_finalize(plan, contract, context)
    assert exec_contract is not None
    assert exec_contract.is_mutation_allowed("nexus/tool_executor.py")


def test_scenario_3_typescript_feature(engine):
    request = "Add TypeScript type definitions and build step for dashboard component"
    context = {
        "relevant_files": ["nexus/webapp/dashboard.ts"],
        "tests": ["tests/test_dashboard.py"],
    }
    contract = engine.interpret_task(request, context)
    plan = engine.create_engineering_plan(contract, context)

    critique, exec_contract = engine.critique_and_finalize(plan, contract, context)
    assert critique.decision in (CritiqueDecision.APPROVE, CritiqueDecision.APPROVE_WITH_WARNINGS)


def test_scenario_4_config_driven_failure(engine):
    request = "Fix timeout value in NexusConfig initialization"
    context = {
        "relevant_files": ["nexus/config/core.py"],
        "tests": ["tests/test_architecture.py"],
    }
    contract = engine.interpret_task(request, context)
    plan = engine.create_engineering_plan(contract, context)

    assert any("nexus/config/core.py" in p for p in plan.affected_scope)


def test_scenario_5_authentication_security_change(engine):
    request = "Remediate JWT token validation vulnerability in security module"
    context = {
        "relevant_files": ["nexus/security/auth.py"],
        "tests": ["tests/test_agent_safety.py"],
    }
    contract = engine.interpret_task(request, context)
    assert contract.task_type == TaskType.SECURITY_REMEDIATION
    assert contract.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    plan = engine.create_engineering_plan(contract, context)
    critique, exec_contract = engine.critique_and_finalize(plan, contract, context)
    assert exec_contract is not None
    assert "USER_EXPLICIT_APPROVAL" in plan.risk_assessment.get("approval_requirements", [])


def test_scenario_6_framework_migration(engine):
    request = "Migrate database connection layer from SQLite to PostgreSQL backend"
    context = {
        "relevant_files": ["nexus/storage.py"],
        "tests": ["tests/test_agent_services.py"],
    }
    contract = engine.interpret_task(request, context)
    assert contract.task_type == TaskType.MIGRATION

    plan = engine.create_engineering_plan(contract, context)
    critique, exec_contract = engine.critique_and_finalize(plan, contract, context)
    assert exec_contract is not None


def test_scenario_7_intentionally_ambiguous_request(engine):
    request = "delete all database tables and drop schema"
    contract = engine.interpret_task(request)

    # Must detect blocking question
    assert len(contract.unresolved_questions) > 0
    assert any(q.is_blocking for q in contract.unresolved_questions)
