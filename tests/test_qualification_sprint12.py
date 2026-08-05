"""Qualification test suite for Nexus CLI Sprint 12.

Validates final release gates, packaging integrity, exit code mappings,
false-success fail-closed behavior, budget enforcement, and benchmark execution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.benchmarks.benchmark_final_runner import FinalBenchmarkRunner
from nexus.budget import BudgetController, BudgetExceeded, BudgetLimits
from nexus.cli import exit_code_for_outcome
from nexus.security.filesystem_security import FilesystemSecurity
from nexus.security.policy_engine import PolicyEngine, SecurityAction
from nexus.security.secret_protection import SecretRedactor
from nexus.verification import CheckType, VerificationEngine


def test_sprint12_false_success_fail_closed(tmp_path):
    """Verify that failing checks return FAILED and never false VERIFIED."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\nversion='0.1.0'\n", encoding="utf-8")
    engine = VerificationEngine(str(tmp_path), {"test": "python3 -c 'import sys; sys.exit(1)'"})
    result = engine.run_check(CheckType.TEST)
    assert not result.passed
    assert result.status.value in {"failed", "error"}


def test_sprint12_exit_code_mappings():
    """Verify deterministic exit codes for every terminal outcome state."""
    assert exit_code_for_outcome("VERIFIED") == 0
    assert exit_code_for_outcome("FAILED") == 1
    assert exit_code_for_outcome("INTERNAL_ERROR") == 1
    assert exit_code_for_outcome("PARTIALLY_VERIFIED") == 2
    assert exit_code_for_outcome("BLOCKED") == 3
    assert exit_code_for_outcome("BUDGET_EXHAUSTED") == 4
    assert exit_code_for_outcome("SECURITY_POLICY_DENIED") == 5
    assert exit_code_for_outcome("CONFIGURATION_ERROR") == 6
    assert exit_code_for_outcome("VERIFICATION_UNAVAILABLE") == 7


def test_sprint12_budget_enforcement():
    """Verify hard non-bypassable budget enforcement."""
    controller = BudgetController(BudgetLimits(max_hosted_calls=1))
    controller.before_hosted_call(messages=[{"role": "user", "content": "hello"}])
    with pytest.raises(BudgetExceeded):
        controller.before_hosted_call(messages=[{"role": "user", "content": "overflow"}])


def test_sprint12_path_containment_security(tmp_path):
    """Verify path traversal containment defense."""
    fs_sec = FilesystemSecurity(tmp_path)
    with pytest.raises(ValueError):
        fs_sec.validate_path(tmp_path / "../../../etc/passwd")


def test_sprint12_secret_redaction():
    """Verify secret redactor strips credentials from outputs."""
    redactor = SecretRedactor()
    sample_text = "Connecting with sk-proj-1234567890abcdef1234567890abcdef and ghp_1234567890abcdef1234567890abcdef1234"
    redacted = redactor.redact_text(sample_text)
    assert "sk-proj-1234567890abcdef1234567890abcdef" not in redacted
    assert "ghp_1234567890abcdef1234567890abcdef1234" not in redacted
    assert "[REDACTED]" in redacted


def test_sprint12_final_benchmark_runner():
    """Run full Sprint 12 benchmark suite and assert 100% pass rate."""
    runner = FinalBenchmarkRunner()
    summary = runner.run_all()
    assert summary.total_tasks == 12
    assert summary.passed_tasks == 12
    assert summary.verified_success_rate == 1.0
    assert summary.false_success_rate == 0.0
    assert summary.budget_compliance_rate == 1.0


def test_sprint12_release_manifest_artifacts_exist():
    """Verify that release manifest files exist and are well-formed."""
    manifest_file = Path("benchmarks/final/manifest.yaml")
    assert manifest_file.exists()
    results_file = Path("artifacts/final-benchmark-results.json")
    assert results_file.exists()
    data = json.loads(results_file.read_text(encoding="utf-8"))
    assert data["total_tasks"] == 12
    assert data["passed_tasks"] == 12
