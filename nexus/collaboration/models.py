"""
nexus/collaboration/models.py

Core models for controlled multi-agent collaboration.
Every public type used across the collaboration sub-package is defined here
so that the rest of the package can import from a single, stable location
without creating circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from nexus.routing.models import ModelTier

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CollaborationState(Enum):
    ANALYZING = "analyzing"
    DECOMPOSING = "decomposing"
    VALIDATING_ASSIGNMENTS = "validating_assignments"
    PREPARING_WORKERS = "preparing_workers"
    RUNNING_WORKERS = "running_workers"
    COLLECTING_RESULTS = "collecting_results"
    REVIEWING_RESULTS = "reviewing_results"
    RESOLVING_CONFLICTS = "resolving_conflicts"
    INTEGRATING = "integrating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerState(Enum):
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CLEANED_UP = "cleaned_up"


class AgentRole(Enum):
    LEAD_ENGINEER = "LEAD_ENGINEER"
    REPOSITORY_ANALYST = "REPOSITORY_ANALYST"
    IMPLEMENTATION_ENGINEER = "IMPLEMENTATION_ENGINEER"
    TEST_ENGINEER = "TEST_ENGINEER"
    DEBUGGER = "DEBUGGER"
    SECURITY_REVIEWER = "SECURITY_REVIEWER"
    ARCHITECTURE_REVIEWER = "ARCHITECTURE_REVIEWER"
    DEPENDENCY_SPECIALIST = "DEPENDENCY_SPECIALIST"
    DOCUMENTATION_ENGINEER = "DOCUMENTATION_ENGINEER"
    INDEPENDENT_VERIFIER = "INDEPENDENT_VERIFIER"


class RiskLevel(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkspaceStrategy(Enum):
    READ_ONLY_SHARED_SNAPSHOT = "READ_ONLY_SHARED_SNAPSHOT"
    ISOLATED_WORKTREE = "ISOLATED_WORKTREE"
    ISOLATED_TEMPORARY_COPY = "ISOLATED_TEMPORARY_COPY"


class ReservationMode(Enum):
    EXCLUSIVE = "exclusive"
    SHARED_READ = "shared_read"


class WorkerResultStatus(Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INVALID = "INVALID"


class CoordinationMessageType(Enum):
    CONTEXT_REQUEST = "CONTEXT_REQUEST"
    CLARIFICATION_REQUEST = "CLARIFICATION_REQUEST"
    DEPENDENCY_UPDATE = "DEPENDENCY_UPDATE"
    BLOCKER_REPORT = "BLOCKER_REPORT"
    RESULT_SUBMISSION = "RESULT_SUBMISSION"
    CANCELLATION = "CANCELLATION"
    REVISION_REQUEST = "REVISION_REQUEST"


class ReviewFindingCategory(Enum):
    MISSING_EVIDENCE = "missing_evidence"
    UNPLANNED_FILE = "unplanned_file"
    POLICY_VIOLATION = "policy_violation"
    SECURITY_RISK = "security_risk"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    SCOPE_VIOLATION = "scope_violation"
    VERIFICATION_FAILURE = "verification_failure"
    ASSIGNMENT_NONCOMPLIANCE = "assignment_noncompliance"


class CollaborationPolicyProfile(Enum):
    DISABLED = "DISABLED"
    INVESTIGATION_ONLY = "INVESTIGATION_ONLY"
    REVIEW_ONLY = "REVIEW_ONLY"
    CONTROLLED_PARALLEL = "CONTROLLED_PARALLEL"
    CUSTOM = "CUSTOM"


class ArchitectureReviewDecision(Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_WARNINGS = "APPROVE_WITH_WARNINGS"
    REVISE = "REVISE"
    BLOCK = "BLOCK"


class SecurityFindingSeverity(Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkerRecoveryAction(Enum):
    RETRY_WORKER = "RETRY_WORKER"
    REASSIGN_WITH_DIFFERENT_MODEL = "REASSIGN_WITH_DIFFERENT_MODEL"
    REDUCE_ASSIGNMENT_SCOPE = "REDUCE_ASSIGNMENT_SCOPE"
    REQUEST_MORE_CONTEXT = "REQUEST_MORE_CONTEXT"
    CONVERT_TO_SEQUENTIAL_WORK = "CONVERT_TO_SEQUENTIAL_WORK"
    REPLAN_ASSIGNMENT = "REPLAN_ASSIGNMENT"
    MARK_OPTIONAL_FAILURE = "MARK_OPTIONAL_FAILURE"
    ABORT_COLLABORATION = "ABORT_COLLABORATION"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentCapabilityProfile:
    role: AgentRole
    supported_task_types: Tuple[str, ...]
    supported_languages: Tuple[str, ...]
    allowed_tool_capabilities: Tuple[str, ...]
    mutation_allowed: bool
    maximum_risk_level: RiskLevel
    preferred_model_tiers: Tuple[ModelTier, ...]
    context_budget: int
    can_request_approval: bool
    can_create_workers: bool


@dataclass(frozen=True)
class MutationPolicy:
    allowed: bool
    require_transaction: bool = True
    max_files_per_turn: int = 10
    prohibited_patterns: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkerBudget:
    max_model_calls: int
    max_tool_calls: int
    max_tokens: int
    max_cost_usd: Optional[Decimal]
    max_wall_clock_seconds: int
    max_retries: int = 2


@dataclass(frozen=True)
class RoutingConstraints:
    """Lightweight routing constraints for worker assignments (not the full engine type)."""
    local_only: bool = False
    max_tier: Optional[ModelTier] = None
    preferred_model_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AssignmentScope:
    description: str
    packages: Tuple[str, ...]
    is_bounded: bool = True


@dataclass(frozen=True)
class AgentAssignment:
    assignment_id: str
    parent_run_id: str
    role: AgentRole
    objective: str
    scope: AssignmentScope
    allowed_paths: Tuple[Path, ...]
    prohibited_paths: Tuple[Path, ...]
    relevant_symbols: Tuple[str, ...]
    requirements: Tuple[str, ...]
    expected_outputs: Tuple[str, ...]
    verification_requirements: Tuple[str, ...]
    dependencies: Tuple[str, ...]
    mutation_policy: MutationPolicy
    model_constraints: RoutingConstraints
    budget: WorkerBudget
    deadline_seconds: int
    is_optional: bool = False


@dataclass(frozen=True)
class DelegationAssessment:
    collaboration_recommended: bool
    expected_benefit: float
    coordination_cost: float
    parallelizable_work: Tuple[str, ...]
    sequential_dependencies: Tuple[str, ...]
    risks: Tuple[str, ...]
    maximum_workers: int
    evidence_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ContextResource:
    resource_id: str
    kind: str  # "file", "symbol", "test", "requirement"
    path: Optional[str]
    content_hash: Optional[str]


@dataclass(frozen=True)
class WorkerContextPacket:
    assignment_id: str
    objective: str
    role: AgentRole
    constraints: Tuple[str, ...]
    allowed_resources: Tuple[ContextResource, ...]
    dependency_summary: str
    relevant_evidence: Tuple[str, ...]
    expected_output_schema: str
    token_count: int
    repository_revision: str


@dataclass(frozen=True)
class WorkerWorkspace:
    workspace_id: str
    assignment_id: str
    strategy: WorkspaceStrategy
    root_path: Path
    is_writable: bool
    created_at: datetime
    cleaned_up: bool = False


@dataclass(frozen=True)
class MutationScopeReservation:
    reservation_id: str
    assignment_id: str
    paths: Tuple[Path, ...]
    symbol_ids: Tuple[str, ...]
    mode: ReservationMode
    expires_at: datetime


@dataclass(frozen=True)
class CoordinationMessage:
    message_id: str
    sender_id: str
    recipient_id: str
    message_type: CoordinationMessageType
    assignment_id: str
    content: Mapping[str, Any]
    evidence_ids: Tuple[str, ...]
    timestamp: datetime


@dataclass(frozen=True)
class WorkerFinding:
    finding_id: str
    description: str
    severity: RiskLevel
    evidence_ids: Tuple[str, ...]
    affected_paths: Tuple[str, ...]


@dataclass(frozen=True)
class ProposedChange:
    change_id: str
    path: str
    description: str
    diff_reference: Optional[str]
    transaction_ref: Optional[str]


@dataclass(frozen=True)
class ResourceUsage:
    model_calls: int
    tool_calls: int
    tokens_used: int
    cost_usd: Optional[Decimal]
    wall_clock_seconds: float


@dataclass(frozen=True)
class WorkerResult:
    assignment_id: str
    worker_id: str
    status: WorkerResultStatus
    summary: str
    findings: Tuple[WorkerFinding, ...]
    proposed_changes: Tuple[ProposedChange, ...]
    transaction_reference: Optional[str]
    verification_results: Tuple[str, ...]
    unresolved_questions: Tuple[str, ...]
    risks: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    cost: ResourceUsage


@dataclass(frozen=True)
class ReviewFinding:
    finding_id: str
    category: ReviewFindingCategory
    description: str
    severity: RiskLevel


@dataclass(frozen=True)
class WorkerReview:
    assignment_id: str
    accepted: bool
    findings: Tuple[ReviewFinding, ...]
    missing_evidence: Tuple[str, ...]
    required_revisions: Tuple[str, ...]
    integration_eligible: bool


@dataclass(frozen=True)
class SecurityFinding:
    finding_id: str
    title: str
    severity: SecurityFindingSeverity
    evidence: Tuple[str, ...]
    exploit_preconditions: Tuple[str, ...]
    affected_files: Tuple[str, ...]
    recommended_remediation: str
    confidence: float


@dataclass(frozen=True)
class IntegrationResult:
    integrated_assignments: Tuple[str, ...]
    rejected_assignments: Tuple[str, ...]
    conflicts: Tuple[str, ...]
    verification_results: Tuple[str, ...]
    transaction_id: str
    evidence_ids: Tuple[str, ...]


@dataclass(frozen=True)
class CollaborationBudget:
    maximum_workers: int
    maximum_parallel_workers: int
    maximum_total_model_calls: int
    maximum_total_tool_calls: int
    maximum_total_tokens: int
    maximum_total_cost_usd: Optional[Decimal]
    maximum_wall_clock_seconds: int
    maximum_worker_retries: int
    maximum_reassignments: int


@dataclass
class CollaborationRunState:
    """Mutable state container for a live collaboration run (not frozen — evolves)."""
    run_id: str
    collaboration_id: str
    state: CollaborationState
    policy: CollaborationPolicyProfile
    budget: CollaborationBudget
    assignments: dict = field(default_factory=dict)  # assignment_id -> AgentAssignment
    worker_states: dict = field(default_factory=dict)  # worker_id -> WorkerState
    worker_results: dict = field(default_factory=dict)  # assignment_id -> WorkerResult
    worker_reviews: dict = field(default_factory=dict)  # assignment_id -> WorkerReview
    reservations: dict = field(default_factory=dict)   # reservation_id -> MutationScopeReservation
    integration_result: Optional[IntegrationResult] = None
    cancelled: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def total_spent(self) -> ResourceUsage:
        calls = sum(r.cost.model_calls for r in self.worker_results.values())
        tools = sum(r.cost.tool_calls for r in self.worker_results.values())
        tokens = sum(r.cost.tokens_used for r in self.worker_results.values())
        costs = [r.cost.cost_usd for r in self.worker_results.values() if r.cost.cost_usd is not None]
        total_cost = sum(costs, Decimal("0")) if costs else None
        wall = sum(r.cost.wall_clock_seconds for r in self.worker_results.values())
        return ResourceUsage(
            model_calls=calls,
            tool_calls=tools,
            tokens_used=tokens,
            cost_usd=total_cost,
            wall_clock_seconds=wall,
        )
