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
                raise ValueError(f"Benchmark task {task_id} verification must use argv arrays")
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
    agent_status: str | None = None
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
    failure_phase: str = ""
    failure_type: str = ""
    environment_failure: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""

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
                "verified_passed": sum(
                    1 for item in self.results if item.passed and item.agent_status == "VERIFIED"
                ),
                "failed": len(self.results) - passed,
                "pass_rate": (round(passed / len(self.results), 4) if self.results else 0.0),
                "verified_pass_rate": (
                    round(
                        sum(
                            1
                            for item in self.results
                            if item.passed and item.agent_status == "VERIFIED"
                        )
                        / len(self.results),
                        4,
                    )
                    if self.results
                    else 0.0
                ),
                "total_duration_ms": sum(item.duration_ms for item in self.results),
                "total_model_calls": sum(item.model_calls for item in self.results),
                "average_model_calls": round(
                    sum(item.model_calls for item in self.results) / len(self.results), 2
                )
                if self.results
                else 0.0,
                "average_retries": round(
                    sum(item.retries for item in self.results) / len(self.results), 2
                )
                if self.results
                else 0.0,
                "total_prompt_tokens": sum(item.prompt_tokens for item in self.results),
                "total_completion_tokens": sum(item.completion_tokens for item in self.results),
                "total_cost_usd": round(
                    sum(item.estimated_cost_usd or 0.0 for item in self.results), 8
                ),
                "average_cost_usd": round(
                    sum(item.estimated_cost_usd or 0.0 for item in self.results)
                    / len(self.results),
                    4,
                )
                if self.results
                else 0.0,
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
            raise ValueError(f"Unsupported benchmark schema: {value.get('schema_version')!r}")
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

    def _preflight(self):
        from nexus.models import resolve_model
        from nexus.preflight import BackendProbe, probe_model

        model = os.environ.get("NEXUS_MODEL", "nova")
        model_cfg = resolve_model(model)
        if not model_cfg:
            return BackendProbe(
                ready=False,
                backend="configuration",
                code="unknown_model",
                detail=f"Unknown benchmark model: {model}",
                remediation=("Set NEXUS_MODEL to a key shown by `nexus --list-models`.",),
            )
        return probe_model(model_cfg, model_name=model)

    def _preflight_check(self) -> bool:
        """Backward-compatible boolean check used by external callers."""
        return bool(self._preflight().ready)

    def run(self, *, dry_run: bool = False) -> BenchmarkReport:
        started = _utc_now()
        probe = None if dry_run else self._preflight()

        if probe is not None and not probe.ready:
            results = [
                BenchmarkTaskResult(
                    task_id=task.id,
                    category=task.category,
                    status="INVALID_CONFIGURATION",
                    duration_ms=0,
                    detail=probe.format(),
                    failure_phase="provider_preflight",
                    failure_type=probe.code,
                    environment_failure=True,
                )
                for task in self.suite.tasks
            ]
        else:
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
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
            try:
                process = subprocess.run(
                    command,
                    cwd=workspace,
                    env=env,
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
                    failure_phase="agent_execution",
                    failure_type="timeout",
                    environment_failure=False,
                    stdout_tail=_redact_tail(exc.stdout),
                    stderr_tail=_redact_tail(exc.stderr),
                )
            payload = _last_json_object(process.stdout)
            after = _fingerprints(workspace)
            changed = sorted(
                path for path in set(before) | set(after) if before.get(path) != after.get(path)
            )
            unexpected = [
                path
                for path in changed
                if task.allowed_paths and not _matches_any(path, task.allowed_paths)
            ]
            missing_expected = [path for path in task.expected_changed_files if path not in changed]
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
                process.returncode in {0, 2}
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
            failure_phase, failure_type, environment_failure = _classify_process_failure(
                process.returncode,
                process.stdout,
                process.stderr,
                run_report,
            )
            return BenchmarkTaskResult(
                task_id=task.id,
                category=task.category,
                status="PASSED" if passed else "FAILED",
                duration_ms=int((time.monotonic() - started) * 1000),
                nexus_exit_code=process.returncode,
                agent_status=run_report.get("status", "unknown"),
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
                failure_phase="" if passed else failure_phase,
                failure_type="" if passed else failure_type,
                environment_failure=False if passed else environment_failure,
                stdout_tail=_redact_tail(process.stdout),
                stderr_tail=_redact_tail(process.stderr),
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


def _redact_tail(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    for name in (
        "NVIDIA_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "NEXUS_OPENAI_API_KEY",
    ):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[-max(0, int(limit)) :]


def _classify_process_failure(
    exit_code: int,
    stdout: str,
    stderr: str,
    run_report: dict[str, Any],
) -> tuple[str, str, bool]:
    if exit_code == 0 and run_report.get("status") in {"VERIFIED", "PARTIALLY_VERIFIED"}:
        return "", "", False
    haystack = (str(stdout) + "\n" + str(stderr)).lower()
    environment_signatures = {
        "ollama_unreachable": ("ollama", "connection refused"),
        "dependency_missing": ("modulenotfounderror",),
        "credentials_missing": ("api key", "missing"),
        "provider_unreachable": ("provider", "connection"),
    }
    for failure_type, signatures in environment_signatures.items():
        if all(signature in haystack for signature in signatures):
            return "environment", failure_type, True
    if not run_report:
        return "result_parsing", "missing_structured_result", True
    status = str(run_report.get("status", "")).lower()
    if status in {"awaiting_approval", "blocked"}:
        return "policy", status, False
    if "verification" in haystack or status in {"unverified", "partially_verified"}:
        return "verification", "acceptance_checks_failed", False
    return "agent_execution", "nonzero_exit", False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
