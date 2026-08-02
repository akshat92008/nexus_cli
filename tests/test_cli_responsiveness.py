"""
Tests for CLI Responsiveness, Real-Time Action Streaming, and Non-Interactive Tool Execution
"""

import json
import os
from unittest.mock import patch

from nexus.nexus_runtime import NexusRuntime
from nexus.tools import execute_tool
from nexus.ui import LiveStatus, print_tool_call


def test_live_status_lifecycle():
    """Verify LiveStatus start, update, and stop execute cleanly without exceptions."""
    status = LiveStatus()
    status.start("Initial testing...")
    status.update("Drafting tool: edit_file(path='test.py')...")
    status.stop()
    assert not status._is_active


def test_tool_call_formatting():
    """Verify tool call arguments are formatted cleanly for display."""
    args = {
        "path": "nexus/cli.py",
        "old_text": "line1\nline2\nline3\nline4\nline5\n" * 10,
        "new_text": "new_line",
    }
    print_tool_call("edit_file", args)


def test_non_interactive_command_env():
    """Verify execute_tool('run_command') passes non-interactive environment variables."""
    variables = (
        "%CI% %PAGER% %DEBIAN_FRONTEND% %TERM%"
        if os.name == "nt"
        else "$CI $PAGER $DEBIAN_FRONTEND $TERM"
    )
    res = execute_tool("run_command", {"command": f"echo {variables}"})
    assert "true" in res
    assert "cat" in res
    assert "noninteractive" in res
    assert "dumb" in res


def test_agent_handle_stream_tool_drafting():
    """Verify NexusRuntime._handle_stream updates LiveStatus as tool call deltas arrive."""
    agent = NexusRuntime(api_key="nvapi-mock-key")

    class MockDeltaFunction:
        def __init__(self, name=None, arguments=None):
            self.name = name
            self.arguments = arguments

    class MockDeltaToolCall:
        def __init__(self, index=0, id="call_123", name=None, arguments=None):
            self.index = index
            self.id = id
            self.function = MockDeltaFunction(name, arguments)

    class MockDelta:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class MockChoice:
        def __init__(self, delta):
            self.delta = delta

    class MockChunk:
        def __init__(self, content=None, tool_calls=None):
            self.choices = [MockChoice(MockDelta(content, tool_calls))]
            self.usage = None

    mock_chunks = [
        MockChunk(tool_calls=[MockDeltaToolCall(0, "call_123", "edit_file", "")]),
        MockChunk(tool_calls=[MockDeltaToolCall(0, "call_123", None, '{"path": ')]),
        MockChunk(tool_calls=[MockDeltaToolCall(0, "call_123", None, '"nexus/agent.py"}')]),
    ]

    with patch("nexus.ui.LiveStatus.update") as mock_update:
        content, tool_calls = agent._handle_stream(mock_chunks)

    assert content == ""
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "edit_file"
    assert json.loads(tool_calls[0]["arguments"]) == {"path": "nexus/agent.py"}
    assert mock_update.called
