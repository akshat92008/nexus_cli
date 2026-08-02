"""
Tests for the three NexusRuntime service extraction modules:
  - nexus.tool_executor.ToolExecutionController
  - nexus.report_builder.ReportBuilder, EvidenceSummary, classify_evidence, determine_status
  - nexus.turn_coordinator.SessionState, TurnResult, parse_tool_call_arguments, validate_tool_call

All tests are hermetic — no provider credentials required.
"""

from __future__ import annotations
from nexus.report_builder import ReportBuilder

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from nexus.report_builder import (
    EvidenceClass,
    EvidenceSummary,
    ReportBuilder,
    make_finalizer,
)

# ─── Shared fake agent ────────────────────────────────────────────────────────


def _fake_agent(tmp_path: Path):
    """Build a minimal fake NexusRuntime-like object for service tests."""
    agent = SimpleNamespace(
        working_dir=str(tmp_path),
        model_key="test",
        model_cfg={"name": "test", "id": "test"},
        mode_policy=SimpleNamespace(allow_shell_command=True, require_os_isolation=False),
        evidence=SimpleNamespace(records=lambda: []),
        hooks=SimpleNamespace(),
        reflection=None,
        _tool_capabilities={},
        _pending_confirmations={},
        _execute_tool_with_safety=lambda name, args, **kw: ("ok", True),
        _run_single_turn=lambda messages, emit_ui=True: ("done", []),
    )
    agent._run_finalizer = MagicMock()
    agent._run_finalizer.finish = lambda *a, **kw: {"status": "VERIFIED"}
    return agent


# ─── ToolExecutionController ─────────────────────────────────────────────────


class TestReportBuilder:
    def test_classify_evidence_verified_mutation(self):
        records = [
            {"kind": EvidenceClass.MUTATION, "id": "m1", "status": "verified"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert len(summary.verified_mutations) == 1
        assert not summary.failed_evidence

    def test_classify_evidence_failed_mutation_superseded_by_success(self):
        """A failed mutation followed by a verified mutation with the same ID
        should not appear in failed_evidence."""
        records = [
            {"kind": EvidenceClass.MUTATION, "id": "m1", "status": "failed"},
            {"kind": EvidenceClass.MUTATION, "id": "m1", "status": "verified"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert len(summary.verified_mutations) == 1
        assert not summary.failed_evidence

    def test_classify_evidence_all_failed(self):
        records = [
            {"kind": EvidenceClass.MUTATION, "id": "m1", "status": "failed"},
            {"kind": EvidenceClass.VERIFICATION, "id": "v1", "status": "failed"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert summary.has_failures is True
        assert summary.has_any_success is False

    def test_classify_evidence_passing_command(self):
        records = [
            {"kind": EvidenceClass.COMMAND, "status": "verified", "exit_code": 0, "command": "pytest"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert len(summary.passing_commands) == 1
        assert not summary.failed_evidence

    def test_classify_evidence_behavioral_superseded(self):
        records = [
            {"kind": EvidenceClass.BEHAVIORAL, "tool": "run_command", "status": "failed"},
            {"kind": EvidenceClass.BEHAVIORAL, "tool": "run_command", "status": "verified"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert len(summary.passing_behavioral) == 1
        assert not summary.failed_evidence

    def test_classify_evidence_routing_excluded_from_failures(self):
        records = [
            {"kind": "routing", "status": "failed"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert not summary.failed_evidence

    def test_classify_evidence_independent_review_excluded_from_failures(self):
        records = [
            {"kind": EvidenceClass.REVIEW, "status": "failed"},
        ]
        summary = ReportBuilder.classify_evidence(records)
        assert not summary.failed_evidence

    def test_determine_status_verified(self):
        summary = EvidenceSummary(
            verified_mutations=[{"id": "m1"}],
        )
        assert ReportBuilder.determine_status(summary) == "VERIFIED"

    def test_determine_status_failed(self):
        summary = EvidenceSummary(
            failed_evidence=[{"id": "x"}],
        )
        assert ReportBuilder.determine_status(summary) == "FAILED"

    def test_determine_status_partially_verified(self):
        summary = EvidenceSummary(
            verified_mutations=[{"id": "m1"}],
            failed_evidence=[{"id": "f1"}],
        )
        assert ReportBuilder.determine_status(summary) == "PARTIALLY_VERIFIED"

    def test_determine_status_blocked(self):
        summary = EvidenceSummary()
        assert ReportBuilder.determine_status(summary, blocked=True) == "BLOCKED"

    def test_determine_status_awaiting_approval(self):
        summary = EvidenceSummary()
        assert (
            ReportBuilder.determine_status(summary, awaiting_approval=True)
            == "AWAITING_APPROVAL"
        )

    def test_determine_status_unverified_empty(self):
        summary = EvidenceSummary()
        assert ReportBuilder.determine_status(summary) == "UNVERIFIED"


    def test_make_finalizer_attaches_to_agent(self, tmp_path):
        agent = _fake_agent(tmp_path)
        fin = make_finalizer(agent)
        assert hasattr(agent, "_run_finalizer")
        assert agent._run_finalizer is fin


# ─── SessionState ──────────────────────────────────────────────────────────


