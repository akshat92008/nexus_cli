"""
Regression tests for Agent-level safety enforcement.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import nexus.history as nexus_history
from nexus.agent import Agent


def _agent_for_tmp_path(tmp_path, monkeypatch) -> Agent:
    monkeypatch.setattr(nexus_history, "HISTORY_DIR", tmp_path / ".nexusai" / "history")
    return Agent(model_key="nova3b", working_dir=str(tmp_path))


def test_dangerous_command_requires_confirmation(tmp_path, monkeypatch):
    """DANGEROUS commands must not execute from the agent tool path."""
    target = tmp_path / "should_not_execute"
    target.mkdir()
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        result, success = agent._execute_tool_with_safety(
            "run_command",
            {"command": "rm -rf ./should_not_execute"},
        )
        repeated, repeated_success = agent._execute_tool_with_safety(
            "run_command",
            {"command": "rm -rf ./should_not_execute"},
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert not repeated_success
    assert "PENDING_CONFIRMATION" in result
    assert "danger-0001" in result
    assert "danger-0001" in repeated
    assert "not executed" in result
    assert target.is_dir()


def test_explicit_confirmation_executes_only_the_pending_call(tmp_path, monkeypatch):
    """A CLI confirmation id authorizes its exact stored operation once."""
    target = tmp_path / "confirmed_delete"
    target.mkdir()
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        pending, pending_success = agent._execute_tool_with_safety(
            "run_command",
            {"command": "rm -rf ./confirmed_delete"},
        )
        confirmed, confirmed_success = agent.confirm_pending_operation("danger-0001")
        expired, expired_success = agent.confirm_pending_operation("danger-0001")
    finally:
        os.chdir(old_cwd)

    assert not pending_success
    assert "PENDING_CONFIRMATION" in pending
    assert confirmed_success
    assert "$ rm -rf ./confirmed_delete" in confirmed
    assert not target.exists()
    assert not expired_success
    assert "expired" in expired


def test_cancelled_dangerous_call_never_executes(tmp_path, monkeypatch):
    """Cancelling removes a pending operation without dispatching it."""
    target = tmp_path / "cancelled_delete"
    target.mkdir()
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        agent._execute_tool_with_safety(
            "run_command",
            {"command": "rm -rf ./cancelled_delete"},
        )
        cancelled, cancel_success = agent.cancel_pending_operation("danger-0001")
    finally:
        os.chdir(old_cwd)

    assert cancel_success
    assert "not executed" in cancelled
    assert target.is_dir()


def test_nova_file_edits_require_nova_guardrail_metadata(tmp_path, monkeypatch):
    """Nova-backed file writes must have passed Nova guardrails before Nexus safety."""
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        result, success = agent._execute_tool_with_safety(
            "write_file",
            {"path": "unguarded.txt", "content": "hello"},
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "without a passing Nova guardrail verdict" in result
    assert not (tmp_path / "unguarded.txt").exists()


def test_nova_guarded_file_edit_still_uses_nexus_safety(tmp_path, monkeypatch):
    """A passed Nova verdict is not enough to bypass Nexus SafetyLayer."""
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        result, success = agent._execute_tool_with_safety(
            "write_file",
            {
                "path": "/etc/nova_should_not_write",
                "content": "hello",
                "_nova_guardrail": {"passed": True, "summary": "test"},
            },
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "BLOCKED" in result


def test_multi_edit_cannot_hide_an_outside_workspace_path(tmp_path, monkeypatch):
    """Every path in a batch is scope-checked, not just the top-level args."""
    outside = tmp_path.parent / f"outside-{tmp_path.name}.txt"
    outside.write_text("before\n")
    old_cwd = os.getcwd()
    try:
        agent = Agent(
            model_key="nova3b",
            working_dir=str(tmp_path),
            permission_mode="acceptEdits",
        )
        result, success = agent._execute_tool_with_safety(
            "multi_edit",
            {
                "edits": [
                    {"path": str(outside), "old_text": "before", "new_text": "after"},
                ],
                "_nova_guardrail": {"passed": True, "summary": "test"},
            },
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "PENDING_CONFIRMATION" in result
    assert outside.read_text() == "before\n"


def test_outside_workspace_is_confirmed_before_diff_preview(tmp_path, monkeypatch):
    """Out-of-scope files are not read while Nexus is constructing a preview."""
    outside = tmp_path.parent / f"private-{tmp_path.name}.txt"
    outside.write_text("private\n")
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)

        def fail_preview(*_args, **_kwargs):
            raise AssertionError("preview must not read an unapproved path")

        monkeypatch.setattr("nexus.agent.preview_mutation", fail_preview)
        result, success = agent._execute_tool_with_safety(
            "write_file",
            {
                "path": str(outside),
                "content": "changed\n",
                "_nova_guardrail": {"passed": True, "summary": "test"},
            },
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "PENDING_CONFIRMATION" in result
    assert outside.read_text() == "private\n"


def test_every_read_path_is_scoped_before_tool_dispatch(tmp_path, monkeypatch):
    """Multi-path read tools cannot bypass workspace confinement."""
    local = tmp_path / "local.txt"
    local.write_text("local\n")
    outside = tmp_path.parent / f"read-scope-{tmp_path.name}.txt"
    outside.write_text("outside\n")
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        result, success = agent._execute_tool_with_safety(
            "diff_files",
            {"file_a": str(local), "file_b": str(outside)},
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "PENDING_CONFIRMATION" in result
    assert "outside the current workspace" in result


def test_repository_policy_enforces_read_and_each_batched_write(tmp_path, monkeypatch):
    """Policy matching is per target, including reads and multi-file edits."""
    policy_dir = tmp_path / ".nexus"
    policy_dir.mkdir()
    (policy_dir / "policies.yml").write_text(
        "allow:\n"
        "  - write: src/**\n"
        "deny:\n"
        "  - read: secrets/**\n"
        "  - write: src/generated/**\n"
    )
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "token.txt").write_text("private\n")
    (tmp_path / "src" / "generated").mkdir(parents=True)
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n")
    (tmp_path / "src" / "generated" / "api.py").write_text("VALUE = 1\n")

    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        read_result, read_success = agent._execute_tool_with_safety(
            "read_file",
            {"path": "secrets/token.txt"},
        )
        write_result, write_success = agent._execute_tool_with_safety(
            "multi_edit",
            {
                "edits": [
                    {
                        "path": "src/app.py",
                        "old_text": "VALUE = 1",
                        "new_text": "VALUE = 2",
                    },
                    {
                        "path": "src/generated/api.py",
                        "old_text": "VALUE = 1",
                        "new_text": "VALUE = 2",
                    },
                ],
                "_nova_guardrail": {"passed": True, "summary": "test"},
            },
        )
    finally:
        os.chdir(old_cwd)

    assert not read_success
    assert "policy denies read" in read_result
    assert not write_success
    assert "policy denies write" in write_result
    assert (tmp_path / "src" / "app.py").read_text() == "VALUE = 1\n"


def test_package_install_uses_specific_policy_capability(tmp_path, monkeypatch):
    """Dependency-install commands can be denied independently of other commands."""
    policy_dir = tmp_path / ".nexus"
    policy_dir.mkdir()
    (policy_dir / "policies.yml").write_text(
        "allow:\n"
        "  - command: *\n"
        "deny:\n"
        "  - package_install: *\n"
    )
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        result, success = agent._execute_tool_with_safety(
            "run_command",
            {"command": "python -m pip install requests"},
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "policy denies package_install" in result


def test_common_network_commands_require_explicit_network_approval(
    tmp_path,
    monkeypatch,
):
    """Network intent is inferred for common clients instead of silently escaping."""
    old_cwd = os.getcwd()
    try:
        agent = _agent_for_tmp_path(tmp_path, monkeypatch)
        result, success = agent._execute_tool_with_safety(
            "run_process",
            {"argv": ["curl", "https://example.invalid"]},
        )
    finally:
        os.chdir(old_cwd)

    assert not success
    assert "PENDING_CONFIRMATION" in result
    assert "Network access is disabled by default" in result
