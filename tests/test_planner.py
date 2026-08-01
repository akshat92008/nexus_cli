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
