"""Context quality benchmark for Nexus Repository Intelligence — Sprint 5."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from nexus.intelligence.repository.engine import RepositoryIntelligence


BENCHMARK_TASKS = [
    {
        "id": "task_1_python_bug",
        "description": "Fix bug in VerificationResult finalization authority in nexus/verification.py nexus/run_finalizer.py",
        "oracle_files": ["nexus/verification.py", "nexus/run_finalizer.py"],
        "oracle_symbols": ["VerificationResult", "finalize"],
        "oracle_tests": ["tests/test_sprint2_verification.py"],
    },
    {
        "id": "task_2_signature_change",
        "description": "Update ProcessExecutionGateway signature and call sites in nexus/process_gateway.py nexus/tools.py nexus/sandbox.py",
        "oracle_files": ["nexus/process_gateway.py", "nexus/tools.py", "nexus/sandbox.py"],
        "oracle_symbols": ["ProcessExecutionGateway", "ProcessRequest"],
        "oracle_tests": ["tests/test_sandbox.py"],
    },
    {
        "id": "task_3_typescript_feature",
        "description": "Add new CLI command handler feature in nexus/cli.py nexus/agent.py",
        "oracle_files": ["nexus/cli.py", "nexus/agent.py"],
        "oracle_symbols": ["Agent", "main"],
        "oracle_tests": ["tests/test_cli_coverage.py"],
    },
    {
        "id": "task_4_config_bug",
        "description": "Fix pyproject.toml build configuration and requirements.txt dependency constraints",
        "oracle_files": ["pyproject.toml", "requirements.txt"],
        "oracle_symbols": ["dependencies"],
        "oracle_tests": [],
    },
    {
        "id": "task_5_high_risk_auth",
        "description": "Modify network policy and authentication token verification in nexus/network_policy.py nexus/safety.py",
        "oracle_files": ["nexus/network_policy.py", "nexus/safety.py"],
        "oracle_symbols": ["NetworkPolicyManager"],
        "oracle_tests": ["tests/test_network_policy.py"],
    },
    {
        "id": "task_6_monorepo_scope",
        "description": "Refactor pipeline turn coordinator in nexus/turn_coordinator.py nexus/pipeline.py",
        "oracle_files": ["nexus/turn_coordinator.py", "nexus/pipeline.py"],
        "oracle_symbols": ["TurnCoordinator"],
        "oracle_tests": [],
    },
]


class ContextSelectionBenchmark:
    """Evaluates context selection quality against ground-truth oracle tasks."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.engine = RepositoryIntelligence(self.root)
        self.engine.build(force=False)

    def run_benchmark(self) -> dict[str, Any]:
        results = []
        total_recall = 0.0
        total_precision = 0.0
        total_test_recall = 0.0
        total_tokens = 0
        latencies = []

        for task in BENCHMARK_TASKS:
            start_time = time.perf_counter()
            bundle = self.engine.context_bundle(task["description"], max_files=12)
            latency = time.perf_counter() - start_time
            latencies.append(latency)

            selected_paths = {f.path for f in bundle.files}
            oracle_paths = set(task["oracle_files"])
            oracle_tests = set(task["oracle_tests"])

            matched_files = selected_paths.intersection(oracle_paths)
            recall = len(matched_files) / len(oracle_paths) if oracle_paths else 1.0
            precision = len(matched_files) / len(selected_paths) if selected_paths else 1.0

            selected_tests = {t.test_file for t in bundle.tests}
            matched_tests = selected_tests.intersection(oracle_tests)
            test_recall = len(matched_tests) / len(oracle_tests) if oracle_tests else 1.0

            total_recall += recall
            total_precision += precision
            total_test_recall += test_recall
            total_tokens += bundle.estimated_tokens

            results.append({
                "task_id": task["id"],
                "description": task["description"],
                "intent": bundle.task_intent.value,
                "selected_files_count": len(bundle.files),
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "test_recall": round(test_recall, 4),
                "tokens": bundle.estimated_tokens,
                "latency_seconds": round(latency, 4),
            })

        count = len(BENCHMARK_TASKS)
        summary = {
            "tasks_evaluated": count,
            "mean_relevant_file_recall": round(total_recall / count, 4),
            "mean_precision": round(total_precision / count, 4),
            "mean_relevant_test_recall": round(total_test_recall / count, 4),
            "average_selected_tokens": round(total_tokens / count, 1),
            "average_latency_seconds": round(sum(latencies) / count, 4),
            "details": results,
        }
        return summary


if __name__ == "__main__":
    benchmark = ContextSelectionBenchmark(".")
    report = benchmark.run_benchmark()
    print(json.dumps(report, indent=2))
