"""
Benchmark Suite for Sprint 8 Multi-File Engineering Intelligence.

Measures performance and correctness metrics across repository-scale operations:
1. Multi-File Impact Analysis Latency & Accuracy
2. Dependency Graph Construction & Topological Sorting
3. Consistency Validator Verification Speed
4. Multi-File Patch Validation & Execution Throughput
5. End-to-End Staged Change-Set Execution Overhead
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from nexus.multifile.consistency import ChangeSetConsistencyValidator
from nexus.multifile.contracts import (
    ChangeType,
    EngineeringChangeSet,
    PlannedFileChange,
    TaskType,
)
from nexus.multifile.graph import build_graph
from nexus.multifile.impact import ImpactAnalyzer
from nexus.multifile.patch import MultiFilePatchManager
from nexus.multifile.staged_execution import StagedChangeSetExecutor


def run_benchmark(file_count: int = 50) -> dict[str, Any]:
    """Run performance and accuracy benchmark suite on synthetic multi-file repositories."""
    results: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_count": file_count,
        "metrics": {},
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        _create_synthetic_repo(repo_root, file_count)

        # Benchmark 1: Impact Analysis Latency
        t0 = time.perf_counter()
        analyzer = ImpactAnalyzer(repo_root)
        callers = analyzer.discover_callers("target_func_0", definition_path="pkg/module_0.py")
        t_impact = (time.perf_counter() - t0) * 1000.0  # ms
        results["metrics"]["impact_analysis_latency_ms"] = round(t_impact, 2)
        results["metrics"]["impact_callers_found"] = len(callers)

        # Benchmark 2: Dependency Graph & Topological Sort Latency
        file_changes = [
            PlannedFileChange(
                path=f"pkg/module_{i}.py",
                reason=f"Refactor module {i}",
                change_type=ChangeType.MODIFY,
                depends_on=[f"pkg/module_{i-1}.py"] if i > 0 else [],
            )
            for i in range(file_count)
        ]
        t0 = time.perf_counter()
        graph = build_graph(file_changes)
        sorted_changes = graph.topological_sort()
        t_graph = (time.perf_counter() - t0) * 1000.0  # ms
        results["metrics"]["graph_topological_sort_latency_ms"] = round(t_graph, 2)
        results["metrics"]["graph_nodes"] = len(sorted_changes)

        # Benchmark 3: Consistency Validator Latency
        cs = EngineeringChangeSet(
            run_id="bm-run",
            task_type=TaskType.REFACTOR,
            file_changes=file_changes + [
                PlannedFileChange(path="tests/test_benchmark.py", reason="Test update", change_type=ChangeType.CREATE)
            ],
        )
        validator = ChangeSetConsistencyValidator(repo_root)
        t0 = time.perf_counter()
        val_result = validator.validate(cs)
        t_val = (time.perf_counter() - t0) * 1000.0  # ms
        results["metrics"]["consistency_validator_latency_ms"] = round(t_val, 2)
        results["metrics"]["validator_status"] = val_result.status.value

        # Benchmark 4: Patch Manager Throughput
        patch_files = {f"pkg/module_{i}.py": f"# Updated module {i}\n" for i in range(file_count)}
        patch_mgr = MultiFilePatchManager(repo_root)
        t0 = time.perf_counter()
        patch_res = patch_mgr.apply_patch(patch_files, cs)
        t_patch = (time.perf_counter() - t0) * 1000.0  # ms
        results["metrics"]["patch_application_latency_ms"] = round(t_patch, 2)
        results["metrics"]["patch_status"] = patch_res.status.value

        # Benchmark 5: Staged Executor End-to-End
        executor = StagedChangeSetExecutor(repo_root, run_dir=repo_root / ".nexus")
        t0 = time.perf_counter()
        exec_res = executor.execute(cs)
        t_exec = (time.perf_counter() - t0) * 1000.0  # ms
        results["metrics"]["staged_execution_latency_ms"] = round(t_exec, 2)
        results["metrics"]["execution_status"] = exec_res.status

    return results


def _create_synthetic_repo(repo_root: Path, count: int) -> None:
    pkg_dir = repo_root / "pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    for i in range(count):
        content = f"def target_func_{i}():\n    return {i}\n"
        if i > 0:
            content += f"from pkg.module_{i-1} import target_func_{i-1}\n"
        (pkg_dir / f"module_{i}.py").write_text(content, encoding="utf-8")

    (tests_dir / "test_benchmark.py").write_text("def test_dummy(): pass\n", encoding="utf-8")


if __name__ == "__main__":
    bm = run_benchmark(50)
    print(json.dumps(bm, indent=2))
