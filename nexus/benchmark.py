"""Reproducible, versioned benchmark runner for Nexus engineering tasks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus import __version__
from nexus.sandbox import CommandSpec, SandboxRunner

BENCHMARK_SCHEMA_VERSION = "nexus.benchmark.v1"
RESULT_SCHEMA_VERSION = "nexus.benchmark-result.v1"
SUPPORTED_CATEGORIES = {
    "single-file-edit",
    "bug-repair",
    "feature-implementation",
    "multi-file-refactor",
    "dependency-migration",
    "test-generation",
    "repository-debugging",
    "ui-implementation",
    "api-development",
    "security-repair",
}


@dataclass(frozen=True)
class BenchmarkTask:
    """One isolated repository task and its deterministic acceptance checks."""

    id: str
    category: str
    prompt: str
    repository: str
    verification: tuple[tuple[str, ...], ...]
    timeout_seconds: int = 900
    allowed_paths: tuple[str, ...] = ()
    expected_changed_files: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any], base: Path) -> "BenchmarkTask":
        task_id = str(value.get("id", "")).strip()
        category = str(value.get("category", "")).strip()
        prompt = str(value.get("prompt", "")).strip()
        repository_value = str(value.get("repository", "")).strip()
        if not task_id or not prompt or not repository_value:
            raise ValueError("Each benchmark task requires id, prompt, and repository")
        repository = Path(repository_value).expanduser()
        if not repository.is_absolute():
            repository = (base / repository).resolve()
        verification = value.get("verification", [])
        if category not in SUPPORTED_CATEGORIES:
            raise ValueError(f"Unsupported benchmark category for {task_id}: {category}")
        if not isinstance(verification, list) or not verification:
            raise ValueError(f"Benchmark task {task_id} requires verification commands")
        commands: list[tuple[str, ...]] = []
        for command in verification:
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(item, str) and item for item in command)
            ):
                raise ValueError(
                    f"Benchmark task {task_id} verification must use argv arrays"
                )
            commands.append(tuple(command))
        return cls(
            id=task_id,
            category=category,
            prompt=prompt,
            repository=str(repository),
            verification=tuple(commands),
            timeout_seconds=max(30, int(value.get("timeout_seconds", 900))),
            allowed_paths=tuple(str(item) for item in value.get("allowed_paths", [])),
            expected_changed_files=tuple(
                str(item) for item in value.get("expected_changed_files", [])
            ),
        )


@dataclass
class BenchmarkTaskResult:
    task_id: str
    category: str
    status: str
    duration_ms: int
    nexus_exit_code: int | None = None
    verification: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    unexpected_files: list[str] = field(default_factory=list)
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float | None = None
    retries: int = 0
    human_intervention: bool = False
    recovery_succeeded: bool | None = None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status in {"PASSED", "VALID"}


@dataclass
class BenchmarkReport:
    suite: str
    nexus_version: str
    started_at: str
    completed_at: str
    results: list[BenchmarkTaskResult]
    schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        passed = sum(item.passed for item in self.results)
        return {
            "schema_version": self.schema_version,
            "suite": self.suite,
            "nexus_version": self.nexus_version,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "summary": {
                "tasks": len(self.results),
                "passed": passed,
                "failed": len(self.results) - passed,
                "success_rate": (
                    round(passed / len(self.results), 4) if self.results else 0.0
                ),
                "total_duration_ms": sum(item.duration_ms for item in self.results),
                "total_model_calls": sum(item.model_calls for item in self.results),
                "total_prompt_tokens": sum(item.prompt_tokens for item in self.results),
                "total_completion_tokens": sum(
                    item.completion_tokens for item in self.results
                ),
                "total_cost_usd": round(
                    sum(item.estimated_cost_usd or 0.0 for item in self.results), 8
                ),
            },
            "results": [asdict(item) for item in self.results],
        }


class BenchmarkSuite:
    """Validated benchmark manifest."""

    def __init__(self, name: str, tasks: list[BenchmarkTask], source: Path):
        self.name = name
        self.tasks = tasks
        self.source = source

    @classmethod
    def load(cls, path: str | Path) -> "BenchmarkSuite":
        source = Path(path).expanduser().resolve()
        value = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Benchmark manifest must be a JSON object")
        if value.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported benchmark schema: {value.get('schema_version')!r}"
            )
        raw_tasks = value.get("tasks", [])
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError("Benchmark manifest must contain at least one task")
        tasks = [BenchmarkTask.from_dict(item, source.parent) for item in raw_tasks]
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Benchmark task ids must be unique")
        return cls(str(value.get("name", source.stem)), tasks, source)


class BenchmarkRunner:
    """Run each task in a temporary copy and preserve only the JSON report."""

    def __init__(self, suite: BenchmarkSuite):
        self.suite = suite

    def run(self, *, dry_run: bool = False) -> BenchmarkReport:
        started = _utc_now()
        results = [
            self._validate_task(task) if dry_run else self._run_task(task)
            for task in self.suite.tasks
        ]
        return BenchmarkReport(
            suite=self.suite.name,
            nexus_version=__version__,
            started_at=started,
            completed_at=_utc_now(),
            results=results,
        )

    def _validate_task(self, task: BenchmarkTask) -> BenchmarkTaskResult:
        repository = Path(task.repository)
        available = repository.is_dir()
        return BenchmarkTaskResult(
            task_id=task.id,
            category=task.category,
            status="VALID" if available else "BLOCKED",
            duration_ms=0,
            detail=(
                "Manifest and repository are valid"
                if available
                else f"Repository does not exist: {repository}"
            ),
        )

    def _run_task(self, task: BenchmarkTask) -> BenchmarkTaskResult:
        source = Path(task.repository)
        started = time.monotonic()
        if not source.is_dir():
            return BenchmarkTaskResult(
                task.id,
                task.category,
                "BLOCKED",
                0,
                detail=f"Repository does not exist: {source}",
            )
        temporary_root = Path(tempfile.mkdtemp(prefix=f"nexus-benchmark-{task.id}-"))
        workspace = temporary_root / "workspace"
        try:
            shutil.copytree(
                source,
                workspace,
                symlinks=False,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".nexusai",
                    ".venv",
                    "venv",
                    "node_modules",
                    "dist",
                    "build",
                    "__pycache__",
                ),
            )
            before = _fingerprints(workspace)
            command = [
                sys.executable,
                "-m",
                "nexus",
                "run",
                "--prompt",
                task.prompt,
                "--mode",
                "ci",
                "--working-dir",
                str(workspace),
                "--no-workspace",
                "--output-format",
                "json",
            ]
            try:
                process = subprocess.run(
                    command,
                    cwd=workspace,
                    env=dict(os.environ),
                    capture_output=True,
                    text=True,
                    timeout=task.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                return BenchmarkTaskResult(
                    task.id,
                    task.category,
                    "FAILED",
                    int((time.monotonic() - started) * 1000),
                    detail=f"Nexus timed out after {task.timeout_seconds}s: {exc}",
                )
            payload = _last_json_object(process.stdout)
            after = _fingerprints(workspace)
            changed = sorted(
                path
                for path in set(before) | set(after)
                if before.get(path) != after.get(path)
            )
            unexpected = [
                path
                for path in changed
                if task.allowed_paths and not _matches_any(path, task.allowed_paths)
            ]
            missing_expected = [
                path
                for path in task.expected_changed_files
                if path not in changed
            ]
            checks = []
            for argv in task.verification:
                result = SandboxRunner(workspace).run(
                    CommandSpec.create(
                        argv,
                        workspace,
                        timeout_seconds=min(task.timeout_seconds, 300),
                        network=False,
                    )
                )
                checks.append(result.to_dict())
            run_report = payload.get("run", {}) if isinstance(payload, dict) else {}
            costs = run_report.get("costs", {})
            usage = costs.get("usage", costs) if isinstance(costs, dict) else {}
            checks_pass = all(item.get("success") for item in checks)
            passed = (
                process.returncode == 0
                and checks_pass
                and not unexpected
                and not missing_expected
                and run_report.get("status") in {"VERIFIED", "PARTIALLY_VERIFIED"}
            )
            details = []
            if process.returncode:
                details.append(f"Nexus exit code {process.returncode}")
            if not checks_pass:
                details.append("one or more deterministic checks failed")
            if unexpected:
                details.append(f"unexpected files: {unexpected}")
            if missing_expected:
                details.append(f"expected files unchanged: {missing_expected}")
            if run_report.get("status") not in {"VERIFIED", "PARTIALLY_VERIFIED"}:
                details.append(f"run status: {run_report.get('status', 'missing')}")
            return BenchmarkTaskResult(
                task_id=task.id,
                category=task.category,
                status="PASSED" if passed else "FAILED",
                duration_ms=int((time.monotonic() - started) * 1000),
                nexus_exit_code=process.returncode,
                verification=checks,
                changed_files=changed,
                unexpected_files=unexpected,
                model_calls=int(usage.get("hosted_calls", 0) or 0),
                prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage.get("completion_tokens", 0) or 0),
                estimated_cost_usd=(
                    float(usage["estimated_cost_usd"])
                    if usage.get("estimated_cost_usd") is not None
                    else None
                ),
                retries=int(run_report.get("metadata", {}).get("retries", 0) or 0),
                human_intervention=run_report.get("status") == "AWAITING_APPROVAL",
                detail="; ".join(details) if details else "All acceptance checks passed",
            )
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)


def _fingerprints(root: Path) -> dict[str, str]:
    ignored = {".git", ".nexusai", "__pycache__", ".pytest_cache", ".ruff_cache"}
    result = {}
    for path in root.rglob("*"):
        if not path.is_file() or any(part in ignored for part in path.relative_to(root).parts):
            continue
        try:
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        except OSError:
            continue
    return result


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(path, pattern) for pattern in patterns)


def _last_json_object(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
