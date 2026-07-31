"""Opt-in Git worktree isolation for Nexus modifying sessions."""

from __future__ import annotations

import json
import re
import shutil
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
    backend: str = "git-worktree"


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
        if not (self.repository / ".git").exists():
            return self._create_temporary_copy()
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

    def _create_temporary_copy(self) -> WorktreeInfo:
        """Isolate a greenfield/non-Git directory with a persistent temporary copy."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        def ignore(_directory: str, names: list[str]) -> set[str]:
            return {
                name
                for name in names
                if name
                in {
                    ".git",
                    ".nexusai",
                    ".pytest_cache",
                    ".ruff_cache",
                    "__pycache__",
                    "node_modules",
                    ".venv",
                    "venv",
                    "dist",
                    "build",
                }
            }

        try:
            shutil.copytree(self.repository, self.path, ignore=ignore)
        except OSError as exc:
            raise WorktreeError(f"Could not create temporary isolated copy: {exc}") from exc
        self.info = WorktreeInfo(
            source_repository=str(self.repository),
            path=str(self.path),
            base_commit="",
            branch="",
            created_at=datetime.now(timezone.utc).isoformat(),
            backend="temporary-copy",
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
        if self.info.backend != "git-worktree":
            return {
                **asdict(self.info),
                "git_status": "Non-Git source isolated in a persistent temporary copy.",
            }
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

    def diff(self) -> str:
        """Return the unified diff of changes in the worktree."""
        if not self.info:
            return ""
        if self.info.backend == "git-worktree":
            result = subprocess.run(
                ["git", "diff", self.info.base_commit],
                cwd=self.path,
                capture_output=True,
                text=True,
            )
            return result.stdout
        else:
            # Python-native unified diff — cross-platform, no Unix diff required
            import difflib
            lines: list[str] = []
            src = self.path
            dst = self.repository
            _ignore = {
                ".git", ".nexusai", ".pytest_cache", "__pycache__",
                "node_modules", ".venv", "venv", "dist", "build",
            }

            def _collect_files(base: "Path") -> list["Path"]:
                out = []
                for entry in base.rglob("*"):
                    if entry.is_file() and not any(
                        part in _ignore for part in entry.parts
                    ):
                        out.append(entry)
                return out

            src_files = {f.relative_to(src) for f in _collect_files(src)}
            dst_files = {f.relative_to(dst) for f in _collect_files(dst)}

            for rel in sorted(src_files | dst_files):
                src_f = src / rel
                dst_f = dst / rel
                src_lines = src_f.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if src_f.exists() else []
                dst_lines = dst_f.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) if dst_f.exists() else []
                diff_lines = list(difflib.unified_diff(
                    dst_lines, src_lines,
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                ))
                lines.extend(diff_lines)

            return "".join(lines)

    def apply(self) -> None:
        """Apply changes from the worktree back to the source repository safely.

        For Git worktrees:
          1. Re-checks the source repository for uncommitted changes (so concurrent
             edits do not silently corrupt the merge).
          2. Creates an immutable backup ref before merging.
          3. On merge failure, runs ``git merge --abort`` automatically.

        For temporary copies:
          Uses Python's shutil (cross-platform) instead of rsync.

        Raises:
            WorktreeError: On any failure. The source repository is left in a
                clean, mergeable state.
        """
        if not self.info:
            return
        if self.info.backend == "git-worktree":
            # ── Pre-apply safety check ────────────────────────────────────
            dirty_now = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repository,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if dirty_now:
                raise WorktreeError(
                    "Source repository has uncommitted changes since the workspace was "
                    "created. Commit or stash them before applying workspace changes."
                )

            # ── Auto-commit any uncommitted worktree changes ──────────────
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.path,
                capture_output=True,
                text=True,
            )
            if status.stdout.strip():
                subprocess.run(["git", "add", "-A"], cwd=self.path, check=True)
                subprocess.run(
                    ["git", "commit", "-m", "Nexus workspace apply"],
                    cwd=self.path,
                    check=True,
                )

            # ── Create backup ref before merge ────────────────────────────
            backup_ref = f"refs/nexus/pre-apply-{self.session_id}"
            head_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repository,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "update-ref", backup_ref, head_sha],
                cwd=self.repository,
                capture_output=True,
            )

            # ── Merge with automatic abort on failure ─────────────────────
            result = subprocess.run(
                ["git", "merge", self.info.branch, "--no-edit"],
                cwd=self.repository,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                # Auto-abort to leave the source repository clean
                subprocess.run(
                    ["git", "merge", "--abort"],
                    cwd=self.repository,
                    capture_output=True,
                )
                raise WorktreeError(
                    f"Failed to merge branch '{self.info.branch}': "
                    f"{result.stderr or result.stdout}\n"
                    f"The source repository has been automatically restored. "
                    f"Backup ref is available at {backup_ref}."
                )
        else:
            # ── Python-native sync (cross-platform, no rsync required) ────
            import shutil as _shutil

            src = self.path
            dst = self.repository
            _ignore = {
                ".git", ".nexusai", ".pytest_cache", ".ruff_cache",
                "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
            }

            def _sync(src_dir: "Path", dst_dir: "Path") -> None:
                dst_dir.mkdir(parents=True, exist_ok=True)
                src_names = {e.name for e in src_dir.iterdir()}
                for entry in src_dir.iterdir():
                    if entry.name in _ignore:
                        continue
                    dst_entry = dst_dir / entry.name
                    if entry.is_dir():
                        _sync(entry, dst_entry)
                    else:
                        _shutil.copy2(str(entry), str(dst_entry))
                # Remove files in dst that are absent in src (mirrors rsync --delete)
                if dst_dir.exists():
                    for entry in dst_dir.iterdir():
                        if entry.name not in src_names and entry.name not in _ignore:
                            if entry.is_dir():
                                _shutil.rmtree(entry, ignore_errors=True)
                            else:
                                entry.unlink(missing_ok=True)

            try:
                _sync(src, dst)
            except OSError as exc:
                raise WorktreeError(f"Failed to sync temporary copy: {exc}") from exc

    def discard(self) -> None:
        """Discard the worktree or temporary copy and clean up metadata."""
        if not self.info:
            return
        if self.info.backend == "git-worktree":
            subprocess.run(
                ["git", "worktree", "remove", "--force", self.path],
                cwd=self.repository,
                capture_output=True,
            )
            subprocess.run(
                ["git", "branch", "-D", self.info.branch],
                cwd=self.repository,
                capture_output=True,
            )
        else:
            if Path(self.path).exists():
                shutil.rmtree(self.path, ignore_errors=True)
        if self.info_path.exists():
            self.info_path.unlink(missing_ok=True)
        self.info = None


class WorkspaceManager:
    """Manages global isolation sessions for Nexus."""
    
    def __init__(self, state_root: str | Path | None = None):
        root = Path(state_root).expanduser().resolve() if state_root else nexus_home()
        self.worktrees_dir = root / "worktrees"
        
    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all active isolated worktrees."""
        if not self.worktrees_dir.exists():
            return []
        
        results = []
        for p in self.worktrees_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append(WorktreeInfo(**data))
            except Exception:
                pass
        
        # Sort by creation time descending
        results.sort(key=lambda w: w.created_at, reverse=True)
        return results
        
    def resolve_worktree(self, session_id: str) -> GitWorktreeSession | None:
        """Resolve a specific session ID to an active worktree session."""
        info_path = self.worktrees_dir / f"{session_id}.json"
        if not info_path.exists():
            return None
            
        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
            info = WorktreeInfo(**data)
            session = GitWorktreeSession(info.source_repository, session_id)
            session.info = info
            session.path = Path(info.path)
            return session
        except Exception:
            return None
