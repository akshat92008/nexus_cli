"""
Test suit for API resilience: key rotation and Groq failover.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from nexus.api import NvidiaClient, GROQ_MODEL_MAP, DEFAULT_GROQ_MODEL


@patch.dict(os.environ, {"GROQ_API_KEY": "fake_groq_key", "NVIDIA_FALLBACK_API_KEY_1": "fake_nvidia_key1", "NVIDIA_API_KEY": "fake_nvidia_key"})
def test_api_client_key_loading():
    """Verify that primary key, fallback keys, and Groq key are loaded."""
    client = NvidiaClient()
    assert len(client.nvidia_keys) >= 2
    assert client.groq_key == "fake_groq_key"


def test_groq_model_resolution():
    """Verify model mapping to Groq models for tool calling compatibility."""
    client = NvidiaClient()
    assert client.resolve_groq_model("z-ai/glm-5.2") == "llama-3.3-70b-versatile"
    assert client.resolve_groq_model("meta/llama-3.3-70b-instruct") == "llama-3.3-70b-versatile"
    assert client.resolve_groq_model("deepseek-ai/deepseek-v4-pro") == "llama-3.3-70b-versatile"
    assert client.resolve_groq_model("unknown-model") == DEFAULT_GROQ_MODEL


def test_client_timeout():
    """Verify client timeout defaults to 15.0s for resilience."""
    client = NvidiaClient()
    assert client.timeout == 15.0
    assert client.client.timeout == 15.0


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
