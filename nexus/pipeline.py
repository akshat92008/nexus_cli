"""
Canonical Execution Pipeline for Nexus CLI.

Defines the single authoritative execution flow consumed by all modes:
    UserPrompt → RepoUnderstanding → Planning → ContextSelection →
    ModelRouting → Execution → Verification → RepairLoop → IndependentReview → Evidence → Completion

Every mode (interactive, non-interactive, Nova, two-node, CI) calls this same
pipeline, eliminating duplicated business logic.

Usage::

    from nexus.pipeline import ExecutionPipeline, PipelineStage, PipelineResult
    pipeline = ExecutionPipeline(agent)
    result = pipeline.run(user_input)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from nexus.planner import TaskStatus
from nexus.run_state import RunStatus

if TYPE_CHECKING:
    from nexus.agent import Agent

logger = logging.getLogger(__name__)


# ── Pipeline Stages ───────────────────────────────────────────────────────────


class PipelineStage(str, Enum):
    """Ordered stages of the canonical execution pipeline."""

    REPO_UNDERSTANDING = "repo_understanding"
    PLANNING = "planning"
    CONTEXT_SELECTION = "context_selection"
    MODEL_ROUTING = "model_routing"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    REPAIR = "repair"
    REVIEW = "review"
    EVIDENCE = "evidence"
    COMPLETION = "completion"


@dataclass
class StageResult:
    """Outcome of a single pipeline stage."""

    stage: PipelineStage
    success: bool
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class PipelineResult:
    """Complete result of a pipeline execution."""

    user_input: str
    response: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    stage_results: list[StageResult] = field(default_factory=list)
    success: bool = False
    total_duration_ms: int = 0
    model_turns: int = 0
    recovered_from_error: bool = False
    status: str = RunStatus.RUNNING.value
    outcome: str = ""

    def failed_stages(self) -> list[StageResult]:
        """Return stages that did not succeed."""
        return [s for s in self.stage_results if not s.success]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_input": self.user_input[:200],
            "success": self.success,
            "total_duration_ms": self.total_duration_ms,
            "model_turns": self.model_turns,
            "recovered_from_error": self.recovered_from_error,
            "status": self.status,
            "outcome": self.outcome,
            "stages": [
                {
                    "stage": s.stage.value,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                }
                for s in self.stage_results
            ],
        }


# ── Pipeline ──────────────────────────────────────────────────────────────────


class ExecutionPipeline:
    """
    Canonical execution pipeline — the single authoritative path through which
    all agent modes execute user requests.

    Each stage is discrete and independently observable. Failures in optional
    stages (repo understanding, verification) are logged but do not terminate
    execution. Failures in required stages (execution) are propagated.
    """

    def __init__(self, agent: "Agent") -> None:
        self._agent = agent
        self._logger = logging.getLogger(__name__)

    # ── Public entry point ────────────────────────────────────────────────────

    def run(
        self,
        user_input: str,
        *,
        interactive: bool = False,
        emit_ui: bool = False,
    ) -> PipelineResult:
        """
        Execute the full pipeline for a user request.

        Args:
            user_input: The raw user prompt.
            interactive: If True, stream output and support confirmations.
            emit_ui: If True, use the UI layer for progress indicators.

        Returns:
            PipelineResult with response, events and stage metrics.
        """
        pipeline_start = time.monotonic()
        result = PipelineResult(user_input=user_input)
        stage_results = result.stage_results

        # ── Stage 1: Repo Understanding ───────────────────────────────────────
        stage_results.append(self._stage_repo_understanding())

        # ── Stage 2: Planning ─────────────────────────────────────────────────
        analysis, plan, planning_result = self._stage_planning(user_input)
        stage_results.append(planning_result)

        # ── Stage 3: Context Selection ────────────────────────────────────────
        stage_results.append(self._stage_context_selection(user_input))

        # ── Stage 4: Model Routing ────────────────────────────────────────────
        routing_mode = self._stage_model_routing(analysis)
        stage_results.append(
            StageResult(
                stage=PipelineStage.MODEL_ROUTING,
                success=True,
                metadata={"routing_mode": routing_mode},
            )
        )

        self._agent._begin_managed_run(user_input, analysis, plan)

        # ── Stage 5: Execution ────────────────────────────────────────────────
        exec_result = self._stage_execution(
            user_input, analysis, plan, routing_mode, interactive=interactive, emit_ui=emit_ui
        )
        stage_results.append(exec_result["stage_result"])
        if not exec_result["stage_result"].success:
            result.response = exec_result.get("response", "❌ Execution failed.")
            result.events = exec_result.get("events", [])
            result.model_turns = exec_result.get("model_turns", 0)
            result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
            report = self._agent._finish_managed_run(
                result.response,
                result.events,
                status_override=RunStatus.FAILED,
            )
            result.status = report.get("status", RunStatus.FAILED.value)
            result.outcome = report.get("outcome", "FAILED")
            return result

        response = exec_result["response"]
        events = exec_result["events"]
        result.model_turns = exec_result.get("model_turns", 0)

        # ── Stage 6: Verification ─────────────────────────────────────────────
        ver_result = self._stage_verification()
        stage_results.append(ver_result)

        # ── Stage 7: Repair (if verification failed) ──────────────────────────
        if not ver_result.success:
            repair_result = self._stage_repair(user_input, ver_result)
            stage_results.append(repair_result)
            if repair_result.success:
                result.recovered_from_error = True
                ver_result = self._stage_verification()
                stage_results.append(ver_result)

        # ── Stage 8: Independent review ──────────────────────────────────────
        review_result = self._stage_review(routing_mode, ver_result.success)
        stage_results.append(review_result)
        if ver_result.success and not review_result.success and routing_mode == "hosted":
            repair_result = self._stage_repair(user_input, review_result)
            stage_results.append(repair_result)
            if repair_result.success:
                result.recovered_from_error = True
                ver_result = self._stage_verification()
                stage_results.append(ver_result)
                review_result = self._stage_review(routing_mode, ver_result.success)
                stage_results.append(review_result)

        # ── Stage 9: Evidence ─────────────────────────────────────────────────
        stage_results.append(self._stage_evidence())

        report = self._agent._finish_managed_run(response, events)

        # ── Stage 10: Completion ──────────────────────────────────────────────
        result.response = response
        result.events = events
        result.status = report.get("status", RunStatus.UNVERIFIED.value)
        result.outcome = report.get("outcome", result.status)
        result.success = result.status == RunStatus.VERIFIED.value
        result.total_duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        stage_results.append(
            StageResult(
                stage=PipelineStage.COMPLETION,
                success=result.success,
                metadata={"status": result.status, "outcome": result.outcome},
                error="" if result.success else f"Run finished as {result.outcome}",
            )
        )

        return result

    # ── Stage implementations ─────────────────────────────────────────────────

    def _stage_repo_understanding(self) -> StageResult:
        """Refresh the repository graph index if stale."""
        t = time.monotonic()
        try:
            updated = self._agent.repo_graph.build(force=False)
            return StageResult(
                stage=PipelineStage.REPO_UNDERSTANDING,
                success=True,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={
                    "refreshed": updated.scanned_files > 0
                    if hasattr(updated, "scanned_files")
                    else True
                },
            )
        except Exception as exc:
            # Non-fatal: missing graph degrades context quality, not correctness
            self._logger.debug("Repo understanding stage skipped: %s", exc)
            return StageResult(
                stage=PipelineStage.REPO_UNDERSTANDING,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"refreshed": False, "warning": str(exc)},
            )

    def _stage_planning(self, user_input: str) -> tuple[dict[str, Any], Any, StageResult]:
        """Classify intent and generate or retrieve the execution plan."""
        t = time.monotonic()
        try:
            analysis = self._agent.planner.analyze(user_input)
            plan = None
            if analysis.get("plan_type") == "planned":
                repo_summary = (
                    self._agent.repo_graph.summary()
                    if getattr(self._agent, "repo_graph", None)
                    else None
                )
                plan = self._agent.planner.create_plan(
                    user_input, analysis, repo_summary=repo_summary
                )
                verification = self._agent._applicable_verification(  # noqa: SLF001
                    analysis["intent"], analysis.get("skills_needed", [])
                )
                plan.verification_steps = verification
                plan.acceptance_criteria = self._agent.planner._generate_acceptance_criteria(
                    user_input,
                    analysis["intent"],
                    verification,
                )
                for step in plan.steps:
                    step.acceptance_criteria = list(plan.acceptance_criteria)
                    if step.checks:
                        step.checks = list(verification)
            return (
                analysis,
                plan,
                StageResult(
                    stage=PipelineStage.PLANNING,
                    success=True,
                    duration_ms=int((time.monotonic() - t) * 1000),
                    metadata={
                        "intent": str(analysis.get("intent", "")),
                        "plan_type": str(analysis.get("plan_type", "")),
                    },
                ),
            )
        except Exception as exc:
            self._logger.warning("Planning stage error (continuing): %s", exc)
            return (
                {"intent": "unknown", "plan_type": "direct", "skills_needed": []},
                None,
                StageResult(
                    stage=PipelineStage.PLANNING,
                    success=False,
                    duration_ms=int((time.monotonic() - t) * 1000),
                    metadata={"degraded": True},
                    error=str(exc),
                ),
            )

    def _stage_context_selection(self, user_input: str) -> StageResult:
        """Select minimal but sufficient context from the repository graph."""
        t = time.monotonic()
        try:
            if not self._agent._context_gathered:  # noqa: SLF001
                self._agent._gather_context()  # noqa: SLF001
            return StageResult(
                stage=PipelineStage.CONTEXT_SELECTION,
                success=True,
                duration_ms=int((time.monotonic() - t) * 1000),
            )
        except Exception as exc:
            self._logger.debug("Context selection error (non-fatal): %s", exc)
            return StageResult(
                stage=PipelineStage.CONTEXT_SELECTION,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"warning": str(exc)},
            )

    def _stage_model_routing(self, analysis: dict[str, Any]) -> str:
        """Determine which execution path to use for this request."""
        agent = self._agent
        if agent._is_nova_model():  # noqa: SLF001
            return "nova"
        if agent._should_use_two_node(analysis):  # noqa: SLF001
            return "two_node"
        return "hosted"

    def _stage_execution(
        self,
        user_input: str,
        analysis: dict[str, Any],
        plan: Any,
        routing_mode: str,
        *,
        interactive: bool,
        emit_ui: bool,
    ) -> dict[str, Any]:
        """Run the model + tool loop."""
        t = time.monotonic()
        agent = self._agent
        try:
            if routing_mode == "nova":
                response, events = agent._run_nova_turn(user_input, emit_ui=emit_ui)  # noqa: SLF001
            elif routing_mode == "two_node":
                response, events = agent._run_two_node_turn(user_input, analysis, emit_ui=emit_ui)  # noqa: SLF001
            else:
                response, events = self._run_hosted_execution(  # noqa: SLF001
                    user_input,
                    analysis,
                    plan,
                    interactive=interactive,
                    emit_ui=emit_ui,
                )
            execution_failed = bool(
                (response or "").lstrip().upper().startswith(("ERROR:", "BLOCKED:"))
                or (plan is not None and plan.has_failures)
            )
            return {
                "stage_result": StageResult(
                    stage=PipelineStage.EXECUTION,
                    success=not execution_failed,
                    duration_ms=int((time.monotonic() - t) * 1000),
                    error="Execution stopped before the requested work was complete."
                    if execution_failed
                    else "",
                ),
                "response": response,
                "events": events,
                "model_turns": len(
                    [e for e in events if isinstance(e, dict) and e.get("type") == "model_turn"]
                ),
            }
        except Exception as exc:
            self._logger.error("Execution stage failed: %s", exc)
            return {
                "stage_result": StageResult(
                    stage=PipelineStage.EXECUTION,
                    success=False,
                    duration_ms=int((time.monotonic() - t) * 1000),
                    error=str(exc),
                ),
                "response": f"❌ Execution failed: {exc}",
                "events": [],
            }

    def _run_hosted_execution(
        self,
        user_input: str,
        analysis: dict[str, Any],
        plan: Any,
        *,
        interactive: bool,
        emit_ui: bool,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Execute every ready plan step under one global model-turn budget."""

        agent = self._agent
        if plan is None or not getattr(plan, "steps", None):
            return agent._run_hosted_turn(  # noqa: SLF001
                user_input,
                analysis,
                plan,
                interactive=interactive,
                emit_ui=emit_ui,
            )

        all_events: list[dict[str, Any]] = []
        responses: list[str] = []
        turns_used = 0
        while not plan.is_complete and not plan.has_failures:
            current = next(
                (step for step in plan.steps if step.status == TaskStatus.IN_PROGRESS),
                None,
            )
            if current is None:
                current = plan.next_step
                if current is None:
                    break
                agent.planner.advance_step(current.id, TaskStatus.IN_PROGRESS)

            remaining = max(0, agent.max_turns - turns_used)
            if remaining == 0:
                agent.planner.advance_step(
                    current.id,
                    TaskStatus.FAILED,
                    f"Global model-turn budget ({agent.max_turns}) exhausted.",
                )
                break

            step_budget = min(remaining, max(2, int(current.max_tool_calls) + 1))
            step_prompt = (
                f"Original objective:\n{user_input}\n\n"
                f"Autonomous plan step {current.id + 1}/{len(plan.steps)}: "
                f"{current.title}\n{current.description}\n\n"
                "Complete this step now. Inspect actual repository state, use tools as needed, "
                "and do not claim success without tool-backed evidence. Do not commit, push, "
                "deploy, or expand the task scope."
            )
            agent._enforce_plan_tool_contract = True  # noqa: SLF001
            try:
                response, events = agent._run_hosted_turn(  # noqa: SLF001
                    step_prompt,
                    analysis,
                    plan,
                    interactive=interactive,
                    emit_ui=emit_ui,
                    max_turns_override=step_budget,
                )
            finally:
                agent._enforce_plan_tool_contract = False  # noqa: SLF001
            responses.append(response)
            all_events.extend(events)
            turns_used += sum(
                1
                for event in events
                if isinstance(event, dict) and event.get("type") == "model_turn"
            )
            agent.run_ledger.record_tasks(plan.steps)
            agent.run_ledger.record_plan(plan)
            if current.status == TaskStatus.COMPLETED:
                agent.run_ledger.checkpoint(
                    f"plan-step-{current.id}-completed",
                    plan=plan,
                    metadata={"task_id": current.id, "model_turns_used": turns_used},
                )
            if (response or "").lstrip().upper().startswith(("ERROR:", "BLOCKED:")):
                if current.status == TaskStatus.IN_PROGRESS:
                    agent.planner.advance_step(current.id, TaskStatus.FAILED, response[:2000])
                break

        return (responses[-1] if responses else ""), all_events

    def _stage_verification(self) -> StageResult:
        """Run post-execution verification checks."""
        t = time.monotonic()
        try:
            evidence = self._agent.evidence.records()[
                getattr(self._agent, "_turn_evidence_start", 0) :
            ]
            mutations = self._agent._effective_evidence(evidence, "file_mutation")  # noqa: SLF001
            checks = self._agent._effective_evidence(  # noqa: SLF001
                evidence, "verification_check"
            )
            engine_checks = [item for item in checks if item.get("tool") == "verification_engine"]
            if mutations and not engine_checks:
                self._agent._record_verification_report(  # noqa: SLF001
                    self._agent.verifier.run_all()
                )
                evidence = self._agent.evidence.records()[
                    getattr(self._agent, "_turn_evidence_start", 0) :
                ]
                checks = self._agent._effective_evidence(  # noqa: SLF001
                    evidence, "verification_check"
                )
            verified_mutations = all(item.get("status") == "verified" for item in mutations)
            verified_checks = bool(checks) and all(
                item.get("status") == "verified" for item in checks
            )
            verified = (verified_mutations and verified_checks) if mutations else True
            return StageResult(
                stage=PipelineStage.VERIFICATION,
                success=verified,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={
                    "mutations": len(mutations),
                    "verified": sum(1 for e in mutations if e.get("status") == "verified"),
                    "checks": len(checks),
                    "checks_passed": sum(1 for e in checks if e.get("status") == "verified"),
                },
                error=""
                if verified
                else (
                    f"{sum(1 for e in mutations if e.get('status') != 'verified')} "
                    "mutations unverified; "
                    f"{sum(1 for e in checks if e.get('status') != 'verified')} checks failed"
                ),
            )
        except Exception as exc:
            self._logger.debug("Verification stage error: %s", exc)
            return StageResult(
                stage=PipelineStage.VERIFICATION,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"warning": str(exc)},
            )

    def _stage_repair(self, user_input: str, ver_result: StageResult) -> StageResult:
        """Attempt autonomous repair when verification fails."""
        t = time.monotonic()
        try:
            from nexus.repair import RepairLoop  # noqa: PLC0415

            loop = RepairLoop(self._agent)
            repaired = loop.attempt(user_input, failure_context=ver_result.error)
            return StageResult(
                stage=PipelineStage.REPAIR,
                success=repaired,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"attempted": True},
                error="" if repaired else "Repair budget exhausted without success",
            )
        except ImportError:
            # repair module not yet available — skip silently
            return StageResult(
                stage=PipelineStage.REPAIR,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"skipped": True},
            )
        except Exception as exc:
            self._logger.warning("Repair stage error: %s", exc)
            return StageResult(
                stage=PipelineStage.REPAIR,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                error=str(exc),
            )

    def _stage_review(self, routing_mode: str, verification_succeeded: bool) -> StageResult:
        """Require a fail-closed review after deterministic verification."""

        t = time.monotonic()
        if not verification_succeeded:
            return StageResult(
                stage=PipelineStage.REVIEW,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"skipped": True},
                error="Independent review withheld because deterministic verification failed.",
            )
        if routing_mode == "nova":
            return StageResult(
                stage=PipelineStage.REVIEW,
                success=True,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"local_guardrails": True},
            )
        if routing_mode == "two_node":
            evidence = self._agent.evidence.records()[
                getattr(self._agent, "_turn_evidence_start", 0) :
            ]
            reviews = [item for item in evidence if item.get("kind") == "independent_review"]
            approved = bool(reviews) and reviews[-1].get("status") == "verified"
            return StageResult(
                stage=PipelineStage.REVIEW,
                success=approved,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"review_records": len(reviews)},
                error="Two-node reviewer did not approve the final candidate."
                if not approved
                else "",
            )
        try:
            approved, summary = self._agent._run_independent_review()  # noqa: SLF001
            return StageResult(
                stage=PipelineStage.REVIEW,
                success=approved,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"summary": summary[:1000]},
                error="" if approved else summary[:2000],
            )
        except Exception as exc:
            return StageResult(
                stage=PipelineStage.REVIEW,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                error=f"Independent review failed closed: {exc}",
            )

    def _stage_evidence(self) -> StageResult:
        """Snapshot evidence and finalize the run record."""
        t = time.monotonic()
        try:
            count = len(self._agent.evidence.records())
            return StageResult(
                stage=PipelineStage.EVIDENCE,
                success=True,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"evidence_records": count},
            )
        except Exception as exc:
            return StageResult(
                stage=PipelineStage.EVIDENCE,
                success=False,
                duration_ms=int((time.monotonic() - t) * 1000),
                metadata={"warning": str(exc)},
            )
