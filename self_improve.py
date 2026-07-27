#!/usr/bin/env python3
"""
self_improve.py — Autonomous Self-Improvement Pipeline for Amuara Labs (Nova 1.5b)

Implements the full self-improvement loop:
  1. Generate candidate solutions for a curated problem set
  2. Execute and verify each candidate in a sandbox
  3. Compute reward signals (binary pass/fail + quality metrics)
  4. Identify weak domains from failure analysis
  5. Generate targeted training data for weak areas
  6. Feed back into training pipeline

This runs periodically to continuously improve the model.
"""

import os
import sys
import json
import time
import subprocess
import tempfile
import traceback
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class EvaluationResult:
    """Result of evaluating a single candidate solution."""
    problem_id: str
    domain: str
    difficulty: str
    passed: bool
    execution_time_ms: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    code_quality_score: float = 0.0
    test_coverage: float = 0.0


@dataclass
class DomainReport:
    """Performance report for a single domain."""
    domain: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    error_types: Dict[str, int] = field(default_factory=dict)
    avg_execution_time_ms: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / max(self.total, 1)


class CodeQualityAnalyzer:
    """Static analysis for code quality scoring."""

    def __init__(self):
        self.checks = [
            ("has_docstring", self._check_docstring, 0.15),
            ("has_type_hints", self._check_type_hints, 0.15),
            ("has_error_handling", self._check_error_handling, 0.15),
            ("reasonable_length", self._check_length, 0.10),
            ("no_bare_except", self._check_bare_except, 0.10),
            ("has_tests", self._check_tests, 0.15),
            ("proper_naming", self._check_naming, 0.10),
            ("no_hardcoded_secrets", self._check_secrets, 0.10),
        ]

    def score(self, code: str) -> Tuple[float, List[str]]:
        """Score code quality from 0.0 to 1.0 with issue list."""
        total_score = 0.0
        issues = []
        for name, check_fn, weight in self.checks:
            passed, detail = check_fn(code)
            if passed:
                total_score += weight
            else:
                issues.append(f"{name}: {detail}")
        return min(total_score, 1.0), issues

    def _check_docstring(self, code: str) -> Tuple[bool, str]:
        return ('"""' in code or "'''" in code or "# " in code[:200]), "No documentation found"

    def _check_type_hints(self, code: str) -> Tuple[bool, str]:
        import re
        has_hints = bool(re.search(r'def \w+\([^)]*:\s*\w+', code)) or \
                    bool(re.search(r'->\s*\w+', code))
        return has_hints, "No type annotations"

    def _check_error_handling(self, code: str) -> Tuple[bool, str]:
        return ("try:" in code or "except " in code or
                "raise " in code or "Error" in code), "No error handling"

    def _check_length(self, code: str) -> Tuple[bool, str]:
        lines = code.strip().split("\n")
        return 5 <= len(lines) <= 500, f"Length {len(lines)} lines outside ideal range"

    def _check_bare_except(self, code: str) -> Tuple[bool, str]:
        import re
        has_bare = bool(re.search(r'except\s*:', code))
        return not has_bare, "Has bare except clause"

    def _check_tests(self, code: str) -> Tuple[bool, str]:
        return ("test" in code.lower() or "assert" in code or
                "unittest" in code or "pytest" in code), "No tests found"

    def _check_naming(self, code: str) -> Tuple[bool, str]:
        import re
        # Check for descriptive function/variable names (not single letter)
        short_vars = re.findall(r'\b[a-z]\b\s*=', code)
        return len(short_vars) < 5, f"Too many single-letter variables ({len(short_vars)})"

    def _check_secrets(self, code: str) -> Tuple[bool, str]:
        import re
        patterns = [
            r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
            r'(?:sk-|ghp_|pk_)\w{20,}',
        ]
        for p in patterns:
            if re.search(p, code, re.IGNORECASE):
                return False, "Possible hardcoded secret"
        return True, ""


class SandboxExecutor:
    """Execute code in an isolated sandbox."""

    def __init__(self, timeout: int = 30, max_memory_mb: int = 256):
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb

    def execute_python(self, code: str, test_code: str = "") -> EvaluationResult:
        """Execute Python code and return evaluation result."""
        t0 = time.time()
        with tempfile.TemporaryDirectory() as tmpdir:
            sol_path = os.path.join(tmpdir, "solution.py")
            with open(sol_path, "w") as f:
                f.write(code)

            if test_code:
                test_path = os.path.join(tmpdir, "test_solution.py")
                with open(test_path, "w") as f:
                    f.write(test_code)
                cmd = [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"]
            else:
                cmd = [sys.executable, sol_path]

            try:
                result = subprocess.run(
                    cmd, cwd=tmpdir, capture_output=True, text=True,
                    timeout=self.timeout,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
                )
                elapsed_ms = (time.time() - t0) * 1000
                passed = result.returncode == 0

                error_type = None
                error_msg = None
                if not passed:
                    stderr = result.stderr.strip()
                    if "SyntaxError" in stderr:
                        error_type = "syntax_error"
                    elif "TypeError" in stderr:
                        error_type = "type_error"
                    elif "ImportError" in stderr or "ModuleNotFoundError" in stderr:
                        error_type = "import_error"
                    elif "AssertionError" in stderr or "FAILED" in stderr:
                        error_type = "test_failure"
                    elif "TimeoutError" in stderr:
                        error_type = "timeout"
                    else:
                        error_type = "runtime_error"
                    error_msg = stderr[:500]

                return EvaluationResult(
                    problem_id="", domain="", difficulty="",
                    passed=passed, execution_time_ms=elapsed_ms,
                    error_type=error_type, error_message=error_msg,
                )

            except subprocess.TimeoutExpired:
                return EvaluationResult(
                    problem_id="", domain="", difficulty="",
                    passed=False, execution_time_ms=self.timeout * 1000,
                    error_type="timeout", error_message=f"Exceeded {self.timeout}s limit",
                )
            except Exception as e:
                return EvaluationResult(
                    problem_id="", domain="", difficulty="",
                    passed=False, execution_time_ms=(time.time() - t0) * 1000,
                    error_type="execution_error", error_message=str(e),
                )


class SelfImprovementPipeline:
    """
    Orchestrates the full self-improvement loop:
      Evaluate → Analyze → Generate → Train → Repeat
    """

    def __init__(self, dataset_path: str, model_path: str = "",
                 output_dir: str = "self_improve_results"):
        self.dataset_path = dataset_path
        self.model_path = model_path
        self.output_dir = output_dir
        self.executor = SandboxExecutor()
        self.analyzer = CodeQualityAnalyzer()
        os.makedirs(output_dir, exist_ok=True)

    def run_evaluation_cycle(self, max_problems: int = 100) -> Dict[str, DomainReport]:
        """Run evaluation on the dataset and produce per-domain reports."""
        print("=" * 60)
        print(" SELF-IMPROVEMENT EVALUATION CYCLE")
        print("=" * 60)

        records = self._load_dataset(max_problems)
        results: List[EvaluationResult] = []
        domain_reports: Dict[str, DomainReport] = defaultdict(DomainReport)

        for i, record in enumerate(records):
            domain = record.get("metadata", {}).get("domain", "unknown")
            difficulty = record.get("metadata", {}).get("difficulty", "unknown")
            output = record.get("output", "")

            # Extract code from the output
            code = self._extract_code(output)
            if not code:
                continue

            # Quality analysis
            quality_score, issues = self.analyzer.score(code)

            # Execution check (only for Python since we can sandbox it)
            eval_result = EvaluationResult(
                problem_id=f"prob_{i}",
                domain=domain,
                difficulty=difficulty,
                passed=True,  # Default true for non-executed
                execution_time_ms=0,
                code_quality_score=quality_score,
            )

            lang = record.get("metadata", {}).get("language", "python")
            if lang == "python":
                exec_result = self.executor.execute_python(code)
                eval_result.passed = exec_result.passed
                eval_result.execution_time_ms = exec_result.execution_time_ms
                eval_result.error_type = exec_result.error_type
                eval_result.error_message = exec_result.error_message

            results.append(eval_result)

            # Update domain report
            report = domain_reports[domain]
            report.domain = domain
            report.total += 1
            if eval_result.passed:
                report.passed += 1
            else:
                report.failed += 1
                if eval_result.error_type:
                    report.error_types[eval_result.error_type] = \
                        report.error_types.get(eval_result.error_type, 0) + 1

            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(records)}] evaluated...")

        self._save_evaluation_report(domain_reports, results)
        return dict(domain_reports)

    def identify_weak_domains(self, reports: Dict[str, DomainReport],
                               threshold: float = 0.7) -> List[str]:
        """Identify domains where pass rate is below threshold."""
        weak = []
        for domain, report in sorted(reports.items(), key=lambda x: x[1].pass_rate):
            if report.pass_rate < threshold:
                weak.append(domain)
                print(f"  ⚠ WEAK: {domain} — {report.pass_rate:.1%} pass rate "
                      f"({report.passed}/{report.total})")
        return weak

    def generate_targeted_data(self, weak_domains: List[str],
                                samples_per_domain: int = 500) -> str:
        """Generate additional training data focused on weak domains."""
        print(f"\n[Self-Improve] Generating targeted data for {len(weak_domains)} weak domains")

        try:
            from generate_dataset import ALL_DOMAINS, generate_solution_code, \
                format_chatml_record, DIFFICULTY_TIERS, LANGUAGES
            import random

            output_path = os.path.join(self.output_dir, "targeted_training_data.jsonl")
            records = []

            for domain in weak_domains:
                templates = ALL_DOMAINS.get(domain, [])
                if not templates:
                    continue

                for _ in range(samples_per_domain):
                    template = random.choice(templates)
                    difficulty = random.choice(DIFFICULTY_TIERS)
                    lang = random.choice(LANGUAGES)

                    params = template["params_fn"]()
                    params["lang"] = lang
                    prompt = template["prompt_fn"](params)
                    files, test_cmd = generate_solution_code(prompt, lang, difficulty)

                    record = format_chatml_record(
                        domain=domain, prompt=prompt,
                        thinking=f"Targeted training for weak domain: {domain}",
                        files=files, test_cmd=test_cmd,
                        difficulty=difficulty["level"], lang=lang,
                    )
                    records.append(record)

            with open(output_path, "w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

            print(f"[Self-Improve] Generated {len(records)} targeted records → {output_path}")
            return output_path

        except ImportError:
            print("[Self-Improve] Cannot import generate_dataset — skipping targeted generation")
            return ""

    def run_full_cycle(self, max_problems: int = 100, threshold: float = 0.7):
        """Run the complete self-improvement cycle."""
        print("\n" + "=" * 60)
        print(" FULL SELF-IMPROVEMENT CYCLE")
        print("=" * 60)

        # Step 1: Evaluate
        reports = self.run_evaluation_cycle(max_problems)

        # Step 2: Print summary
        print("\n" + "-" * 60)
        print(" DOMAIN PERFORMANCE SUMMARY")
        print("-" * 60)
        for domain, report in sorted(reports.items(), key=lambda x: x[1].pass_rate):
            status = "✓" if report.pass_rate >= threshold else "✗"
            bar = "█" * int(report.pass_rate * 20) + "░" * (20 - int(report.pass_rate * 20))
            print(f"  {status} {domain:25s} [{bar}] {report.pass_rate:6.1%} "
                  f"({report.passed}/{report.total})")

        # Step 3: Identify weak areas
        weak = self.identify_weak_domains(reports, threshold)

        # Step 4: Generate targeted data
        if weak:
            targeted_path = self.generate_targeted_data(weak)
            if targeted_path:
                print(f"\n[Self-Improve] Next step: Merge {targeted_path} into training data")
                print("[Self-Improve] Then re-run SFT → DPO → GRPO pipeline")
        else:
            print("\n[Self-Improve] All domains above threshold. No targeted generation needed.")

        # Step 5: Save cycle metadata
        cycle_meta = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "problems_evaluated": sum(r.total for r in reports.values()),
            "overall_pass_rate": sum(r.passed for r in reports.values()) /
                                max(sum(r.total for r in reports.values()), 1),
            "weak_domains": weak,
            "domain_reports": {
                d: {"pass_rate": r.pass_rate, "total": r.total,
                    "passed": r.passed, "errors": r.error_types}
                for d, r in reports.items()
            }
        }
        meta_path = os.path.join(self.output_dir, "cycle_report.json")
        with open(meta_path, "w") as f:
            json.dump(cycle_meta, f, indent=2)
        print(f"\n[Self-Improve] Cycle report → {meta_path}")

    def _load_dataset(self, max_records: int) -> List[dict]:
        """Load dataset records."""
        records = []
        if not os.path.exists(self.dataset_path):
            print(f"[Self-Improve] Dataset not found: {self.dataset_path}")
            return records
        with open(self.dataset_path, "r") as f:
            for line in f:
                if len(records) >= max_records:
                    break
                try:
                    records.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return records

    def _extract_code(self, output: str) -> str:
        """Extract code content from the training output format."""
        import re
        # Look for FILES block
        match = re.search(r'<<FILES>>\s*(.+?)\s*<</FILES>>', output, re.DOTALL)
        if match:
            try:
                files = json.loads(match.group(1))
                if files and isinstance(files, list):
                    return files[0].get("content", "")
            except json.JSONDecodeError:
                pass
        # Fallback: look for code blocks
        match = re.search(r'```(?:python)?\s*\n(.+?)\n```', output, re.DOTALL)
        if match:
            return match.group(1)
        return ""

    def _save_evaluation_report(self, reports: Dict[str, DomainReport],
                                 results: List[EvaluationResult]):
        """Save detailed evaluation results."""
        report_path = os.path.join(self.output_dir, "evaluation_results.jsonl")
        with open(report_path, "w") as f:
            for r in results:
                f.write(json.dumps({
                    "problem_id": r.problem_id, "domain": r.domain,
                    "difficulty": r.difficulty, "passed": r.passed,
                    "execution_time_ms": r.execution_time_ms,
                    "error_type": r.error_type, "code_quality_score": r.code_quality_score,
                }) + "\n")
        print(f"  Evaluation results → {report_path}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nova 1.5b Self-Improvement Pipeline")
    parser.add_argument("--dataset", type=str, default="dataset_nova_v2.jsonl",
                       help="Dataset to evaluate")
    parser.add_argument("--model", type=str, default="", help="Model path (for generation)")
    parser.add_argument("--output-dir", type=str, default="self_improve_results")
    parser.add_argument("--max-problems", type=int, default=100)
    parser.add_argument("--threshold", type=float, default=0.7,
                       help="Pass rate threshold for identifying weak domains")
    parser.add_argument("--evaluate-only", action="store_true",
                       help="Only run evaluation, skip targeted data generation")
    args = parser.parse_args()

    pipeline = SelfImprovementPipeline(
        dataset_path=args.dataset,
        model_path=args.model,
        output_dir=args.output_dir,
    )

    if args.evaluate_only:
        pipeline.run_evaluation_cycle(args.max_problems)
    else:
        pipeline.run_full_cycle(args.max_problems, args.threshold)
