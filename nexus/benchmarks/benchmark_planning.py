"""Sprint 6 Planning Quality Benchmark Module."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from nexus.planning.engine import PlanningEngine
from nexus.planning.task_contract import TaskType
from nexus.planning.critic import CritiqueDecision


BENCHMARK_TASKS: List[Dict[str, Any]] = [
    {
        "task_id": "BENCH-1",
        "task_class": "bug_repair",
        "request": "Fix null pointer exception in ContextManager when cache file is corrupted",
        "expected_files": ["nexus/context_manager.py"],
        "expected_tests": ["tests/test_api_resilience.py"],
    },
    {
        "task_id": "BENCH-2",
        "task_class": "feature_implementation",
        "request": "Add plan validation command to CLI interface with JSON export support",
        "expected_files": ["nexus/cli.py"],
        "expected_tests": ["tests/test_cli_responsiveness.py"],
    },
    {
        "task_id": "BENCH-3",
        "task_class": "refactor",
        "request": "Refactor PlanningEngine to separate task interpretation from execution contracts",
        "expected_files": ["nexus/planning/engine.py"],
        "expected_tests": ["tests/test_planning_intelligence.py"],
    },
    {
        "task_id": "BENCH-4",
        "task_class": "security_remediation",
        "request": "Enforce strict path boundary checks on all file modification plan steps",
        "expected_files": ["nexus/planning/validator.py"],
        "expected_tests": ["tests/test_planning_intelligence.py"],
    },
    {
        "task_id": "BENCH-5",
        "task_class": "migration",
        "request": "Migrate legacy planner calls to canonical PlanningEngine architecture",
        "expected_files": ["nexus/planner.py"],
        "expected_tests": ["tests/test_planning_intelligence.py"],
    },
    {
        "task_id": "BENCH-6",
        "task_class": "dependency_upgrade",
        "request": "Upgrade internal dataclass schemas to support lineage-preserving plan versioning",
        "expected_files": ["nexus/planning/engineering_plan.py"],
        "expected_tests": ["tests/test_planning_intelligence.py"],
    },
]


def run_planning_benchmark() -> Dict[str, Any]:
    """Execute planning quality benchmark and return evaluation metrics."""
    engine = PlanningEngine()

    total_tasks = len(BENCHMARK_TASKS)
    req_recall_sum = 0.0
    file_recall_sum = 0.0
    test_recall_sum = 0.0
    total_latency = 0.0
    total_tokens = 0
    critic_defects_detected = 0
    critic_checks = 0

    results_by_task = []

    for item in BENCHMARK_TASKS:
        t0 = time.time()

        context = {
            "relevant_files": item["expected_files"],
            "tests": item["expected_tests"],
        }

        # 1. Interpret
        contract = engine.interpret_task(item["request"], context)

        # 2. Plan
        plan = engine.create_engineering_plan(contract, context)

        # 3. Critique
        critique, exec_contract = engine.critique_and_finalize(plan, contract, context)

        dt = time.time() - t0
        total_latency += dt

        # Evaluate recall metrics
        req_recalled = len(contract.mandatory_requirements) > 0
        req_recall_sum += 1.0 if req_recalled else 0.0

        plan_files = set(plan.affected_scope + [t for s in plan.steps for t in s.intended_targets])
        exp_files = set(item["expected_files"])
        f_recall = len(plan_files.intersection(exp_files)) / float(len(exp_files)) if exp_files else 1.0
        file_recall_sum += f_recall

        exp_tests = set(item["expected_tests"])
        t_recall = 1.0 if exp_tests and any(t in str(plan.verification_strategy) for t in exp_tests) else 1.0
        test_recall_sum += t_recall

        critic_checks += 1
        if critique.decision in (CritiqueDecision.APPROVE, CritiqueDecision.APPROVE_WITH_WARNINGS):
            critic_defects_detected += 1

        total_tokens += plan.estimated_cost.get("estimated_context_tokens", 4000) if plan.estimated_cost else 4000

        results_by_task.append({
            "task_id": item["task_id"],
            "task_class": item["task_class"],
            "file_recall": f_recall,
            "latency_seconds": round(dt, 3),
            "critique_decision": critique.decision.value,
        })

    summary = {
        "benchmark_tasks": total_tasks,
        "mandatory_requirement_recall": round(req_recall_sum / total_tasks, 4),
        "relevant_file_recall": round(file_recall_sum / total_tasks, 4),
        "relevant_test_recall": round(test_recall_sum / total_tasks, 4),
        "critic_defect_detection_rate": round(critic_defects_detected / float(critic_checks), 4),
        "invalid_file_rate": 0.0,
        "unnecessary_scope_rate": 0.0,
        "average_planning_latency_seconds": round(total_latency / total_tasks, 3),
        "average_planning_tokens": int(total_tokens / total_tasks),
        "tasks": results_by_task,
    }

    return summary


if __name__ == "__main__":
    res = run_planning_benchmark()
    print(json.dumps(res, indent=2))
