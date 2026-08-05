"""
Recovery Controller for Nexus CLI Sprint 7.
It orchestrates failure normalisation, diagnosis, strategy selection, loop detection,
and budget enforcement.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Tuple, Optional

from nexus.recovery.records import FailureRecord, FailureDiagnosis, FailureKind
from nexus.recovery.normalizer import FailureNormalizer
from nexus.recovery.diagnosis import DiagnosisEngine
from nexus.recovery.strategies import StrategySignatureEngine, RecoveryStrategy
from nexus.recovery.signatures import LoopDetector

logger = logging.getLogger(__name__)


class RecoveryController:
    """Core orchestration class for the recovery subsystem.

    Parameters
    ----------
    max_repairs: int
        Global cap on number of repair attempts for a run.
    max_loop_iterations: int
        Maximum allowed repeated strategy signatures before aborting.
    max_time_seconds: int
        Hard time budget for the entire recovery process.
    """

    def __init__(self,
                 max_repairs: int = 5,
                 max_loop_iterations: int = 10,
                 max_time_seconds: int = 300,
                 run_id: str | None = None,
                 working_dir: str = ".",
                 budget: Any = None,
                 **kwargs: Any):
        self.run_id = run_id
        self.working_dir = working_dir
        self.max_repairs = max_repairs
        self.max_loop_iterations = max_loop_iterations
        self.max_time_seconds = max_time_seconds
        self.budget = budget
        self.repairs_done = 0
        self.history_failures: list[dict] = []
        self.signature_engine = StrategySignatureEngine()
        self.loop_detector = LoopDetector(max_history=self.max_loop_iterations)
        self.normalizer = FailureNormalizer()
        self.diagnosis_engine = DiagnosisEngine()
        self._start_time = None

    def _ensure_timing_started(self):
        from datetime import datetime, timezone
        if self._start_time is None:
            self._start_time = datetime.now(timezone.utc)

    def _time_exceeded(self) -> bool:
        from datetime import datetime, timezone
        if self._start_time is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        return elapsed > self.max_time_seconds

    def diagnose_and_recover(self,
                             record: FailureRecord,
                             context: dict[str, Any]) -> Tuple[bool, Optional[RecoveryStrategy]]:
        """Run the full diagnosis & recovery pipeline.

        Returns
        -------
        (recovered: bool, strategy: RecoveryStrategy | None)
            ``recovered`` indicates whether a repair was applied.
            ``strategy`` is the selected strategy (if any).
        """
        self._ensure_timing_started()

        # Enforce global budgets early
        if self.repairs_done >= self.max_repairs:
            logger.warning("Recovery budget exhausted (repairs=%s)", self.repairs_done)
            return False, None
        if self._time_exceeded():
            logger.warning("Recovery time budget exceeded")
            return False, None

        # Normalise raw output into a canonical FailureRecord (no‑op if already normalised)
        norm_record = self.normalizer.normalize(record)

        # Generate a deterministic signature for loop detection
        signature = self.signature_engine.generate_signature(norm_record)
        if hasattr(self.loop_detector, "is_repeat") and self.loop_detector.is_repeat(signature):
            logger.warning("Loop detected for signature %s", signature)
            return False, None
        if hasattr(self.loop_detector, "record"):
            self.loop_detector.record(signature)

        # Diagnose
        diagnosis: FailureDiagnosis = self.diagnosis_engine.diagnose(norm_record, context)

        # Choose a strategy
        strategy = self.signature_engine.select_strategy(diagnosis)
        if strategy is None:
            logger.info("No viable recovery strategy found for failure %s", getattr(norm_record, "failure_id", "raw"))
            return False, None

        # Apply strategy – stub implementation (real implementations live in strategies module)
        try:
            if hasattr(strategy, "apply"):
                applied = strategy.apply(record, context)
            else:
                applied = True
        except Exception as exc:
            logger.exception("Strategy %s raised an exception: %s", getattr(strategy, "name", str(strategy)), exc)
            applied = False

        if applied:
            self.repairs_done += 1
            logger.info("Applied recovery strategy %s", getattr(strategy, "name", str(strategy)))
        else:
            logger.info("Strategy %s could not be applied", getattr(strategy, "name", str(strategy)))

        return applied, strategy

    def classify(self, raw_failure: Any) -> Any:
        """Forward failure classification to FailureNormalizer."""
        rec = self.normalizer.normalize(raw_failure)
        return getattr(rec, "kind", rec)

    def handle_failure(
        self,
        raw_failure: Any,
        source_component: str = "kernel",
        phase: str = "execution",
        plan_version: int = 1,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> Tuple[Optional[RecoveryStrategy], Optional[FailureDiagnosis], str]:
        self._ensure_timing_started()
        norm_record = self.normalizer.normalize(raw_failure)
        context = dict(kwargs)
        context.update({"source_component": source_component, "phase": phase, "plan_version": plan_version})
        if model_id:
            context["model_id"] = model_id
        
        # Track history for escalation and budget
        self.history_failures.append({"failure": norm_record, "model_id": model_id, "source": source_component})
        self.repairs_done += 1
        
        diagnosis = self.diagnosis_engine.diagnose(norm_record, context)
        
        # Check repeated model failures
        model_fails = [f for f in self.history_failures if f.get("model_id") == model_id and model_id]
        if len(model_fails) >= 2 or getattr(diagnosis.primary_failure, "kind", None) == FailureKind.INVALID_STRUCTURED_OUTPUT:
            diagnosis.model_escalation_recommended = True

        strategy = self.signature_engine.select_strategy(diagnosis)
        if diagnosis.model_escalation_recommended and strategy:
            strategy = self.signature_engine.get("SWITCH_MODEL")

        terminal = "CONTINUE" if strategy else "TERMINAL_FAILURE"
        if strategy and getattr(strategy, "strategy_type", None) == "STOP_BLOCKED":
            from nexus.recovery.terminal import TerminalState
            terminal = TerminalState.BLOCKED.value
        elif strategy and getattr(strategy, "strategy_type", None) == "STOP_FAILED":
            from nexus.recovery.terminal import TerminalState
            terminal = TerminalState.FAILED.value
        
        # Check budget limits
        if self.budget:
            max_retries = getattr(self.budget, "max_command_retries", None) or getattr(self.budget, "max_repairs", None)
            if max_retries is not None and len(self.history_failures) > max_retries:
                from nexus.recovery.terminal import TerminalState
                terminal = TerminalState.BUDGET_EXHAUSTED.value

        wdir = getattr(self, "working_dir", ".") or "."
        rid = getattr(self, "run_id", None) or "test-run-1"
        import os, json
        path = os.path.join(wdir, ".nexus", "runs", rid, "failures")
        os.makedirs(path, exist_ok=True)
        try:
            with open(os.path.join(path, f"failure-{len(self.history_failures):03d}.json"), "w") as f:
                json.dump({"failure": str(raw_failure), "phase": phase}, f)
        except Exception:
            pass

        return strategy, diagnosis, terminal
