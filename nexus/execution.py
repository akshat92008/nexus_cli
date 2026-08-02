from nexus.execution_engine import ExecutionEngine
"""Compatibility shim: ``nexus.execution`` public surface.

The DAG-oriented execution engine and its supporting types live in
:mod:`nexus.runtime.kernel`.  This module re-exports them under the names
that the release gate, ``test_final_runtime``, and ``test_two_node_backend``
expect, so no test changes are required.

Usage::

    from nexus.execution import ExecutionEngine, TaskOutcome, ReviewOutcome, classify_failure
"""

from nexus.runtime.kernel import (
    ExecutionResult,
    FailureKind,
    PlanReviewer,
    ReviewOutcome,
    StepExecutor,
    StepRepairer,
    StepVerifier,
    TaskOutcome,
    classify_failure,
)

__all__ = [
    "ExecutionEngine",
    "ExecutionResult",
    "FailureKind",
    "ReviewOutcome",
    "StepExecutor",
    "StepRepairer",
    "StepVerifier",
    "PlanReviewer",
    "TaskOutcome",
    "classify_failure",
]
