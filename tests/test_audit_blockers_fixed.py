from __future__ import annotations

from types import SimpleNamespace

from nexus.nexus_runtime import NexusRuntime
from nexus.execution_engine import ExecutionEngine
from nexus.planner import Difficulty, IntentType, PlanningEngine
from nexus.preflight import probe_hosted
from nexus.run_state import RunStatus


def test_repo_summary_aliases_activate_large_repo_planning(tmp_path):
    for index in range(12):
        (tmp_path / f"m{index}.py").write_text(f"def f{index}():\n    return {index}\n")
    agent = NexusRuntime(api_key="dummy", working_dir=str(tmp_path), workspace_isolation=False)
    agent.repo_graph.build(force=True)
    summary = agent.repo_graph.summary()
    assert summary["files"] == summary["total_files"]
    assert summary["symbols"] == summary["total_symbols"]
    analysis = {
        "intent": IntentType.REFACTOR,
        "difficulty": Difficulty.COMPLEX,
        "skills_needed": ["backend"],
    }
    plan = agent.planner.create_plan("Refactor modules safely", analysis, repo_summary=summary)
    assert plan.steps[0].title == "Understand Repository (Mandatory)"


def test_non_git_workspace_is_indexed(tmp_path):
    (tmp_path / "app.py").write_text("VALUE = 1\n")
    agent = NexusRuntime(api_key="dummy", working_dir=str(tmp_path), workspace_isolation=False)
    result = ExecutionEngine(agent)._stage_repo_understanding()
    assert result.success is True
    assert agent.repo_graph.summary()["files"] >= 1


def test_planning_failure_fails_closed(tmp_path, monkeypatch):
    agent = NexusRuntime(api_key="dummy", working_dir=str(tmp_path), workspace_isolation=False)
    def fail(_prompt):
        raise RuntimeError("boom")
    monkeypatch.setattr(agent.planner, "analyze", fail)
    result = ExecutionEngine(agent).run("Refactor authentication across the repository")
    assert result.status == RunStatus.BLOCKED.value
    assert result.response.startswith("BLOCKED: Planning failed safely")


def test_finalizer_uses_agent_turn_evidence_marker(tmp_path):
    agent = NexusRuntime(api_key="dummy", working_dir=str(tmp_path), workspace_isolation=False)
    agent.evidence.append(
        kind="verification_check",
        claim="old pass",
        status="verified",
        metadata={"check_type": "test"},
    )
    analysis = {
        "intent": IntentType.TEST,
        "difficulty": Difficulty.SIMPLE,
        "plan_type": "direct",
        "skills_needed": [],
    }
    agent._begin_managed_run("new turn", analysis, None)
    report = agent._run_finalizer.finish("done", [])
    assert report["metadata"]["evidence_start"] == 1
    assert report["metadata"]["verification_records"] == 0
    assert report["status"] != RunStatus.VERIFIED.value


def test_remote_plain_http_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("NEXUS_OPENAI_BASE_URL", "http://provider.example/v1")
    monkeypatch.setenv("NEXUS_OPENAI_API_KEY", "x")
    probe = probe_hosted()
    assert probe.ready is False
    assert probe.code == "plaintext_remote_endpoint"


def test_step_criteria_remain_narrow():
    planner = PlanningEngine()
    criteria = [
        "The requested objective is implemented.",
        "Project tests pass.",
        "No unrelated files are changed.",
    ]
    step = SimpleNamespace(title="Implement token validation", description="Change auth behavior")
    selected = planner._step_acceptance_criteria(step, criteria)
    assert "The requested objective is implemented." in selected
    assert "Project tests pass." not in selected
    assert "No unrelated files are changed." in selected


def test_project_dotenv_does_not_mutate_parent_environment(tmp_path, monkeypatch):
    from nexus.api import _load_env_file

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MALICIOUS_REPO_VALUE", raising=False)
    (tmp_path / ".env").write_text("MALICIOUS_REPO_VALUE=owned\n", encoding="utf-8")

    runtime_env = _load_env_file()

    assert "MALICIOUS_REPO_VALUE" not in runtime_env
    assert "MALICIOUS_REPO_VALUE" not in __import__("os").environ


def test_abandoned_stream_finalizes_provider_telemetry():
    from nexus.api import _ObservedStream

    statuses = []
    stream = _ObservedStream(iter([object(), object()]), lambda status, _meta: statuses.append(status))
    next(iter(stream))
    stream.close()

    assert statuses == ["cancelled"]
