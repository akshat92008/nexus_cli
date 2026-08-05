"""Versioned Replanning Architecture (Sprint 6)."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from nexus.planning.engineering_plan import EngineeringPlan, PlanStep
from nexus.planning.task_contract import TaskContract


class PlanReplanner:
    """Manages plan revisions, evidence-based invalidation, and prevents infinite replanning loops."""

    def __init__(self, max_revisions: int = 5):
        self.max_revisions = max_revisions
        self.plan_history: Dict[int, EngineeringPlan] = {}
        self.signature_history: List[str] = []

    def compute_plan_signature(self, plan: EngineeringPlan) -> str:
        """Create hash signature of plan steps and targets to detect duplicate loops."""
        content = []
        for s in plan.steps:
            content.append(f"{s.title}:{s.action_type}:{s.objective}:{','.join(s.intended_targets)}")
        sig = hashlib.sha256(";".join(content).encode("utf-8")).hexdigest()
        return sig

    def revise_plan(
        self,
        current_plan: EngineeringPlan,
        trigger_reason: str,
        failed_step_id: Optional[str] = None,
        new_evidence: Optional[Dict[str, Any]] = None,
    ) -> Tuple[EngineeringPlan, bool]:
        """Revise an existing plan due to new evidence or step failure. Returns (revised_plan, success)."""
        if current_plan.version >= self.max_revisions:
            return current_plan, False

        current_sig = self.compute_plan_signature(current_plan)
        if current_sig not in self.signature_history:
            self.signature_history.append(current_sig)

        revised = copy.deepcopy(current_plan)
        revised.version += 1

        # Mark failed step if any and update steps
        new_steps: List[PlanStep] = []
        for s in revised.steps:
            if s.step_id == failed_step_id:
                s.objective += f" (Revised attempt following: {trigger_reason[:50]})"
            new_steps.append(s)

        revised.steps = new_steps

        # Check signature loop against past revisions
        new_sig = self.compute_plan_signature(revised)
        if new_sig in self.signature_history:
            # Infinite replanning loop detected!
            return current_plan, False

        # Save history
        self.plan_history[current_plan.version] = copy.deepcopy(current_plan)
        self.signature_history.append(new_sig)

        return revised, True
