"""
tests/test_qualification_sprint10.py

Comprehensive qualification test suite for Sprint 10: Multi-Agent Collaboration,
Subagent Coordination and Verified Integration.

Covers all 12 qualification scenarios:
  Scenario 1: Implementer plus reviewer
  Scenario 2: Investigator plus implementer
  Scenario 3: Implementer plus test engineer
  Scenario 4: Parallel package work
  Scenario 5: Overlapping mutations
  Scenario 6: Worker timeout
  Scenario 7: Malformed worker output
  Scenario 8: Integration conflict
  Scenario 9: Central-verification failure
  Scenario 10: Collaboration not beneficial (single-agent fallback)
  Scenario 11: Budget pressure
  Scenario 12: Interrupted collaboration & safe resume
"""

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from nexus.collaboration import (
    AgentAssignment,
    AgentRole,
    AssignmentGraph,
    AssignmentResult,
    AssignmentReview,
    AssignmentScope,
    AssignmentStatus,
    CollaborationBudget,
    CollaborationMode,
    CollaborationPolicyProfile,
    CollaborationState,
    DelegationPlanner,
    IntegrationCoordinator,
    IntegrationStatus,
    LeadOrchestrator,
    ResultReviewService,
    ReviewDecision,
    RiskLevel,
    ScopeReservationRegistry,
    TaskCharacteristics,
    WorkerBudget,
    WorkerLifecycleManager,
    WorkerRuntime,
    WorkerState,
    WorkspaceStrategy,
)
from nexus.collaboration.conflicts import OutOfScopeError, ReservationConflictError, ReservationMode
from nexus.collaboration.persistence import CollaborationPersistence


@pytest.fixture
def temp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "nexus").mkdir()
    (repo / "nexus" / "core.py").write_text("# Core implementation\ndef main(): pass\n")
    (repo / "nexus" / "buffer.py").write_text("# Buffer implementation\nclass BufferPool: pass\n")
    return repo


@pytest.fixture
def default_wb():
    return WorkerBudget(
        max_model_calls=10,
        max_tool_calls=20,
        max_tokens=50000,
        max_cost_usd=Decimal("0.50"),
        max_wall_clock_seconds=120,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — Implementer Plus Reviewer
# ---------------------------------------------------------------------------
def test_scenario_1_implementer_plus_reviewer(temp_repo, default_wb):
    a1 = AgentAssignment(
        assignment_id="s1-impl",
        role=AgentRole.IMPLEMENTER,
        objective="Implement feature",
        allowed_mutation_paths=(Path("nexus/core.py"),),
        expected_deliverables=("Core patch",),
        acceptance_criteria=("Feature implemented",),
        budget=default_wb,
    )
    a2 = AgentAssignment(
        assignment_id="s1-rev",
        role=AgentRole.REVIEWER,
        objective="Review feature patch",
        dependencies=("s1-impl",),
        expected_deliverables=("Review findings",),
        acceptance_criteria=("Patch approved",),
        budget=default_wb,
    )

    orchestrator = LeadOrchestrator(
        run_id="run-s1",
        policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
        lead_workspace_root=temp_repo,
        persistence_dir=temp_repo / ".nexus" / "runs" / "run-s1" / "collab",
    )

    final_state = asyncio.run(orchestrator.run_collaboration([a1, a2]))
    assert final_state.state == CollaborationState.COMPLETED
    assert isinstance(final_state.mode, CollaborationMode)
    assert len(final_state.worker_results) == 2
    assert final_state.integration_result is not None
    assert "s1-impl" in final_state.integration_result.applied_assignments


# ---------------------------------------------------------------------------
# Scenario 2 — Investigator Plus Implementer
# ---------------------------------------------------------------------------
def test_scenario_2_investigator_plus_implementer(temp_repo, default_wb):
    a1 = AgentAssignment(
        assignment_id="s2-inv",
        role=AgentRole.INVESTIGATOR,
        objective="Investigate root cause",
        expected_deliverables=("Diagnosis",),
        acceptance_criteria=("Root cause found",),
        budget=default_wb,
    )
    a2 = AgentAssignment(
        assignment_id="s2-impl",
        role=AgentRole.IMPLEMENTER,
        objective="Fix configuration issue",
        dependencies=("s2-inv",),
        allowed_mutation_paths=(Path("nexus/core.py"),),
        expected_deliverables=("Config patch",),
        acceptance_criteria=("Config fixed",),
        budget=default_wb,
    )

    orchestrator = LeadOrchestrator(
        run_id="run-s2",
        policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
        lead_workspace_root=temp_repo,
    )

    final_state = asyncio.run(orchestrator.run_collaboration([a1, a2]))
    assert final_state.state == CollaborationState.COMPLETED
    assert "s2-inv" in final_state.worker_results
    assert final_state.worker_results["s2-inv"].status == AssignmentStatus.COMPLETED


# ---------------------------------------------------------------------------
# Scenario 3 — Implementer Plus Test Engineer
# ---------------------------------------------------------------------------
def test_scenario_3_implementer_plus_test_engineer(temp_repo, default_wb):
    a1 = AgentAssignment(
        assignment_id="s3-impl",
        role=AgentRole.IMPLEMENTER,
        objective="Implement feature core",
        allowed_mutation_paths=(Path("nexus/core.py"),),
        expected_deliverables=("Core patch",),
        acceptance_criteria=("Feature core done",),
        budget=default_wb,
    )
    a2 = AgentAssignment(
        assignment_id="s3-test",
        role=AgentRole.TEST_ENGINEER,
        objective="Develop tests for feature",
        dependencies=("s3-impl",),
        allowed_mutation_paths=(Path("nexus/test_core.py"),),
        expected_deliverables=("Test patch",),
        acceptance_criteria=("Tests created",),
        budget=default_wb,
    )

    orchestrator = LeadOrchestrator(
        run_id="run-s3",
        policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
        lead_workspace_root=temp_repo,
    )

    final_state = asyncio.run(orchestrator.run_collaboration([a1, a2]))
    assert final_state.state == CollaborationState.COMPLETED
    assert len(final_state.integration_result.applied_assignments) == 2


# ---------------------------------------------------------------------------
# Scenario 4 — Parallel Package Work
# ---------------------------------------------------------------------------
def test_scenario_4_parallel_package_work(temp_repo, default_wb):
    a1 = AgentAssignment(
        assignment_id="s4-p1",
        role=AgentRole.IMPLEMENTER,
        objective="Refactor package 1",
        allowed_mutation_paths=(Path("nexus/core.py"),),
        expected_deliverables=("Pkg1 patch",),
        acceptance_criteria=("Pkg1 clean",),
        budget=default_wb,
    )
    a2 = AgentAssignment(
        assignment_id="s4-p2",
        role=AgentRole.IMPLEMENTER,
        objective="Refactor package 2",
        allowed_mutation_paths=(Path("nexus/buffer.py"),),
        expected_deliverables=("Pkg2 patch",),
        acceptance_criteria=("Pkg2 clean",),
        budget=default_wb,
    )

    orchestrator = LeadOrchestrator(
        run_id="run-s4",
        policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
        lead_workspace_root=temp_repo,
    )

    final_state = asyncio.run(orchestrator.run_collaboration([a1, a2]))
    assert final_state.state == CollaborationState.COMPLETED


# ---------------------------------------------------------------------------
# Scenario 5 — Overlapping Mutations Detection
# ---------------------------------------------------------------------------
def test_scenario_5_overlapping_mutations(temp_repo, default_wb):
    registry = ScopeReservationRegistry()
    registry.reserve(
        assignment_id="a1",
        paths=(Path("nexus/core.py"),),
        symbol_ids=("main",),
        mode=ReservationMode.EXCLUSIVE,
    )

    with pytest.raises(ReservationConflictError):
        registry.reserve(
            assignment_id="a2",
            paths=(Path("nexus/core.py"),),
            symbol_ids=("main",),
            mode=ReservationMode.EXCLUSIVE,
        )


# ---------------------------------------------------------------------------
# Scenario 6 — Worker Timeout
# ---------------------------------------------------------------------------
def test_scenario_6_worker_timeout(temp_repo):
    short_wb = WorkerBudget(
        max_model_calls=1,
        max_tool_calls=1,
        max_tokens=100,
        max_cost_usd=Decimal("0.01"),
        max_wall_clock_seconds=0,  # Immediate timeout
    )
    a1 = AgentAssignment(
        assignment_id="s6-timeout",
        role=AgentRole.IMPLEMENTER,
        objective="Timeout assignment",
        expected_deliverables=("Patch",),
        acceptance_criteria=("Done",),
        budget=short_wb,
    )

    orchestrator = LeadOrchestrator(
        run_id="run-s6",
        policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
        lead_workspace_root=temp_repo,
    )

    final_state = asyncio.run(orchestrator.run_collaboration([a1]))
    assert final_state.state == CollaborationState.FAILED


# ---------------------------------------------------------------------------
# Scenario 7 — Malformed Worker Output Rejection
# ---------------------------------------------------------------------------
def test_scenario_7_malformed_worker_output(temp_repo):
    service = ResultReviewService(known_repository_revision="main")
    assignment = AgentAssignment(
        assignment_id="a-stub",
        role=AgentRole.IMPLEMENTER,
        objective="Implement feature",
        expected_deliverables=("Patch",),
        acceptance_criteria=("Done",),
    )
    malformed_result = AssignmentResult(
        assignment_id="a-stub",
        worker_id="w-0",
        status=AssignmentStatus.COMPLETED,
        summary="Short",  # <10 chars
        evidence=(),      # Missing evidence
    )

    review = service.review(malformed_result, assignment, "main")
    assert not review.accepted
    assert review.decision != ReviewDecision.APPROVE_FOR_INTEGRATION


# ---------------------------------------------------------------------------
# Scenario 8 — Integration Conflict Detection
# ---------------------------------------------------------------------------
def test_scenario_8_integration_conflict(temp_repo):
    coordinator = IntegrationCoordinator(current_revision="main", lead_workspace_root=temp_repo)
    r1 = AssignmentResult(
        assignment_id="a1",
        worker_id="w1",
        status=AssignmentStatus.COMPLETED,
        summary="Changes in core.py",
        proposed_changes=(
            {"change_id": "c1", "path": "nexus/core.py", "description": "Mod 1", "diff_reference": "diff1", "transaction_ref": None},
        ),
        evidence=("ev1",),
    )
    r2 = AssignmentResult(
        assignment_id="a2",
        worker_id="w2",
        status=AssignmentStatus.COMPLETED,
        summary="Conflicting changes in core.py",
        proposed_changes=(
            {"change_id": "c2", "path": "nexus/core.py", "description": "Mod 2", "diff_reference": "diff2", "transaction_ref": None},
        ),
        evidence=("ev2",),
    )
    reviews = {
        "a1": AssignmentReview(review_id="r1", assignment_id="a1", decision=ReviewDecision.APPROVE_FOR_INTEGRATION, accepted=True, integration_eligible=True),
        "a2": AssignmentReview(review_id="r2", assignment_id="a2", decision=ReviewDecision.APPROVE_FOR_INTEGRATION, accepted=True, integration_eligible=True),
    }

    res = coordinator.integrate([r1, r2], reviews)
    assert len(res.conflicts) > 0
    assert len(res.rejected_assignments) > 0


# ---------------------------------------------------------------------------
# Scenario 9 — Central Verification Failure
# ---------------------------------------------------------------------------
class FailingVerifier:
    def run_verification(self, context=None, checks=None):
        class Outcome:
            passed = False
        return Outcome()


def test_scenario_9_central_verification_failure(temp_repo):
    coordinator = IntegrationCoordinator(
        current_revision="main",
        verification_service=FailingVerifier(),
        lead_workspace_root=temp_repo,
    )
    r1 = AssignmentResult(
        assignment_id="a1",
        worker_id="w1",
        status=AssignmentStatus.COMPLETED,
        summary="Substantive summary of work done",
        proposed_changes=({"change_id": "c1", "path": "nexus/core.py", "description": "Mod 1", "diff_reference": "+# mod", "transaction_ref": None},),
        evidence=("ev1",),
    )
    reviews = {
        "a1": AssignmentReview(review_id="r1", assignment_id="a1", decision=ReviewDecision.APPROVE_FOR_INTEGRATION, accepted=True, integration_eligible=True),
    }

    res = coordinator.integrate([r1], reviews)
    assert res.status == IntegrationStatus.FAILED
    assert len(res.applied_assignments) == 0


# ---------------------------------------------------------------------------
# Scenario 10 — Collaboration Not Beneficial (Single-Agent Fallback)
# ---------------------------------------------------------------------------
def test_scenario_10_collaboration_not_beneficial():
    planner = DelegationPlanner()
    t_small = TaskCharacteristics(
        task_id="t-small",
        description="Fix typo in comment",
        estimated_files_affected=1,
        packages_involved=["nexus"],
        languages_involved=["python"],
        independent_workstreams=[],
        sequential_dependencies=[],
        estimated_context_tokens=1000,
        requires_security_review=False,
        requires_architecture_review=False,
        dependency_coupling_score=0.1,
        time_budget_seconds=60,
        financial_budget_usd=0.10,
        local_only=True,
        worker_isolation_available=True,
    )
    decision = planner.decide(t_small)
    assert not decision.use_collaboration
    assert decision.recommended_mode == CollaborationMode.SINGLE_AGENT


# ---------------------------------------------------------------------------
# Scenario 11 — Budget Pressure
# ---------------------------------------------------------------------------
def test_scenario_11_budget_pressure():
    restricted_budget = CollaborationBudget(
        maximum_workers=1,
        maximum_parallel_workers=1,
        maximum_total_model_calls=5,
        maximum_total_tool_calls=10,
        maximum_total_tokens=10000,
        maximum_total_cost_usd=Decimal("0.10"),
        maximum_wall_clock_seconds=60,
        maximum_worker_retries=1,
        maximum_reassignments=1,
    )
    planner = DelegationPlanner(policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL, budget=restricted_budget)
    t_large = TaskCharacteristics(
        task_id="t-large",
        description="Large multi-package feature",
        estimated_files_affected=10,
        packages_involved=["p1", "p2"],
        languages_involved=["python"],
        independent_workstreams=["w1", "w2"],
        sequential_dependencies=[],
        estimated_context_tokens=30000,
        requires_security_review=False,
        requires_architecture_review=False,
        dependency_coupling_score=0.1,
        time_budget_seconds=300,
        financial_budget_usd=2.0,
        local_only=True,
        worker_isolation_available=True,
    )
    decision = planner.decide(t_large)
    assert not decision.use_collaboration
    assert "Budget limits maximum workers to 1" in decision.reasons[0]


# ---------------------------------------------------------------------------
# Scenario 12 — Persistence and Resume
# ---------------------------------------------------------------------------
def test_scenario_12_persistence_and_resume(temp_repo):
    pdir = temp_repo / ".nexus" / "runs" / "run-s12" / "collaboration"
    orchestrator = LeadOrchestrator(
        run_id="run-s12",
        policy=CollaborationPolicyProfile.CONTROLLED_PARALLEL,
        lead_workspace_root=temp_repo,
        persistence_dir=pdir,
    )
    a1 = AgentAssignment(
        assignment_id="s12-a1",
        role=AgentRole.INVESTIGATOR,
        objective="Investigate",
        expected_deliverables=("Report",),
        acceptance_criteria=("Done",),
    )
    asyncio.run(orchestrator.run_collaboration([a1]))

    persistence = CollaborationPersistence(pdir)
    loaded_state = persistence.load()
    assert loaded_state is not None
    assert loaded_state.run_id == "run-s12"
    assert loaded_state.state == CollaborationState.COMPLETED
