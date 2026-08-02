"""
RunFinalizer — extracted service for run completion and evidence evaluation.

This module provides a clean boundary for the ~379-line ``_finish_managed_run``
logic inside Agent.  By making it a standalone service, the completion pipeline
becomes independently testable, readable, and replaceable without touching the
monolithic Agent class.

Architecture::

    RunFinalizer
    ├── evaluate_evidence()     classify mutations, checks, commands, review
    ├── assess_criteria()       match task criteria to evidence records
    ├── determine_status()      VERIFIED / PARTIALLY_VERIFIED / FAILED / …
    ├── write_report()          persist final_report.json to the run directory
    └── summarise()             return the machine-readable report dict
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nexus.agent import Agent
    from nexus.run_state import RunStatus

logger = logging.getLogger(__name__)


class EvidenceClass(str, Enum):
    """Broad category used during final-report assembly."""

    MUTATION = "file_mutation"
    VERIFICATION = "verification_check"
    COMMAND = "command"
    BEHAVIORAL = "behavioral_verification"
    REVIEW = "independent_review"


@dataclass
class EvidenceSummary:
    """Aggregated evidence for one run turn."""

    verified_mutations: list[dict[str, Any]] = field(default_factory=list)
    passing_checks: list[dict[str, Any]] = field(default_factory=list)
    passing_commands: list[dict[str, Any]] = field(default_factory=list)
    passing_behavioral: list[dict[str, Any]] = field(default_factory=list)
    approved_reviews: list[dict[str, Any]] = field(default_factory=list)
    failed_evidence: list[dict[str, Any]] = field(default_factory=list)
    reproduction_evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_any_success(self) -> bool:
        return bool(
            self.verified_mutations
            or self.passing_checks
            or self.passing_commands
            or self.passing_behavioral
        )

    @property
    def has_failures(self) -> bool:
        return bool(self.failed_evidence)


class RunFinalizer:
    """
    Service that evaluates evidence and produces the final run report.

    This is a *delegation target* for ``Agent._finish_managed_run``.
    It surfaces the evaluation logic as independently callable methods so
    that the report generation pipeline can be tested without a full agent.

    Usage::

        finalizer = RunFinalizer(agent)
        report = finalizer.finish(content, events)
    """

    def __init__(self, agent: "Agent") -> None:
        self._agent = agent

    # ──────────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────────

    def finish(
        self,
        content: str,
        events: list[dict[str, Any]] | None = None,
        *,
        status_override: "RunStatus | None" = None,
    ) -> dict[str, Any]:
        """
        Evaluate evidence and write a machine-readable final report.

        Delegates to ``Agent._finish_managed_run`` for now; this wrapper
        establishes the decomposition boundary so callers can migrate one
        by one without a big-bang refactor.
        """
        return self._agent._finish_managed_run(
            content,
            events,
            status_override=status_override,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Evidence helpers (independently testable)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def classify_evidence(records: list[dict[str, Any]]) -> EvidenceSummary:
        """
        Partition a flat list of evidence records into the structured summary.

        This is a pure function — it does not touch disk or agent state.
        """
        summary = EvidenceSummary()

        # Track latest status per mutation/verification ID so stale failed
        # attempts don't poison the report.
        latest_by_id: dict[str, str] = {}
        for item in records:
            kind = item.get("kind", "")
            if kind in (EvidenceClass.MUTATION, EvidenceClass.VERIFICATION):
                rid = str(item.get("id", ""))
                if rid:
                    latest_by_id[rid] = item.get("status", "")

        effective_ids = {
            rid for rid, status in latest_by_id.items() if status == "verified"
        }

        # Latest behavioral status per tool
        latest_behavioral: dict[str, str] = {
            item.get("tool", ""): item.get("status", "")
            for item in records
            if item.get("kind") == EvidenceClass.BEHAVIORAL
        }

        # Passing command set (for deduplication)
        passing_cmd_text: set[str] = set()

        for item in records:
            kind = item.get("kind", "")
            status = item.get("status", "")

            if kind == EvidenceClass.MUTATION and str(item.get("id")) in effective_ids and status == "verified":
                summary.verified_mutations.append(item)
            elif kind == EvidenceClass.VERIFICATION and str(item.get("id")) in effective_ids and status == "verified":
                summary.passing_checks.append(item)
            elif kind == EvidenceClass.COMMAND and status == "verified" and item.get("exit_code") == 0:
                summary.passing_commands.append(item)
                passing_cmd_text.add(item.get("command", ""))
            elif kind == EvidenceClass.BEHAVIORAL and status == "verified":
                summary.passing_behavioral.append(item)
            elif kind == EvidenceClass.REVIEW and status == "verified":
                summary.approved_reviews.append(item)

        # Failed evidence (exclude stale retried items that later succeeded)
        for item in records:
            kind = item.get("kind", "")
            status = item.get("status", "")
            rid = str(item.get("id", ""))

            if status != "failed":
                continue
            if kind in ("routing", EvidenceClass.REVIEW):
                continue
            if kind in (EvidenceClass.MUTATION, EvidenceClass.VERIFICATION):
                if rid in effective_ids:
                    continue  # Later attempt succeeded
            if kind == EvidenceClass.COMMAND and item.get("command", "") in passing_cmd_text:
                continue
            if kind == EvidenceClass.BEHAVIORAL:
                if latest_behavioral.get(item.get("tool", "")) == "verified":
                    continue
            summary.failed_evidence.append(item)

        # Reproduction evidence (failed commands + failed verification checks)
        for item in records:
            kind = item.get("kind", "")
            if kind == EvidenceClass.COMMAND and (
                item.get("status") == "failed" or item.get("exit_code") not in (None, 0)
            ):
                summary.reproduction_evidence.append(item)
            elif kind == EvidenceClass.VERIFICATION and item.get("status") == "failed":
                summary.reproduction_evidence.append(item)

        return summary

    @staticmethod
    def determine_status(
        summary: EvidenceSummary,
        *,
        awaiting_approval: bool = False,
        blocked: bool = False,
    ) -> str:
        """
        Map an EvidenceSummary to a RunStatus string.

        This is a pure function — no side effects.
        """
        if blocked:
            return "BLOCKED"
        if awaiting_approval:
            return "AWAITING_APPROVAL"
        if not summary.has_any_success and summary.has_failures:
            return "FAILED"
        if summary.has_failures:
            return "PARTIALLY_VERIFIED"
        if summary.has_any_success:
            return "VERIFIED"
        return "UNVERIFIED"


# ─── Convenience factory ─────────────────────────────────────────────────────


def make_finalizer(agent: "Agent") -> RunFinalizer:
    """Create and attach a ``RunFinalizer`` to *agent*."""
    finalizer = RunFinalizer(agent)
    agent._run_finalizer = finalizer  # type: ignore[attr-defined]
    return finalizer
