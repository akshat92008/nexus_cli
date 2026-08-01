import os

os.environ["NVIDIA_API_KEY"] = "test"
from nexus.agent import Agent
from nexus.pipeline import ExecutionPipeline, PipelineResult


def test_pipeline_preserves_ledger_and_emits_hooks():
    agent = Agent(working_dir=".", workspace_isolation=False)
    pipeline = ExecutionPipeline(agent)

    def mock_analyze(*args, **kwargs):
        return {"plan_type": "direct", "intent": "build", "skills_needed": []}

    def mock_turn(*args, **kwargs):
        return "", []

    agent.planner.analyze = mock_analyze
    agent._run_hosted_turn = mock_turn

    result = pipeline.run("Test simple pipeline without plan", interactive=False)

    assert isinstance(result, PipelineResult)
    assert [item.stage.value for item in result.stage_results] == [
        "repo_understanding",
        "planning",
        "context_selection",
        "model_routing",
        "execution",
        "verification",
        "review",
        "evidence",
        "completion",
    ]
    assert result.status == "UNVERIFIED"
    assert result.outcome == "NO_CHANGES"
    assert result.success is False
    assert agent.run_ledger.resume_summary()["final_report"]["status"] == "UNVERIFIED"
