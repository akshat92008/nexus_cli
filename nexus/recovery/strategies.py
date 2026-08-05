"""
Canonical Recovery Strategy Definitions for Nexus CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RecoveryStrategyType(str, Enum):
    RETRY_TRANSIENT = "RETRY_TRANSIENT"
    RETRY_WITH_CORRECTED_ARGUMENTS = "RETRY_WITH_CORRECTED_ARGUMENTS"
    REQUEST_MISSING_PERMISSION = "REQUEST_MISSING_PERMISSION"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    EXPAND_CONTEXT = "EXPAND_CONTEXT"
    REVISE_PLAN = "REVISE_PLAN"
    REVERT_LAST_MUTATION = "REVERT_LAST_MUTATION"
    ROLLBACK_TO_CHECKPOINT = "ROLLBACK_TO_CHECKPOINT"
    APPLY_SMALLER_PATCH = "APPLY_SMALLER_PATCH"
    CHANGE_TOOL = "CHANGE_TOOL"
    CHANGE_VALIDATION_COMMAND = "CHANGE_VALIDATION_COMMAND"
    INSTALL_OR_CONFIGURE_DEPENDENCY = "INSTALL_OR_CONFIGURE_DEPENDENCY"
    REPRODUCE_FAILURE_DIFFERENTLY = "REPRODUCE_FAILURE_DIFFERENTLY"
    SWITCH_MODEL = "SWITCH_MODEL"
    REDUCE_SCOPE = "REDUCE_SCOPE"
    SPLIT_TASK = "SPLIT_TASK"
    STOP_BLOCKED = "STOP_BLOCKED"
    STOP_FAILED = "STOP_FAILED"


@dataclass
class RecoveryStrategy:
    strategy_type: RecoveryStrategyType
    description: str
    prerequisites: list[str] = field(default_factory=list)
    expected_state_change: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    cost_impact: str = "low"
    risk: str = "low"
    rollback_required: bool = False
    verification_required: bool = True
    max_repetitions: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_type": self.strategy_type.value,
            "description": self.description,
            "prerequisites": self.prerequisites,
            "expected_state_change": self.expected_state_change,
            "allowed_tools": self.allowed_tools,
            "cost_impact": self.cost_impact,
            "risk": self.risk,
            "rollback_required": self.rollback_required,
            "verification_required": self.verification_required,
            "max_repetitions": self.max_repetitions,
            "metadata": self.metadata,
        }


class StrategyRegistry:
    """Catalog of canonical recovery strategies."""

    _STRATEGIES: dict[RecoveryStrategyType, RecoveryStrategy] = {
        RecoveryStrategyType.RETRY_TRANSIENT: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.RETRY_TRANSIENT,
            description="Retry transient execution error once with minor delay.",
            cost_impact="low",
            risk="low",
            max_repetitions=1,
        ),
        RecoveryStrategyType.RETRY_WITH_CORRECTED_ARGUMENTS: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.RETRY_WITH_CORRECTED_ARGUMENTS,
            description="Re-execute tool with corrected parameters.",
            cost_impact="low",
            risk="low",
            max_repetitions=2,
        ),
        RecoveryStrategyType.REQUEST_MISSING_PERMISSION: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.REQUEST_MISSING_PERMISSION,
            description="Request user or policy approval for missing permission.",
            cost_impact="zero",
            risk="low",
            verification_required=False,
            max_repetitions=1,
        ),
        RecoveryStrategyType.REQUEST_CLARIFICATION: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.REQUEST_CLARIFICATION,
            description="Prompt user for clarifying details on ambiguous requirement.",
            cost_impact="zero",
            risk="low",
            verification_required=False,
            max_repetitions=1,
        ),
        RecoveryStrategyType.EXPAND_CONTEXT: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.EXPAND_CONTEXT,
            description="Expand task repository context bundle with missing callers or definitions.",
            cost_impact="medium",
            risk="low",
            max_repetitions=2,
        ),
        RecoveryStrategyType.REVISE_PLAN: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.REVISE_PLAN,
            description="Trigger versioned plan revision based on updated root cause analysis.",
            cost_impact="medium",
            risk="medium",
            max_repetitions=2,
        ),
        RecoveryStrategyType.REVERT_LAST_MUTATION: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.REVERT_LAST_MUTATION,
            description="Revert the most recent invalid file mutation.",
            cost_impact="low",
            risk="medium",
            rollback_required=True,
            max_repetitions=2,
        ),
        RecoveryStrategyType.ROLLBACK_TO_CHECKPOINT: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.ROLLBACK_TO_CHECKPOINT,
            description="Rollback entire repository workspace to last verified task checkpoint.",
            cost_impact="low",
            risk="high",
            rollback_required=True,
            max_repetitions=2,
        ),
        RecoveryStrategyType.APPLY_SMALLER_PATCH: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.APPLY_SMALLER_PATCH,
            description="Apply a minimal, highly targeted patch to fix specific assertion.",
            cost_impact="low",
            risk="low",
            max_repetitions=2,
        ),
        RecoveryStrategyType.CHANGE_TOOL: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.CHANGE_TOOL,
            description="Switch to an alternative equivalent tool implementation.",
            cost_impact="low",
            risk="low",
            max_repetitions=2,
        ),
        RecoveryStrategyType.CHANGE_VALIDATION_COMMAND: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.CHANGE_VALIDATION_COMMAND,
            description="Use a targeted single-test command instead of full test suite.",
            cost_impact="low",
            risk="low",
            max_repetitions=2,
        ),
        RecoveryStrategyType.INSTALL_OR_CONFIGURE_DEPENDENCY: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.INSTALL_OR_CONFIGURE_DEPENDENCY,
            description="Install or configure missing environment dependency.",
            cost_impact="medium",
            risk="medium",
            max_repetitions=1,
        ),
        RecoveryStrategyType.REPRODUCE_FAILURE_DIFFERENTLY: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.REPRODUCE_FAILURE_DIFFERENTLY,
            description="Run reproduction command with extra verbosity or single worker.",
            cost_impact="low",
            risk="low",
            max_repetitions=2,
        ),
        RecoveryStrategyType.SWITCH_MODEL: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.SWITCH_MODEL,
            description="Recommend model escalation for higher reasoning capability.",
            cost_impact="high",
            risk="low",
            max_repetitions=1,
        ),
        RecoveryStrategyType.REDUCE_SCOPE: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.REDUCE_SCOPE,
            description="Reduce execution scope to exclude inherited broken tests.",
            cost_impact="low",
            risk="medium",
            max_repetitions=1,
        ),
        RecoveryStrategyType.SPLIT_TASK: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.SPLIT_TASK,
            description="Decompose failing step into smaller sub-tasks.",
            cost_impact="medium",
            risk="low",
            max_repetitions=1,
        ),
        RecoveryStrategyType.STOP_BLOCKED: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.STOP_BLOCKED,
            description="Stop execution honestly with BLOCKED terminal state.",
            cost_impact="zero",
            risk="zero",
            verification_required=False,
            max_repetitions=0,
        ),
        RecoveryStrategyType.STOP_FAILED: RecoveryStrategy(
            strategy_type=RecoveryStrategyType.STOP_FAILED,
            description="Stop execution honestly with FAILED terminal state.",
            cost_impact="zero",
            risk="zero",
            verification_required=False,
            max_repetitions=0,
        ),
    }

    @classmethod
    def get(cls, strategy_type: RecoveryStrategyType | str) -> RecoveryStrategy:
        st = RecoveryStrategyType(strategy_type) if isinstance(strategy_type, str) else strategy_type
        return cls._STRATEGIES.get(
            st,
            RecoveryStrategy(
                strategy_type=RecoveryStrategyType.STOP_FAILED,
                description="Default stop failed.",
            ),
        )

    @classmethod
    def select_strategy(cls, diagnosis: Any) -> RecoveryStrategy | None:
        prim = getattr(diagnosis, "primary_failure", None)
        if prim:
            kind = getattr(prim, "kind", None)
            if hasattr(kind, "value"):
                kind_str = str(kind.value).lower()
            else:
                kind_str = str(kind or "").lower()
            if kind_str in ("executable_not_found", "policy_blocked", "permission_denied"):
                return cls.get(RecoveryStrategyType.STOP_BLOCKED)
            if kind_str in ("dependency_missing", "dependency", "environment"):
                return cls.get(RecoveryStrategyType.INSTALL_OR_CONFIGURE_DEPENDENCY)
        rec = getattr(diagnosis, "recommended_strategy", None)
        if rec:
            return cls.get(rec)
        hyps = getattr(diagnosis, "hypotheses", [])
        if hyps:
            for h in hyps:
                strat = getattr(h, "recommended_strategy", None)
                if strat:
                    return cls.get(strat)
        return cls.get(RecoveryStrategyType.REVISE_PLAN)

    @classmethod
    def generate_signature(cls, norm_record: Any) -> str:
        fid = getattr(norm_record, "failure_id", "unknown")
        cat = getattr(norm_record, "category", "unknown")
        kind = getattr(norm_record, "kind", "unknown")
        return f"sig-{cat}-{kind}-{fid}"


# Alias for backward-compat import in recovery.controller
StrategySignatureEngine = StrategyRegistry

