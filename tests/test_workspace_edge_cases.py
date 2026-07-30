"""Tests for Workspace edge cases and cross-platform behaviors."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from nexus.workspace import GitWorktreeSession, WorktreeError

def test_workspace_rejects_dirty_git(tmp_path: Path):
    ws_path = tmp_path / "dirty_repo"
    ws_path.mkdir()
    (ws_path / ".git").mkdir() # Make it look like a git repo
    
    with patch.object(GitWorktreeSession, "_git") as mock_git:
        mock_git.side_effect = lambda cmd: ws_path.as_posix() if "rev-parse" in cmd else "M file.txt\n"
        
        session = GitWorktreeSession(ws_path, "session-123", state_root=tmp_path / "state")
        with pytest.raises(WorktreeError, match="uncommitted changes"):
            session.create()


        # Since the class does mostly path manipulation via pathlib, it should not fail on init.

def test_workspace_merge_conflict_rejection(tmp_path: Path):
    ws_path = tmp_path / "conflict_repo"
    ws_path.mkdir()
    (ws_path / ".git").mkdir()
    
    with patch.object(GitWorktreeSession, "_git") as mock_git:
        mock_git.side_effect = lambda cmd: ws_path.as_posix() if "rev-parse" in cmd else "UU conflicting_file.txt\n"
        
        session = GitWorktreeSession(ws_path, "session-456", state_root=tmp_path / "state")
        with pytest.raises(WorktreeError, match="uncommitted changes"):
            session.create()
