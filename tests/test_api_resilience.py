"""
Test suit for API resilience: key rotation and Groq failover.
"""

import os
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from nexus.api import DEFAULT_GROQ_MODEL, NvidiaClient
from nexus.two_node_backend import CeilingCallTimeout, _run_ceiling_call


@pytest.fixture(autouse=True)
def provider_keys(monkeypatch):
    """Keep resilience tests independent of a developer's local .env file."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")


@patch.dict(
    os.environ,
    {
        "GROQ_API_KEY": "fake_groq_key",
        "NVIDIA_FALLBACK_API_KEY_1": "fake_nvidia_key1",
        "NVIDIA_API_KEY": "fake_nvidia_key",
    },
)
def test_api_client_key_loading():
    """Verify that primary key, fallback keys, and Groq key are loaded."""
    client = NvidiaClient()
    assert len(client.nvidia_keys) >= 2
    assert client.groq_key == "fake_groq_key"


def test_groq_model_resolution():
    """Verify model mapping to Groq models for tool calling compatibility."""
    client = NvidiaClient()
    assert client.resolve_groq_model("z-ai/glm-5.2") == "openai/gpt-oss-120b"
    assert client.resolve_groq_model("meta/llama-3.3-70b-instruct") == "llama-3.3-70b-versatile"
    assert client.resolve_groq_model("deepseek-ai/deepseek-v4-pro") == "openai/gpt-oss-120b"
    assert client.resolve_groq_model("unknown-model") == DEFAULT_GROQ_MODEL


def test_client_timeout():
    """Verify hosted inference gets enough time to produce a first token."""
    client = NvidiaClient()
    assert client.timeout == 60.0
    assert client.client.timeout == 60.0


def test_groq_only_configuration_is_supported(monkeypatch):
    """A Groq key is sufficient to start the hosted client."""
    for name in list(os.environ):
        if name.startswith(("NVIDIA_API_KEY", "NVIDIA_FALLBACK_API_KEY")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-only")
    monkeypatch.setattr("nexus.api._load_env_file", lambda: None)

    client = NvidiaClient()

    assert client.nvidia_keys == []
    assert client.groq_keys == ["gsk-only"]
    assert str(client.client.base_url) == "https://api.groq.com/openai/v1/"


def test_openrouter_only_configuration_is_supported(monkeypatch):
    """An OpenRouter key is sufficient to start the hosted client."""
    for name in list(os.environ):
        if name.startswith(
            (
                "NVIDIA_API_KEY",
                "NVIDIA_FALLBACK_API_KEY",
                "GROQ_API_KEY",
                "GROQ_FALLBACK_API_KEY",
            )
        ):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-only")
    monkeypatch.setattr("nexus.api._load_env_file", lambda: None)

    client = NvidiaClient()

    assert client.nvidia_keys == []
    assert client.groq_keys == []
    assert str(client.client.base_url) == "https://openrouter.ai/api/v1/"


def test_groq_fallback_execution():
    """Verify that when NVIDIA attempts fail, it automatically falls back to Groq."""
    client = NvidiaClient()

    # Mock _get_nvidia_client to raise TimeoutError
    def mock_nvidia_fail(key):
        m = MagicMock()
        m.chat.completions.create.side_effect = TimeoutError("Request timed out.")
        return m

    # Mock Groq client to return success
    mock_groq_response = MagicMock()
    mock_groq_response.choices = [MagicMock(message=MagicMock(content="Groq fallback success!"))]

    mock_groq_instance = MagicMock()
    mock_groq_instance.chat.completions.create.return_value = mock_groq_response

    with patch.object(client, "_get_nvidia_client", side_effect=mock_nvidia_fail):
        with patch.object(client, "_get_groq_client", return_value=mock_groq_instance):
            resp = client.chat_sync(
                model_id="z-ai/glm-5.2",
                messages=[{"role": "user", "content": "hello"}],
            )
            assert resp.choices[0].message.content == "Groq fallback success!"


def test_active_round_robin_key_rotation():
    """Verify that successful requests advance current_key_idx in a Round-Robin cycle."""
    client = NvidiaClient()
    client.nvidia_keys = ["key1", "key2", "key3"]
    client.current_key_idx = 0

    mock_resp = MagicMock()

    def mock_nvidia_success(key):
        m = MagicMock()
        m.chat.completions.create.return_value = mock_resp
        return m

    with patch.object(client, "_get_nvidia_client", side_effect=mock_nvidia_success):
        # Call 1 -> Uses key1 (idx 0), advances current_key_idx to 1
        client.chat(model_id="test", messages=[{"role": "user", "content": "hello"}], stream=False)
        assert client.current_key_idx == 1

        # Call 2 -> Uses key2 (idx 1), advances current_key_idx to 2
        client.chat(model_id="test", messages=[{"role": "user", "content": "hello"}], stream=False)
        assert client.current_key_idx == 2

        # Call 3 -> Uses key3 (idx 2), advances current_key_idx to 0
        client.chat(model_id="test", messages=[{"role": "user", "content": "hello"}], stream=False)
        assert client.current_key_idx == 0


def test_cloud_api_exhaustion_falls_back_to_local_nova():
    """Verify that when all cloud APIs fail, agent.run falls back to local Nova turn."""
    from nexus.agent import Agent

    agent = Agent(api_key="nvapi-test", model_key="deepseek-v4", enable_nova_fallback=True)
    agent.local_intern_enabled = True

    # Mock client.chat to simulate cloud rate limit exhaustion on a chat query
    with patch.object(
        agent.client, "chat", side_effect=RuntimeError("Rate limited after multiple retries")
    ):
        with patch.object(
            agent, "_run_nova_turn", return_value=("Local Nova fallback response", [])
        ) as mock_nova:
            res = agent.run("hello, explain binary search trees")
            assert res == "Local Nova fallback response"
            mock_nova.assert_called_once()


def test_round_robin_key_pool():
    """Verify explicit RoundRobinKeyPool cycling and cooldown skipping."""
    from nexus.api import NvidiaClient, RoundRobinKeyPool

    pool = RoundRobinKeyPool(["k1", "k2", "k3"])
    assert pool.get_next_key() == "k1"
    assert pool.get_next_key() == "k2"
    assert pool.get_next_key() == "k3"
    assert pool.get_next_key() == "k1"

    # Mark k1 in cooldown
    pool.mark_cooldown("k1", duration=60.0)
    assert pool.is_cooldown("k1") is True
    # Should skip k1 and return k2
    assert pool.get_next_key() == "k2"

    client = NvidiaClient()
    client.nvidia_keys = ["keyA", "keyB"]
    client.nvidia_pool = RoundRobinKeyPool(client.nvidia_keys)
    assert client.get_next_key("nvidia") == "keyA"
    assert client.get_next_key("nvidia") == "keyB"


def test_ceiling_timeout_works_outside_main_thread():
    result = {}

    def run():
        try:
            _run_ceiling_call(lambda: time.sleep(0.1), 0.01)
        except CeilingCallTimeout:
            result["timed_out"] = True

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert result == {"timed_out": True}
