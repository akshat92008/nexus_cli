"""
Verification Engine — auto-detects project type and runs appropriate checks
(tests, linting, type checking, compilation) after code changes.

Architecture:
    Detect Project Type → Select Checks → Execute → Report Results
"""

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class CheckType(str, Enum):
    """Types of verification checks."""
    TEST = "test"
    LINT = "lint"
    TYPE_CHECK = "type_check"
    BUILD = "build"
    FORMAT = "format"
    SECURITY = "security"


class CheckStatus(str, Enum):
    """Status of a verification check."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class CheckResult:
    """Result of a single verification check."""
    check_type: CheckType
    status: CheckStatus
    command: str
    output: str = ""
    error_count: int = 0
    warning_count: int = 0
    duration_ms: int = 0

    @property
    def passed(self) -> bool:
        return self.status == CheckStatus.PASSED

    def format_result(self) -> str:
        icons = {
            CheckStatus.PASSED: "✅",
            CheckStatus.FAILED: "❌",
            CheckStatus.SKIPPED: "⏭️",
            CheckStatus.ERROR: "💥",
            CheckStatus.NOT_APPLICABLE: "➖",
        }
        icon = icons.get(self.status, "❓")
        line = f"{icon} {self.check_type.value}: {self.status.value}"
        if self.error_count:
            line += f" ({self.error_count} errors)"
        if self.warning_count:
            line += f" ({self.warning_count} warnings)"
        if self.command:
            line += f"  [{self.command}]"
        return line


@dataclass
class VerificationReport:
    """Full report from a verification run."""
    project_type: str
    checks: list[CheckResult] = field(default_factory=list)
    all_passed: bool = False

    def format_report(self) -> str:
        lines = [f"🔍 Verification Report — {self.project_type}"]
        lines.append("")
        for check in self.checks:
            lines.append(f"  {check.format_result()}")
            if check.output:
                for output_line in check.output.splitlines():
                    lines.append(f"    │ {output_line}")

        passed = sum(1 for c in self.checks if c.passed)
        total = len(self.checks)
        lines.append("")
        lines.append(f"  Summary: {passed}/{total} checks passed")

        return "\n".join(lines)


# ── Project Type Detection ───────────────────────────────────────────────────

_DEFAULT_COMMANDS: dict[str, dict[str, str]] = {
    "python": {
        "test": "python -m pytest -x -q",
        "lint": "ruff check . --no-fix",
        "type_check": "mypy . --ignore-missing-imports",
        "format": "ruff format --check .",
    },
    "javascript": {
        "test": "npm test",
        "lint": "npx eslint . --no-error-on-unmatched-pattern",
        "type_check": "npx tsc --noEmit",
        "build": "npm run build",
    },
    "typescript": {
        "test": "npm test",
        "lint": "npx eslint . --no-error-on-unmatched-pattern",
        "type_check": "npx tsc --noEmit",
        "build": "npm run build",
    },
    "rust": {
        "test": "cargo test --quiet",
        "lint": "cargo clippy --quiet -- -D warnings",
        "build": "cargo check --quiet",
        "format": "cargo fmt --check",
    },
    "go": {
        "test": "go test ./... -count=1",
        "lint": "go vet ./...",
        "build": "go build ./...",
        "format": "gofmt -l .",
    },
    "java": {
        "test": "mvn test -q",
        "build": "mvn compile -q",
    },
    "ruby": {
        "test": "bundle exec rspec --no-color",
        "lint": "bundle exec rubocop --no-color",
    },
    "php": {
        "test": "vendor/bin/phpunit",
        "lint": "vendor/bin/phpstan analyse",
    },
    "dart": {
        "test": "dart test",
        "lint": "dart analyze",
        "format": "dart format --set-exit-if-changed .",
    },
    "elixir": {
        "test": "mix test",
        "lint": "mix credo",
        "build": "mix compile --warnings-as-errors",
    },
}


class VerificationEngine:
    """
    Auto-detects project type and runs appropriate verification checks.

    Supports custom commands from NEXUS.md project rules, falling back to
    sensible defaults for each language/framework.

    Usage:
        engine = VerificationEngine("/path/to/project")
        report = engine.run_all()
        print(report.format_report())

        # Or run specific checks
        result = engine.run_check(CheckType.TEST)
        result = engine.run_check(CheckType.LINT)
    """

    def __init__(
        self,
        working_dir: str,
        custom_commands: dict[str, str] | None = None,
    ):
        self.working_dir = working_dir
        self.project_type = self._detect_project_type()
        self.commands = self._resolve_commands(custom_commands or {})

    def run_all(self, checks: list[CheckType] | None = None) -> VerificationReport:
        """Run all applicable verification checks."""
        if checks is None:
            checks = [CheckType.LINT, CheckType.TYPE_CHECK, CheckType.TEST, CheckType.BUILD]

        report = VerificationReport(project_type=self.project_type)

        for check_type in checks:
            result = self.run_check(check_type)
            if result.status != CheckStatus.NOT_APPLICABLE:
                report.checks.append(result)

        report.all_passed = bool(report.checks) and all(
            c.passed or c.status == CheckStatus.SKIPPED
            for c in report.checks
        )

        return report

    def run_check(self, check_type: CheckType) -> CheckResult:
        """Run a single verification check."""
        command = self.commands.get(check_type.value)

        if not command:
            return CheckResult(
                check_type=check_type,
                status=CheckStatus.NOT_APPLICABLE,
                command="",
            )

        return self._execute_check(check_type, command)

    def run_tests(self) -> CheckResult:
        """Shortcut to run just tests."""
        return self.run_check(CheckType.TEST)

    def run_lint(self) -> CheckResult:
        """Shortcut to run just linting."""
        return self.run_check(CheckType.LINT)

    def get_available_checks(self) -> list[CheckType]:
        """Get which checks are available for this project."""
        available = []
        for check_type in CheckType:
            if check_type.value in self.commands:
                available.append(check_type)
        return available

    # ── Private Methods ──────────────────────────────────────────────────

    def _detect_project_type(self) -> str:
        """Detect the project's primary language/framework."""
        root = Path(self.working_dir)

        indicators = {
            "python": ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
            "typescript": ["tsconfig.json"],
            "javascript": ["package.json"],
            "rust": ["Cargo.toml"],
            "go": ["go.mod"],
            "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "ruby": ["Gemfile"],
            "php": ["composer.json"],
            "dart": ["pubspec.yaml"],
            "elixir": ["mix.exs"],
        }

        for lang, files in indicators.items():
            for filename in files:
                if (root / filename).exists():
                    # TypeScript check: package.json alone means JS
                    if lang == "javascript" and (root / "tsconfig.json").exists():
                        continue  # Will be caught as typescript
                    return lang

        return "unknown"

    def _resolve_commands(self, custom: dict[str, str]) -> dict[str, str]:
        """Resolve verification commands, preferring custom over defaults."""
        defaults = _DEFAULT_COMMANDS.get(self.project_type, {})
        resolved = {**defaults}

        # Override with custom commands
        for key, cmd in custom.items():
            if cmd:
                # Map common aliases
                key_map = {
                    "test_command": "test",
                    "lint_command": "lint",
                    "build_command": "build",
                    "format_command": "format",
                }
                resolved_key = key_map.get(key, key)
                resolved[resolved_key] = cmd

        # Check if tools are actually available (for Python projects)
        if self.project_type == "python":
            root = Path(self.working_dir)
            if not self._command_exists("ruff"):
                if "lint" in resolved and "ruff" in resolved["lint"]:
                    if self._python_module_exists("flake8"):
                        resolved["lint"] = "python -m flake8 ."
                    else:
                        resolved.pop("lint", None)
                if "format" in resolved and "ruff" in resolved["format"]:
                    resolved.pop("format", None)
            if not self._command_exists("mypy"):
                resolved.pop("type_check", None)

        return resolved

    def _python_module_exists(self, module: str) -> bool:
        """Check a Python module without importing it or masking failures."""
        try:
            result = subprocess.run(
                [os.environ.get("PYTHON", "python3"), "-c", f"import importlib.util; raise SystemExit(importlib.util.find_spec('{module}') is None)"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self.working_dir,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _command_exists(self, cmd: str) -> bool:
        """Check if a command is available."""
        try:
            result = subprocess.run(
                ["which", cmd],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _execute_check(self, check_type: CheckType, command: str) -> CheckResult:
        """Execute a verification command and parse the result."""
        import time
        start = time.monotonic()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.working_dir,
                timeout=120,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "true"},
            )

            duration = int((time.monotonic() - start) * 1000)
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            status = CheckStatus.PASSED if result.returncode == 0 else CheckStatus.FAILED

            # Count errors and warnings from output
            error_count = output.lower().count("error")
            warning_count = output.lower().count("warning")

            return CheckResult(
                check_type=check_type,
                status=status,
                command=command,
                output=output.strip(),
                error_count=error_count,
                warning_count=warning_count,
                duration_ms=duration,
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                check_type=check_type,
                status=CheckStatus.ERROR,
                command=command,
                output="Command timed out after 120 seconds",
            )
        except Exception as e:
            return CheckResult(
                check_type=check_type,
                status=CheckStatus.ERROR,
                command=command,
                output=f"Error: {e}",
            )
