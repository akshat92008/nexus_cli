"""
nexus/collaboration/__init__.py

Public API for the Nexus multi-agent collaboration subsystem.

Import surface deliberately kept narrow. Internals are accessed
via the specific sub-modules.
"""

from nexus.collaboration.assignments import AssignmentGraph
from nexus.collaboration.capabilities import AgentCapabilityRegistry
from nexus.collaboration.conflicts import ScopeReservationRegistry
from nexus.collaboration.coordination import CoordinationBus
from nexus.collaboration.delegation import DelegationPlanner, TaskCharacteristics
from nexus.collaboration.lead_orchestrator import LeadOrchestrator
from nexus.collaboration.models import (
    AgentAssignment,
    AgentRole,
    AssignmentScope,
    CollaborationBudget,
    CollaborationPolicyProfile,
    CollaborationState,
    DelegationAssessment,
    MutationPolicy,
    RoutingConstraints,
    WorkerBudget,
    WorkerResult,
    WorkerResultStatus,
    WorkerReview,
    WorkerState,
)
from nexus.collaboration.observability import CollaborationEventEmitter
from nexus.collaboration.policies import CollaborationPolicyEngine, default_budget
from nexus.collaboration.worker_runtime import WorkerRuntime

__all__ = [
    # Orchestrators
    "LeadOrchestrator",
    "WorkerRuntime",
    # Models
    "AgentRole",
    "AgentAssignment",
    "AssignmentScope",
    "CollaborationBudget",
    "CollaborationPolicyProfile",
    "CollaborationState",
    "WorkerState",
    "WorkerResult",
    "WorkerResultStatus",
    "WorkerReview",
    "DelegationAssessment",
    "MutationPolicy",
    "WorkerBudget",
    "RoutingConstraints",
    # Services
    "AgentCapabilityRegistry",
    "DelegationPlanner",
    "TaskCharacteristics",
    "AssignmentGraph",
    "ScopeReservationRegistry",
    "CoordinationBus",
    "CollaborationPolicyEngine",
    "CollaborationEventEmitter",
    "default_budget",
]
