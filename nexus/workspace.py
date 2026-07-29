"""Opt-in Git worktree isolation for Nexus modifying sessions."""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from nexus.paths import nexus_home


class WorktreeError(RuntimeError):
    """Raised when an isolated workspace cannot be created safely."""


@dataclass
class WorktreeInfo:
    source_repository: str
    path: str
    base_commit: str
    branch: str
    created_at: str


class GitWorktreeSession:
    """Create a dedicated branch and worktree without changing the source tree."""

    def __init__(
        self,
        repository: str | Path,
        session_id: str,
        *,
        state_root: str | Path | None = None,
    ):
        self.repository = Path(repository).expanduser().resolve()
        self.session_id = session_id
        root = Path(state_root).expanduser().resolve() if state_root else nexus_home()
        try:
            root.relative_to(self.repository)
            root = Path(tempfile.gettempdir()) / "nexus-worktrees"
        except ValueError:
            pass
        self.path = root / "worktrees" / session_id
        self.info_path = root / "worktrees" / f"{session_id}.json"
        self.info: WorktreeInfo | None = None

    def create(self) -> WorktreeInfo:
        """Create and return an isolated worktree on a dedicated branch."""
        if self.path.exists():
            raise WorktreeError(f"Worktree path already exists: {self.path}")
        top = self._git(["rev-parse", "--show-toplevel"]).strip()
        if Path(top).resolve() != self.repository:
            raise WorktreeError(
                f"Working directory must be the Git repository root: {self.repository}"
            )
        dirty = self._git(["status", "--porcelain"]).strip()
        if dirty:
            raise WorktreeError(
                "Source repository has uncommitted changes. Commit or stash them "
                "before starting an isolated worktree so no work is silently omitted."
            )
        base_commit = self._git(["rev-parse", "HEAD"]).strip()
        branch_suffix = re.sub(r"[^A-Za-z0-9._-]+", "-", self.session_id).strip("-")
        branch = f"nexus/{branch_suffix}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "git",
            "worktree",
            "add",
            "-b",
            branch,
            str(self.path),
            base_commit,
        ]
        result = subprocess.run(
            command,
            cwd=self.repository,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise WorktreeError((result.stderr or result.stdout).strip())

        self.info = WorktreeInfo(
            source_repository=str(self.repository),
            path=str(self.path),
            base_commit=base_commit,
            branch=branch,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.info_path.write_text(
            __import__("json").dumps(asdict(self.info), indent=2) + "\n",
            encoding="utf-8",
        )
        return self.info

    def status(self) -> dict[str, str]:
        """Return branch and diff status without mutating either worktree."""
        if not self.info:
            return {}
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=self.path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            **asdict(self.info),
            "git_status": (result.stdout or result.stderr).strip(),
        }

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise WorktreeError((result.stderr or result.stdout).strip())
        return result.stdout
