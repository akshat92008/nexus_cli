import os

import pytest

os.environ["NVIDIA_API_KEY"] = "test"
from nexus.agent import Agent
from nexus.planner import Difficulty, ExecutionPlan, IntentType, PlanStep, PlanType, TaskStatus


def test_advance_step_dependency_enforcement():
    plan = ExecutionPlan(
        id="test_plan",
        goal="test",
        intent=IntentType.BUILD,
        difficulty=Difficulty.SIMPLE,
        plan_type=PlanType.PLANNED,
        steps=[
            PlanStep(id=0, title="step 1", description="", depends_on=[]),
            PlanStep(id=1, title="step 2", description="", depends_on=[0]),
        ],
    )

    agent = Agent(working_dir=".", workspace_isolation=False)
    planner = agent.planner
    planner.current_plan = plan

    with pytest.raises(RuntimeError, match="dependency 0 is not complete"):
        planner.advance_step(1, TaskStatus.COMPLETED)

    planner.advance_step(0, TaskStatus.COMPLETED)
    planner.advance_step(1, TaskStatus.COMPLETED)
    assert plan.steps[1].status == TaskStatus.COMPLETED


def test_save_and_load_plan(tmp_path, monkeypatch):
    from nexus import planner as planner_module

    monkeypatch.setattr(planner_module, "PLANS_DIR", tmp_path)

    agent = Agent(working_dir=".", workspace_isolation=False)
    planner = agent.planner

    plan = ExecutionPlan(
        id="test_save_load",
        goal="test",
        intent=IntentType.BUILD,
        difficulty=Difficulty.SIMPLE,
        plan_type=PlanType.PLANNED,
        steps=[PlanStep(id=0, title="step 1", description="", depends_on=[])],
    )

    planner._save_plan(plan)
    loaded = planner.load_plan("test_save_load")

    assert loaded is not None
    assert loaded.id == plan.id
    assert loaded.steps[0].title == "step 1"


def test_massive_build_persists_product_architecture_and_subsystem_contracts(
    tmp_path, monkeypatch
):
    from nexus import planner as planner_module

    monkeypatch.setattr(planner_module, "PLANS_DIR", tmp_path)
    planner = planner_module.PlanningEngine()
    plan = planner.create_plan(
        "Build a complete production-ready multi-tenant commerce platform with database, "
        "API, authentication, payments, frontend, deployment, and observability",
        {
            "intent": IntentType.BUILD,
            "difficulty": Difficulty.MASSIVE,
            "plan_type": PlanType.PLANNED,
            "skills_needed": ["frontend", "backend", "database", "security", "devops"],
        },
    )

    assert plan.product_spec["delivery_mode"] == "single-prompt long-horizon execution"
    assert len(plan.architecture_decisions) >= 3
    assert {item["name"] for item in plan.subsystem_contracts} >= {
        "identity-and-tenancy",
        "core-domain",
        "data-platform",
        "api-and-integrations",
        "platform-and-observability",
    }
    assert all(step.phase for step in plan.steps)
    assert all("run_command" not in step.tools_needed for step in plan.steps)

    loaded = planner.load_plan(plan.id)
    assert loaded is not None
    assert loaded.product_spec == plan.product_spec
    assert loaded.subsystem_contracts == plan.subsystem_contracts


def test_failed_massive_step_creates_a_persisted_replan(tmp_path, monkeypatch):
    from nexus import planner as planner_module

    monkeypatch.setattr(planner_module, "PLANS_DIR", tmp_path)
    planner = planner_module.PlanningEngine()
    plan = ExecutionPlan(
        id="failure-replan",
        goal="Build the product",
        intent=IntentType.BUILD,
        difficulty=Difficulty.MASSIVE,
        plan_type=PlanType.PLANNED,
        steps=[
            PlanStep(
                id=0,
                title="Implement data",
                description="data",
                subsystem="data-platform",
            )
        ],
    )
    planner.current_plan = plan

    assert planner.advance_step(0, TaskStatus.FAILED, "migration rollback failed")
    assert plan.revision == 2
    assert plan.failure_replans[-1]["subsystem"] == "data-platform"
    assert "root cause" in plan.failure_replans[-1]["required_action"]
    assert planner.load_plan(plan.id).failure_replans == plan.failure_replans
