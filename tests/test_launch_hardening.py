"""Regression coverage for the public-launch hardening layer."""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.agent import Agent
from nexus.benchmark import BenchmarkRunner, BenchmarkSuite
from nexus.budget import BudgetController, BudgetedClient, BudgetLimits
from nexus.nova_backend import NovaBackendResult, NovaToolProposal
from nexus.pipeline import ExecutionPipeline
from nexus.planner import IntentType
from nexus.policy import get_mode_policy
from nexus.preflight import BackendProbe
from nexus.tools import tool_web_fetch


def test_web_fetch_blocks_non_http_and_loopback_urls():
    assert "blocked" in tool_web_fetch("file:///etc/passwd").lower()
    assert "blocked" in tool_web_fetch("http://127.0.0.1:8080/admin").lower()
    assert "loopback" in tool_web_fetch("http://127.0.0.1:8080/admin").lower()


def test_custom_model_requires_explicit_provider_model_id(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_MODEL_ID", raising=False)
    with pytest.raises(ValueError, match="require --model-id"):
        Agent(model_key="custom", working_dir=str(tmp_path))


def test_hosted_agent_does_not_require_nova(tmp_path):
    agent = Agent(
        api_key="test",
        model_key="glm-5.2",
        working_dir=str(tmp_path),
        local_intern_mode="off",
    )
    assert agent.local_intern_enabled is False
    assert agent._should_use_two_node({"intent": IntentType.FIX}) is False


def test_auto_local_intern_activates_only_after_successful_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nexus.preflight.probe_ollama",
        lambda *_args, **_kwargs: BackendProbe(True, "ollama", "ready", "available"),
    )
    agent = Agent(
        api_key="test",
        model_key="glm-5.2",
        working_dir=str(tmp_path),
        local_intern_mode="auto",
    )
    assert agent.local_intern_enabled is True
    assert agent._should_use_two_node({"intent": IntentType.FIX}) is True


def test_plugin_activation_is_explicit(tmp_path):
    disabled = Agent(api_key="test", working_dir=str(tmp_path), plugins_enabled=False)
    enabled = Agent(api_key="test", working_dir=str(tmp_path), plugins_enabled=True)
    assert disabled._plugins_enabled is False
    assert enabled._plugins_enabled is True


def test_budget_estimates_usage_when_provider_omits_it():
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="implemented successfully", tool_calls=[])
            )
        ]
    )

    class Client:
        def chat(self, *args, **kwargs):
            return response

    controller = BudgetController(BudgetLimits(max_hosted_calls=1))
    client = BudgetedClient(Client(), controller)
    client.chat(
        model_id="test",
        messages=[{"role": "user", "content": "fix the test"}],
        stream=False,
    )
    usage = controller.snapshot()["usage"]
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0


def test_custom_openai_compatible_model_initializes(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_OPENAI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("NEXUS_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("NEXUS_MODEL_ID", "vendor/frontier-model")
    agent = Agent(model_key="custom", working_dir=str(tmp_path))
    assert agent.model_cfg["id"] == "vendor/frontier-model"
    assert agent.client.model_id == "hosted"


def test_no_tools_is_applied_inside_agent_configuration(tmp_path):
    agent = Agent(
        api_key="test",
        working_dir=str(tmp_path),
        tools_enabled=False,
    )
    assert agent.model_cfg["supports_tools"] is False
    assert agent._get_tools() is None


def test_benchmark_reports_local_backend_preflight_failure(
    tmp_path: Path,
    monkeypatch,
):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "main.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = tmp_path / "suite.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "nexus.benchmark.v1",
                "name": "preflight",
                "tasks": [
                    {
                        "id": "one",
                        "category": "single-file-edit",
                        "prompt": "Change the output",
                        "repository": str(repository),
                        "verification": [["python", "main.py"]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_MODEL", "nova")

    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    report = BenchmarkRunner(BenchmarkSuite.load(manifest)).run()
    result = report.results[0]
    assert result.status == "INVALID_CONFIGURATION"
    assert result.failure_phase == "provider_preflight"
    assert result.environment_failure is True
    assert "ollama" in result.detail.lower()


def test_web_app_propagates_runtime_options(tmp_path):
    from nexus.webapp import server

    server.create_app(
        api_key="test",
        model="glm-5.2",
        working_dir=str(tmp_path),
        model_id_override="provider/frontier",
        local_intern_mode="off",
        enable_nova_fallback=False,
        plugins_enabled=False,
        tools_enabled=False,
    )
    agent = server._get_agent("launch-test")
    assert agent.model_cfg["id"] == "provider/frontier"
    assert agent.local_intern_mode == "off"
    assert agent.local_intern_enabled is False
    assert agent.model_cfg["supports_tools"] is False
    assert "launch-test" in server._agent_locks


def test_custom_endpoint_preflight_rejects_unsafe_scheme(monkeypatch):
    from nexus.preflight import probe_hosted

    monkeypatch.setenv("NEXUS_OPENAI_BASE_URL", "file:///tmp/provider")
    monkeypatch.setenv("NEXUS_OPENAI_API_KEY", "test")
    result = probe_hosted()
    assert result.ready is False
    assert result.code == "custom_url_invalid"


def test_direct_nova_executes_declared_test_and_reaches_verified_status(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("NEXUS_HOME", str(tmp_path / "state"))
    (tmp_path / "verify.py").write_text(
        "from answer import ANSWER\nassert ANSWER == 42\n",
        encoding="utf-8",
    )
    result = NovaBackendResult(
        raw_output="guarded model response",
        assistant_text="Implemented answer.py and declared its acceptance test.",
        guardrail_output="all deterministic gates passed",
        test_command=f"{sys.executable} verify.py",
        proposals=[
            NovaToolProposal(
                name="write_file",
                args={
                    "path": "answer.py",
                    "content": "ANSWER = 42\n",
                    "_nova_guardrail": {"passed": True, "summary": "validated"},
                },
                source_path="answer.py",
                guardrail_summary="validated",
            )
        ],
    )
    monkeypatch.setattr("nexus.nova_backend.NovaPipelineBackend.run", lambda *_args: result)
    agent = Agent(
        model_key="nova3b",
        working_dir=str(tmp_path),
        permission_mode="acceptEdits",
        mode_policy=get_mode_policy("autonomous"),
        workspace_isolation=False,
    )

    pipeline_result = ExecutionPipeline(agent).run("Create answer.py with ANSWER = 42")
    report = agent.run_ledger.resume_summary()["final_report"]
    test_checks = [
        item for item in agent.evidence.records() if item.get("tool") == "model_declared_test"
    ]

    assert (tmp_path / "answer.py").read_text(encoding="utf-8") == "ANSWER = 42\n"
    assert test_checks[-1]["status"] == "verified"
    assert test_checks[-1]["exit_code"] == 0
    assert pipeline_result.success is True
    assert report["status"] == "VERIFIED"
    assert report["outcome"] == "COMPLETED_VERIFIED"
    assert report["metadata"]["model_calls"] == 1
    assert report["metadata"]["tests_executed"] >= 2
