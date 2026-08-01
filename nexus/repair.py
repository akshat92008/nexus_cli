"""
Autonomous Repair Loop for Nexus CLI.

Implements a closed-loop repair system:
    Collect failures → Classify root cause → Generate targeted repair prompt →
    Apply repair → Re-verify → Repeat until success or budget exhausted.

This is fundamentally different from simply re-running the original prompt.
Repairs are targeted to the specific failure class (syntax, import, type,
test, runtime, dependency, timeout, security).

Usage::

    from nexus.repair import RepairLoop
    loop = RepairLoop(agent)
    success = loop.attempt(original_prompt, failure_context="test failed: ...")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nexus.runtime.kernel import FailureKind, classify_failure

if TYPE_CHECKING:
    from nexus.agent import Agent

logger = logging.getLogger(__name__)

# Maximum number of repair iterations before giving up
DEFAULT_MAX_ITERATIONS = 3
# Maximum seconds to spend in total repair
DEFAULT_REPAIR_BUDGET_SECONDS = 120


@dataclass
class RepairAttempt:
    """Record of one repair iteration."""

    iteration: int
    failure_kind: FailureKind
    repair_prompt: str
    success: bool
    duration_ms: int = 0
    evidence_ids: list[str] = field(default_factory=list)
    output: str = ""


@dataclass
class RepairReport:
    """Complete repair run outcome."""

    original_prompt: str
    failure_context: str
    attempts: list[RepairAttempt] = field(default_factory=list)
    succeeded: bool = False
    total_duration_ms: int = 0

    def summary(self) -> str:
        if self.succeeded:
            n = len(self.attempts)
            return f"✅ Repair succeeded after {n} iteration{'s' if n != 1 else ''}."
        kinds = {a.failure_kind.value for a in self.attempts}
        return (
            f"❌ Repair exhausted {len(self.attempts)} iterations "
            f"(failure kinds: {', '.join(kinds)})."
        )


class RepairLoop:
    """
    Closed-loop autonomous repair engine.

    Identifies the class of failure from actual output, generates a targeted
    repair prompt (not a verbatim retry of the original), applies it, and
    re-verifies until the failure is resolved or the budget is exhausted.
    """

    # Repair prompt templates keyed by FailureKind.
    # Each template receives {original_prompt}, {failure_context}, {iteration}.
    _TEMPLATES: dict[FailureKind, str] = {
        FailureKind.SYNTAX: (
            "The previous attempt produced a syntax error:\n\n{failure_context}\n\n"
            "Fix ONLY the syntax error. Do not change any other logic. "
            "Read the file first, identify the exact malformed construct, then apply a minimal edit."
        ),
        FailureKind.IMPORT: (
            "The previous attempt produced an import error:\n\n{failure_context}\n\n"
            "Identify the missing or incorrect import. Check whether the module exists in the "
            "project. If it is a third-party package, verify it is listed in requirements.txt "
            "before installing. Fix only the import — do not rewrite the file."
        ),
        FailureKind.TYPE: (
            "The previous attempt produced a type error:\n\n{failure_context}\n\n"
            "Read the affected function signature and call sites. Apply the minimal type fix "
            "(add annotation, cast, or guard). Run mypy / pyright on that file only to confirm."
        ),
        FailureKind.TEST: (
            "The following tests are failing:\n\n{failure_context}\n\n"
            "Read the test code and the implementation it tests. Identify the assertion that "
            "fails and trace it to its root cause in the production code. Fix the production code "
            "(not the test) unless the test expectation is clearly wrong. Then re-run the tests."
        ),
        FailureKind.RUNTIME: (
            "The previous attempt produced a runtime error:\n\n{failure_context}\n\n"
            "Read the traceback carefully. Identify the exact line that raised the exception. "
            "Add appropriate error handling or fix the root cause. Re-run to verify the fix."
        ),
        FailureKind.DEPENDENCY: (
            "A dependency conflict or missing package was detected:\n\n{failure_context}\n\n"
            "Check requirements.txt and installed packages. Resolve version conflicts or add "
            "the missing dependency. Prefer pinning to a compatible version over upgrading."
        ),
        FailureKind.TIMEOUT: (
            "The previous attempt timed out:\n\n{failure_context}\n\n"
            "Identify the slow operation. Consider: adding a timeout, optimising the hot path, "
            "using async I/O, or caching results. Measure with a quick benchmark after the fix."
        ),
        FailureKind.ENVIRONMENT: (
            "An environment configuration problem was detected:\n\n{failure_context}\n\n"
            "Check environment variables, paths, and platform-specific conditions. "
            "Ensure the fix is portable (Linux/macOS/Windows)."
        ),
        FailureKind.SECURITY: (
            "A security issue was detected:\n\n{failure_context}\n\n"
            "Do not suppress the security check. Fix the underlying vulnerability. "
            "Common fixes: escape user input, parameterise SQL queries, avoid shell=True, "
            "use secrets.token_hex instead of random."
        ),
        FailureKind.UNKNOWN: (
            "The previous attempt produced an unexpected failure:\n\n{failure_context}\n\n"
            "Read the error carefully. Inspect the relevant files. Apply the minimal fix "
            "that addresses the root cause. Run tests to verify."
        ),
    }

    def __init__(
        self,
        agent: "Agent",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        budget_seconds: float = DEFAULT_REPAIR_BUDGET_SECONDS,
    ) -> None:
        self._agent = agent
        self._max_iterations = max_iterations
        self._budget_seconds = budget_seconds

    def attempt(
        self,
        original_prompt: str,
        failure_context: str,
    ) -> bool:
        """
        Run the repair loop.

        Args:
            original_prompt: The user's original request (for context).
            failure_context: The error output / failure description.

        Returns:
            True if repair succeeded within budget, False otherwise.
        """
        report = self.run(original_prompt, failure_context)
        return report.succeeded

    def run(
        self,
        original_prompt: str,
        failure_context: str,
    ) -> RepairReport:
        """
        Run the full repair loop and return a detailed report.

        Args:
            original_prompt: The user's original request.
            failure_context: The error output / failure description.

        Returns:
            RepairReport with all iteration details.
        """
        report = RepairReport(
            original_prompt=original_prompt,
            failure_context=failure_context,
        )
        deadline = time.monotonic() + self._budget_seconds

        current_failure = failure_context
        for iteration in range(1, self._max_iterations + 1):
            if time.monotonic() >= deadline:
                logger.info("Repair budget exhausted at iteration %d.", iteration)
                break

            t_start = time.monotonic()
            failure_kind = classify_failure(current_failure)
            repair_prompt = self._build_repair_prompt(
                original_prompt=original_prompt,
                failure_context=current_failure,
                failure_kind=failure_kind,
                iteration=iteration,
            )

            logger.info(
                "Repair iteration %d/%d — kind=%s",
                iteration,
                self._max_iterations,
                failure_kind.value,
            )

            # Run the targeted repair via the agent
            evidence_start = len(self._agent.evidence.records())
            try:
                response, events = self._agent._run_hosted_turn(  # noqa: SLF001
                    repair_prompt,
                    analysis={"intent": "fix", "plan_type": "direct"},
                    plan=None,
                    interactive=False,
                    emit_ui=False,
                )
            except Exception as exc:
                logger.warning("Repair iteration %d raised exception: %s", iteration, exc)
                response = str(exc)
                events = []

            duration_ms = int((time.monotonic() - t_start) * 1000)

            # A new mutation is necessary but not sufficient. A repair succeeds
            # only when deterministic project checks run after that mutation and
            # all of those checks pass.
            evidence = self._agent.evidence.records()[evidence_start:]
            mutations = [e for e in evidence if e.get("kind") == "file_mutation"]
            checks = []
            verification_output = ""
            if mutations and all(e.get("status") == "verified" for e in mutations):
                verification_report = self._agent._record_verification_report(  # noqa: SLF001
                    self._agent._run_verification_suite()
                )
                verification_output = verification_report.format_report()
                evidence = self._agent.evidence.records()[evidence_start:]
                checks = [e for e in evidence if e.get("kind") == "verification_check"]
            succeeded = bool(mutations) and bool(checks) and all(
                item.get("status") == "verified" for item in [*mutations, *checks]
            )

            attempt = RepairAttempt(
                iteration=iteration,
                failure_kind=failure_kind,
                repair_prompt=repair_prompt[:500],
                success=succeeded,
                duration_ms=duration_ms,
                evidence_ids=[e.get("id", "") for e in [*mutations, *checks]],
                output=(response + "\n\n" + verification_output)[:2000],
            )
            report.attempts.append(attempt)

            if succeeded:
                report.succeeded = True
                logger.info("Repair succeeded at iteration %d.", iteration)
                break

            # Collect the new failure context for the next iteration
            current_failure = self._extract_failure_from_response(response, events)

        report.total_duration_ms = sum(a.duration_ms for a in report.attempts)
        if not report.succeeded:
            logger.warning("Repair loop exhausted: %s", report.summary())

        return report

    def _build_repair_prompt(
        self,
        original_prompt: str,
        failure_context: str,
        failure_kind: FailureKind,
        iteration: int,
    ) -> str:
        """Construct a targeted repair prompt for the given failure class."""
        template = self._TEMPLATES.get(failure_kind, self._TEMPLATES[FailureKind.UNKNOWN])
        body = template.format(
            original_prompt=original_prompt,
            failure_context=failure_context,
            iteration=iteration,
        )
        return (
            f"[REPAIR ITERATION {iteration}/{self._max_iterations}]\n\n"
            f"Original task: {original_prompt[:300]}\n\n"
            f"{body}"
        )

    @staticmethod
    def _extract_failure_from_response(response: str, events: list[dict[str, Any]]) -> str:
        """Extract the new failure context from a repair attempt's output."""
        # Look for command failures in events
        for event in reversed(events):
            if isinstance(event, dict) and event.get("type") == "tool_call":
                if not event.get("success", True):
                    return event.get("detail", response)[:2000]
        # Fall back to the response text
        return response[:2000]
