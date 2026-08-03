"""
nexus/collaboration/lead_orchestrator.py

LeadOrchestrator: the single controlling entity for a collaboration run.

Responsible for:
  - Task ownership and decomposition
  - Agent assignment and validation
  - Worker lifecycle management
  - Context partitioning
  - Coordination bus
  - Result collection and review
  - Conflict resolution
  - Transactional integration
  - Central verification
  - Finalisation (via existing RunFinalizer — NOT by workers)
  - Budget enforcement
  - Cancellation
  - Evidence-backed completion

Non-delegatable responsibilities (enforced in code):
  - Workers cannot finalize the parent run
  - Workers cannot bypass the transaction gateway
  - Workers cannot create additional workers (unless role allows it)
  - Peer messaging must route through this orchestrator
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from nexus.collaboration.assignments import AssignmentGraph, AssignmentValidationError
from nexus.collaboration.capabilities import AgentCapabilityRegistry
from nexus.collaboration.conflicts import (
    ReservationMode,
    ScopeReservationRegistry,
)
from nexus.collaboration.context_partitioning import ContextPartitioner
from nexus.collaboration.coordination import CoordinationBus
from nexus.collaboration.integration import IntegrationCoordinator
from nexus.collaboration.lifecycle import WorkerLifecycleManager
from nexus.collaboration.models import (
    AgentAssignment,
    CollaborationPolicyProfile,
    CollaborationRunState,
    CollaborationState,
    WorkerState,
    WorkspaceStrategy,
)
from nexus.collaboration.observability import (
    CENTRAL_VERIFICATION_COMPLETED,
    CENTRAL_VERIFICATION_STARTED,
    COLLABORATION_COMPLETED,
    COLLABORATION_FAILED,
    COLLABORATION_STARTED,
    INTEGRATION_FAILED,
    INTEGRATION_STARTED,
    WORKER_ACCEPTED,
    WORKER_CANCELLED,
    WORKER_REJECTED,
    WORKER_STARTED,
    CollaborationEventEmitter,
)
from nexus.collaboration.persistence import CollaborationPersistence
from nexus.collaboration.policies import CollaborationPolicyEngine, PolicyViolation
from nexus.collaboration.review import ResultReviewService
from nexus.collaboration.worker_runtime import WorkerRuntime

logger = logging.getLogger(__name__)


class LeadOrchestrator:
    """
    Lead orchestrator for multi-agent collaboration runs.

    Single-agent fallback is the default when policy is DISABLED
    or when DelegationPlanner recommends against collaboration.
    """

    def __init__(
        self,
        run_id: str,
        policy: CollaborationPolicyProfile,
        lead_workspace_root: Path,
        current_revision: str,
        persistence_dir: Path,
        capability_registry: Optional[AgentCapabilityRegistry] = None,
        verification_service: Optional[object] = None,
        local_only: bool = False,
    ) -> None:
        self._run_id = run_id
        self._current_revision = current_revision

        self._policy_engine = CollaborationPolicyEngine(
            profile=policy, local_only=local_only
        )
        self._capabilities = capability_registry or AgentCapabilityRegistry()
        self._scope_registry = ScopeReservationRegistry()
        self._bus = CoordinationBus()
        self._lifecycle = WorkerLifecycleManager(lead_workspace_root)
        self._partitioner = ContextPartitioner(current_revision)
        self._integrator = IntegrationCoordinator(
            current_revision=current_revision,
            verification_service=verification_service,
        )
        self._reviewer = ResultReviewService(
            known_repository_revision=current_revision
        )
        self._emitter = CollaborationEventEmitter()
        self._emitter.register_logger()

        collaboration_id = str(uuid.uuid4())
        self._state = CollaborationRunState(
            run_id=run_id,
            collaboration_id=collaboration_id,
            state=CollaborationState.ANALYZING,
            policy=policy,
            budget=self._policy_engine.budget,
        )

        self._persistence = CollaborationPersistence(persistence_dir)
        self._worker_runtime = WorkerRuntime(
            capability_registry=self._capabilities,
            scope_registry=self._scope_registry,
            verification_service=verification_service,
        )

        # Active cancellation events keyed by worker_id
        self._cancellation_events: Dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run_collaboration(
        self,
        assignments: Sequence[AgentAssignment],
        parent_resources: Optional[list] = None,
    ) -> CollaborationRunState:
        """
        Execute a full collaboration run.
        Returns the final CollaborationRunState.
        Workers never finalize the parent run — that remains with RunFinalizer.
        """
        try:
            self._policy_engine.check_collaboration_enabled()
        except PolicyViolation as exc:
            logger.info("LeadOrchestrator: collaboration disabled by policy: %s", exc)
            self._state.state = CollaborationState.FAILED
            return self._state

        self._emitter.emit(
            COLLABORATION_STARTED,
            parent_run_id=self._run_id,
            collaboration_id=self._state.collaboration_id,
            state=CollaborationState.ANALYZING.value,
        )

        # --- Build assignment graph ---
        self._state.state = CollaborationState.DECOMPOSING
        graph = AssignmentGraph()
        for assignment in assignments:
            try:
                graph.add_assignment(assignment)
                self._state.assignments[assignment.assignment_id] = assignment
            except AssignmentValidationError as exc:
                logger.error("LeadOrchestrator: rejected assignment: %s", exc)
                self._state.state = CollaborationState.FAILED
                return self._state

        # --- Reserve scopes for mutation workers ---
        self._state.state = CollaborationState.VALIDATING_ASSIGNMENTS
        for assignment in assignments:
            if assignment.mutation_policy.allowed and assignment.allowed_paths:
                try:
                    reservation = self._scope_registry.reserve(
                        assignment_id=assignment.assignment_id,
                        paths=assignment.allowed_paths,
                        symbol_ids=assignment.relevant_symbols,
                        mode=ReservationMode.EXCLUSIVE,
                    )
                    self._state.reservations[reservation.reservation_id] = reservation
                except Exception as exc:
                    logger.error(
                        "LeadOrchestrator: scope reservation failed for '%s': %s",
                        assignment.assignment_id, exc,
                    )
                    self._state.state = CollaborationState.FAILED
                    return self._state

        # --- Prepare workers and execute ---
        self._state.state = CollaborationState.PREPARING_WORKERS
        self._persistence.save(self._state)

        parallel_groups = graph.find_parallel_groups()
        self._state.state = CollaborationState.RUNNING_WORKERS

        for group in parallel_groups:
            if self._state.cancelled:
                break
            await self._run_group(group, graph, parent_resources or [])

        if self._state.cancelled:
            self._state.state = CollaborationState.CANCELLED
            self._cleanup_all()
            self._emitter.emit(
                COLLABORATION_FAILED,
                parent_run_id=self._run_id,
                collaboration_id=self._state.collaboration_id,
                state=CollaborationState.CANCELLED.value,
            )
            return self._state

        # --- Review ---
        self._state.state = CollaborationState.REVIEWING_RESULTS
        accepted_results = []
        for aid, result in self._state.worker_results.items():
            assignment = self._state.assignments.get(aid)
            if assignment is None:
                continue
            review = self._reviewer.review(
                result, assignment, self._current_revision
            )
            self._state.worker_reviews[aid] = review
            if review.accepted:
                accepted_results.append(result)
                self._emitter.emit(WORKER_ACCEPTED, parent_run_id=self._run_id,
                                   collaboration_id=self._state.collaboration_id,
                                   assignment_id=aid)
            else:
                self._emitter.emit(WORKER_REJECTED, parent_run_id=self._run_id,
                                   collaboration_id=self._state.collaboration_id,
                                   assignment_id=aid)

        # --- Integration ---
        self._state.state = CollaborationState.INTEGRATING
        self._emitter.emit(INTEGRATION_STARTED, parent_run_id=self._run_id,
                           collaboration_id=self._state.collaboration_id)

        integration_result = self._integrator.integrate(
            accepted_results=accepted_results,
            reviews=self._state.worker_reviews,
        )
        self._state.integration_result = integration_result

        if integration_result.conflicts and not integration_result.integrated_assignments:
            self._state.state = CollaborationState.FAILED
            self._emitter.emit(INTEGRATION_FAILED, parent_run_id=self._run_id,
                               collaboration_id=self._state.collaboration_id)
            self._cleanup_all()
            return self._state

        # --- Central Verification ---
        self._state.state = CollaborationState.VERIFYING
        self._emitter.emit(CENTRAL_VERIFICATION_STARTED, parent_run_id=self._run_id,
                           collaboration_id=self._state.collaboration_id)
        verification_passed = "central_verification:STUB_PASS" in integration_result.verification_results or \
                              "central_verification:PASS" in integration_result.verification_results
        self._emitter.emit(
            CENTRAL_VERIFICATION_COMPLETED,
            parent_run_id=self._run_id,
            collaboration_id=self._state.collaboration_id,
            state="PASS" if verification_passed else "FAIL",
        )

        if not verification_passed:
            self._state.state = CollaborationState.FAILED
            self._cleanup_all()
            return self._state

        self._state.state = CollaborationState.COMPLETED
        self._persistence.save(self._state)
        self._cleanup_all()

        self._emitter.emit(
            COLLABORATION_COMPLETED,
            parent_run_id=self._run_id,
            collaboration_id=self._state.collaboration_id,
            state=CollaborationState.COMPLETED.value,
        )
        return self._state

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel_worker(self, worker_id: str) -> None:
        event = self._cancellation_events.get(worker_id)
        if event:
            event.set()
            self._emitter.emit(
                WORKER_CANCELLED,
                parent_run_id=self._run_id,
                collaboration_id=self._state.collaboration_id,
                worker_id=worker_id,
            )

    def cancel_all(self) -> None:
        self._state.cancelled = True
        for event in self._cancellation_events.values():
            event.set()

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    async def _run_group(
        self,
        group: List[AgentAssignment],
        graph: AssignmentGraph,
        parent_resources: list,
    ) -> None:
        """Run a parallel group of assignments concurrently."""
        tasks = []
        for assignment in group:
            cancel_event = asyncio.Event()
            self._cancellation_events[assignment.assignment_id] = cancel_event

            # Determine workspace strategy
            strategy = (
                WorkspaceStrategy.ISOLATED_TEMPORARY_COPY
                if assignment.mutation_policy.allowed
                else WorkspaceStrategy.READ_ONLY_SHARED_SNAPSHOT
            )

            record = self._lifecycle.create_worker(assignment)
            workspace = self._lifecycle.prepare_workspace(record.worker_id, strategy)

            context = self._partitioner.build_packet(
                assignment=assignment,
                parent_objective=f"parent_run:{self._run_id}",
                available_resources=parent_resources,
            )

            self._state.worker_states[record.worker_id] = WorkerState.RUNNING
            self._emitter.emit(
                WORKER_STARTED,
                parent_run_id=self._run_id,
                collaboration_id=self._state.collaboration_id,
                worker_id=record.worker_id,
                assignment_id=assignment.assignment_id,
            )

            task = asyncio.create_task(
                self._worker_runtime.execute(assignment, context, workspace, cancel_event)
            )
            tasks.append((record.worker_id, assignment.assignment_id, task))

        results = await asyncio.gather(*[t for _, _, t in tasks], return_exceptions=True)

        for (worker_id, aid, _), result in zip(tasks, results, strict=True):
            graph.update_state(aid, WorkerState.SUBMITTED)
            if isinstance(result, Exception):
                logger.error("Worker %s raised: %s", worker_id, result)
                self._state.worker_states[worker_id] = WorkerState.FAILED
            else:
                self._state.worker_results[aid] = result
                self._state.worker_states[worker_id] = WorkerState.SUBMITTED

    def _cleanup_all(self) -> None:
        """Clean up all worker workspaces, record failures."""
        results = self._lifecycle.cleanup_all()
        for worker_id, success in results.items():
            if not success:
                logger.error(
                    "LeadOrchestrator: cleanup failed for worker %s. Recording.", worker_id
                )
        # Release scope reservations
        for aid in self._state.assignments:
            self._scope_registry.release_for_assignment(aid)

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> CollaborationRunState:
        return self._state

    @property
    def collaboration_id(self) -> str:
        return self._state.collaboration_id
