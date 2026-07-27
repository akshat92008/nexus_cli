#!/usr/bin/env python3
"""
benchmark_harness.py — Automated Benchmark Execution Engine for Amuara Labs

Executes empirical benchmark suites (HumanEval, MBPP, etc.) against the model.
Features:
  - True execution validation using SandboxExecutor
  - Measures pass@1, compile rate, execution latency
  - Parallel evaluation of candidates
  - Strict isolation and timeouts
  - Integration with standard datasets

Replaces the previous stub-based benchmark system.
"""

import os
import json
import time
import argparse
import tempfile
import subprocess
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from tool_executor import SandboxExecutor
from router import JarvisFable5Router, ReasoningMode


class BenchmarkEngine:
    def __init__(self, output_dir: str = "benchmark_results", max_workers: int = 4):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.max_workers = max_workers
        self.sandbox = SandboxExecutor(timeout_sec=10, max_memory_mb=512)
        
        self.router = JarvisFable5Router()

    def load_dataset(self, dataset_path: str) -> List[Dict[str, Any]]:
        """Load benchmark dataset (e.g. HumanEval JSONL)."""
        tasks = []
        with open(dataset_path, "r") as f:
            for line in f:
                if line.strip():
                    tasks.append(json.loads(line))
        return tasks

    def evaluate_task(self, task: Dict[str, Any], generate_fn=None) -> Dict[str, Any]:
        """Evaluate a single task."""
        task_id = task.get("task_id", task.get("name", "unknown"))
        prompt = task.get("prompt", "")
        test_code = task.get("test", "")
        entry_point = task.get("entry_point", "")

        print(f"[Benchmark] Evaluating {task_id}...")

        # 1. Generation
        start_t = time.time()
        
        if generate_fn:
            # Call actual model inference
            generated_code, tps = generate_fn(prompt)
        else:
            # Fallback/stub for testing the harness itself
            generated_code = prompt + "\n    pass\n" 
            tps = 0.0
            time.sleep(0.1)

        gen_latency = time.time() - start_t

        # Extract code (assuming model outputs markdown blocks or just code)
        code_content = self._extract_code(generated_code)

        # 2. Compilation check
        compiles = False
        import ast
        try:
            ast.parse(code_content)
            compiles = True
        except SyntaxError:
            compiles = False

        # 3. Execution check
        passed = False
        exec_latency = 0.0
        error_msg = ""
        
        if compiles and test_code:
            # Combine generated code and tests
            full_code = f"{code_content}\n\n{test_code}"
            if entry_point and f"check({entry_point})" not in full_code:
                 full_code += f"\ncheck({entry_point})\n"

            exec_start = time.time()
            # Execute in sandbox
            result = self.sandbox.execute("python", full_code)
            exec_latency = time.time() - exec_start
            
            passed = result.get("exit_code") == 0
            if not passed:
                error_msg = result.get("stderr", result.get("stdout", ""))[:500]

        return {
            "task_id": task_id,
            "compiles": compiles,
            "passed": passed,
            "gen_latency_sec": gen_latency,
            "exec_latency_sec": exec_latency,
            "tps": tps,
            "error": error_msg,
            # "code": code_content # Omitted from summary to save space, but could save to disk
        }

    def _extract_code(self, text: str) -> str:
        """Extract Python code from markdown, JSON, or raw text."""
        import re
        import json
        
        # 1. Strip THINKING tags
        text = re.sub(r'<<?THINKING>>?.*?<<?/THINKING>>?', '', text, flags=re.DOTALL)
        text = text.strip()
        
        # 2. Check if it's JSON (Mode Collapse fallback)
        try:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                for key in ['code', 'solution', 'python', 'answer']:
                    if key in data and isinstance(data[key], str) and 'def ' in data[key]:
                        return data[key]
                for val in data.values():
                    if isinstance(val, str) and 'def ' in val:
                        return val
        except Exception:
            pass

        # 3. Look for markdown code blocks
        match = re.search(r'```(?:python)?\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # 4. If raw text, try to find the start of the code
        match = re.search(r'(def |import |from |class ).*', text, re.DOTALL)
        if match:
            return match.group(0).strip()
            
        return text

    def run_suite(self, dataset_path: str, suite_name: str, generate_fn=None) -> Dict[str, Any]:
        """Run benchmark suite using parallel workers."""
        print("====================================================")
        print(f" Executing Benchmark Suite: {suite_name}")
        print(f" Dataset: {dataset_path}")
        print("====================================================")

        tasks = self.load_dataset(dataset_path)
        total_tasks = len(tasks)
        
        if total_tasks == 0:
            print("[Benchmark] Error: No tasks found in dataset.")
            return {}

        results = []
        
        # Parallel evaluation
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self.evaluate_task, task, generate_fn): task 
                for task in tasks
            }
            for future in as_completed(future_to_task):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    print(f"[Benchmark] Exception in task: {e}")

        # Compute metrics
        compiled_count = sum(1 for r in results if r["compiles"])
        passed_count = sum(1 for r in results if r["passed"])
        avg_gen_latency = sum(r["gen_latency_sec"] for r in results) / total_tasks
        avg_exec_latency = sum(r["exec_latency_sec"] for r in results) / total_tasks
        
        pass_1 = (passed_count / total_tasks) * 100.0
        compile_rate = (compiled_count / total_tasks) * 100.0

        summary = {
            "timestamp": time.time(),
            "suite_name": suite_name,
            "total_tasks": total_tasks,
            "pass@1": round(pass_1, 2),
            "compile_rate": round(compile_rate, 2),
            "avg_gen_latency_sec": round(avg_gen_latency, 4),
            "avg_exec_latency_sec": round(avg_exec_latency, 4),
            "individual_results": results
        }

        # Save results
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.output_dir, f"{suite_name}_report_{timestamp_str}.json")
        
        with open(report_path, "w") as f:
            json.dump(summary, f, indent=2)

        print("\n====================================================")
        print(f" Benchmark Summary: {suite_name}")
        print(f"  - Total Tasks:  {total_tasks}")
        print(f"  - Compile Rate: {summary['compile_rate']}%")
        print(f"  - pass@1:       {summary['pass@1']}%")
        print(f"  - Avg Latency:  {summary['avg_gen_latency_sec']}s (gen) + {summary['avg_exec_latency_sec']}s (exec)")
        print(f"  - Report saved: {report_path}")
        print("====================================================\n")

        return summary


def create_mock_humaneval(output_path: str):
    """Create a mock dataset for testing the harness."""
    tasks = [
        {
            "task_id": "HumanEval/0",
            "prompt": "def add(a, b):\n    '''Add two numbers'''\n",
            "test": "def check(candidate):\n    assert candidate(1, 2) == 3\n    assert candidate(5, 5) == 10\n",
            "entry_point": "add"
        },
        {
            "task_id": "HumanEval/1",
            "prompt": "def mult(a, b):\n    '''Multiply two numbers'''\n",
            "test": "def check(candidate):\n    assert candidate(2, 3) == 6\n",
            "entry_point": "mult"
        }
    ]
    with open(output_path, "w") as f:
        for task in tasks:
            f.write(json.dumps(task) + "\n")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amuara Labs Benchmark Engine")
    parser.add_argument("--dataset", type=str, help="Path to benchmark JSONL (e.g. HumanEval.jsonl)")
    parser.add_argument("--suite", type=str, default="custom_suite", help="Name of the benchmark suite")
    parser.add_argument("--output_dir", type=str, default="benchmark_results", help="Output directory")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--mock", action="store_true", help="Run with mock data for testing")
    args = parser.parse_args()

    engine = BenchmarkEngine(output_dir=args.output_dir, max_workers=args.workers)

    if args.mock:
        dataset_path = "mock_dataset.jsonl"
        create_mock_humaneval(dataset_path)
        
        # Dummy generator that outputs correct code for mock tests
        def dummy_generate(prompt):
            if "add" in prompt:
                return "```python\ndef add(a, b):\n    return a + b\n```", 50.0
            else:
                return "```python\ndef mult(a, b):\n    return a * b\n```", 50.0
                
        engine.run_suite(dataset_path, "mock_suite", generate_fn=dummy_generate)
        if os.path.exists(dataset_path):
            os.remove(dataset_path)
    else:
        if not args.dataset:
            print("Error: Please provide --dataset path or run with --mock")
            exit(1)
            
        def model_generate(prompt):
            res = engine.router.generate(prompt)
            return res["text"], res["tokens_per_second"]
            
        engine.run_suite(args.dataset, args.suite, generate_fn=model_generate)
