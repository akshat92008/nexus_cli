#!/usr/bin/env python3
"""
smoke_test.py — Format Compliance & Performance Smoke Test (Amaura)

Runs 20 curated test prompts against the Nova 3B model and validates:
  1. Format compliance (all 3 blocks present, correct order)
  2. Code quality (valid syntax, filepath/action headers)
  3. Performance (tokens/sec, time-to-first-token)

Usage:
  python smoke_test.py                    # Test default nova3b model
  python smoke_test.py --model nova3b-dev # Test dev model
  python smoke_test.py --report           # Generate detailed report

Part of the Nova model family by Amaura.
"""

import json
import time
import sys
import os
import argparse
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field

from ollama_client import OllamaClient, GenerationResult
from output_parser import NovaOutputParser, ParsedResponse


# ═══════════════════════════════════════════════════════════════════════════════
# Test Suite
# ═══════════════════════════════════════════════════════════════════════════════

SMOKE_TESTS = [
    # ─── Single Function (Core) ───────────────────────────────────────────
    {
        "id": "SF-01",
        "category": "single_function",
        "prompt": "Write a Python function called 'is_palindrome' that checks if a string is a palindrome. Handle empty strings and ignore case.",
        "expect_action": "CREATE",
    },
    {
        "id": "SF-02",
        "category": "single_function",
        "prompt": "Implement a function `fibonacci(n: int) -> int` that returns the nth Fibonacci number using iteration, not recursion.",
        "expect_action": "CREATE",
    },
    {
        "id": "SF-03",
        "category": "single_function",
        "prompt": "Write a Python function to find the longest common prefix among a list of strings. Return an empty string if there is no common prefix.",
        "expect_action": "CREATE",
    },
    {
        "id": "SF-04",
        "category": "single_function",
        "prompt": "Create a function `merge_sorted_lists(list1, list2)` that merges two sorted lists into one sorted list without using the built-in sort.",
        "expect_action": "CREATE",
    },
    {
        "id": "SF-05",
        "category": "single_function",
        "prompt": "Implement a rate limiter class with a `is_allowed(user_id: str) -> bool` method using the token bucket algorithm. Allow 10 requests per minute.",
        "expect_action": "CREATE",
    },

    # ─── Bug Fix ──────────────────────────────────────────────────────────
    {
        "id": "BF-01",
        "category": "bug_fix",
        "prompt": "Fix the bug in this function:\n```python\ndef binary_search(arr, target):\n    left, right = 0, len(arr)\n    while left < right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid\n        else:\n            right = mid\n    return -1\n```\nThe function enters an infinite loop for some inputs.",
        "expect_action": "MODIFY",
    },
    {
        "id": "BF-02",
        "category": "bug_fix",
        "prompt": "Fix: `calculate_average` throws `ZeroDivisionError` when given an empty list. File: src/math_utils.py. It should return 0.0 for empty inputs.",
        "expect_action": "MODIFY",
    },
    {
        "id": "BF-03",
        "category": "bug_fix",
        "prompt": "The function `parse_json_config(filepath)` crashes with `FileNotFoundError` when the config file doesn't exist. Add proper error handling to return a default config dict instead.",
        "expect_action": "MODIFY",
    },

    # ─── Refactor ─────────────────────────────────────────────────────────
    {
        "id": "RF-01",
        "category": "refactor",
        "prompt": "Refactor this function to use a dictionary for O(1) lookup instead of a list:\n```python\ndef find_duplicate(nums):\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] == nums[j]:\n                return nums[i]\n    return None\n```",
        "expect_action": "MODIFY",
    },
    {
        "id": "RF-02",
        "category": "refactor",
        "prompt": "Convert this synchronous function to async/await:\n```python\nimport requests\ndef fetch_user_data(user_id):\n    response = requests.get(f'https://api.example.com/users/{user_id}')\n    return response.json()\n```",
        "expect_action": "MODIFY",
    },

    # ─── Test Writing ─────────────────────────────────────────────────────
    {
        "id": "TW-01",
        "category": "test_writing",
        "prompt": "Write pytest tests for a `Stack` class that has `push(item)`, `pop()`, `peek()`, and `is_empty()` methods. Cover normal operations and edge cases (empty stack).",
        "expect_action": "CREATE",
    },
    {
        "id": "TW-02",
        "category": "test_writing",
        "prompt": "Write 3 pytest test cases for a function `validate_email(email: str) -> bool` that returns True for valid emails and False for invalid ones.",
        "expect_action": "CREATE",
    },

    # ─── Multi-File ───────────────────────────────────────────────────────
    {
        "id": "MF-01",
        "category": "multi_file",
        "prompt": "Create a simple Flask health check endpoint. File 1: `src/app.py` with a Flask app and GET `/health` route returning {'status': 'ok'}. File 2: `tests/test_health.py` with a test for the endpoint.",
        "expect_action": "CREATE",
    },

    # ─── Format Recovery (Messy Prompts) ──────────────────────────────────
    {
        "id": "FR-01",
        "category": "format_recovery",
        "prompt": "hey can u make a func that counts vowels in a string thx",
        "expect_action": "CREATE",
    },
    {
        "id": "FR-02",
        "category": "format_recovery",
        "prompt": "URGENT fix needed: write a function to flatten nested lists like [[1,[2,3]],[4]] -> [1,2,3,4]",
        "expect_action": "CREATE",
    },
    {
        "id": "FR-03",
        "category": "format_recovery",
        "prompt": "yo nova write me some code for reversing a linked list, python pls",
        "expect_action": "CREATE",
    },

    # ─── Edge Cases ───────────────────────────────────────────────────────
    {
        "id": "EC-01",
        "category": "edge_case",
        "prompt": "Write a function that takes no arguments and returns the string 'hello world'.",
        "expect_action": "CREATE",
    },
    {
        "id": "EC-02",
        "category": "edge_case",
        "prompt": "Implement a Python function `safe_divide(a, b)` that returns a/b but handles ZeroDivisionError, TypeError, and returns None for invalid inputs.",
        "expect_action": "CREATE",
    },
    {
        "id": "EC-03",
        "category": "edge_case",
        "prompt": "Write a decorator `@timer` that measures and prints the execution time of any function it wraps.",
        "expect_action": "CREATE",
    },
    {
        "id": "EC-04",
        "category": "edge_case",
        "prompt": "Create a Python context manager `FileHandler` that safely opens a file, yields the file object, and ensures the file is closed even if an exception occurs.",
        "expect_action": "CREATE",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# Test Runner
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TestResult:
    test_id: str
    category: str
    prompt: str
    passed: bool
    format_valid: bool
    has_thinking: bool
    has_files: bool
    has_test_cmd: bool
    has_filepath: bool
    has_action: bool
    thinking_word_count: int = 0
    code_syntax_valid: bool = False
    tps: float = 0.0
    ttft_ms: float = 0.0
    total_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    raw_response: str = ""


def run_smoke_tests(
    model: str = "nova3b",
    tests: List[Dict] = None,
    verbose: bool = True,
) -> List[TestResult]:
    """Run all smoke tests against the specified model."""
    
    if tests is None:
        tests = SMOKE_TESTS
    
    client = OllamaClient()
    parser = NovaOutputParser()
    results = []
    
    if not client.is_running():
        print("❌ Ollama is not running. Start with: ollama serve")
        sys.exit(1)
    
    if not client.has_model(model):
        print(f"❌ Model '{model}' not found. Available models:")
        for m in client.list_models():
            print(f"   - {m['name']}")
        sys.exit(1)
    
    print("═" * 65)
    print(f"  🧪 AMAURA — Nova 3B Smoke Test Suite")
    print(f"  Model: {model} | Tests: {len(tests)}")
    print("═" * 65)
    
    for i, test in enumerate(tests):
        test_id = test["id"]
        category = test["category"]
        prompt = test["prompt"]
        
        if verbose:
            print(f"\n[{i+1}/{len(tests)}] {test_id} ({category})")
            print(f"  Prompt: {prompt[:60]}...")
        
        # Generate
        gen_result = client.nova_generate(prompt, model=model)
        
        # Parse
        parsed = parser.parse(gen_result.text)
        is_strict, strict_errors = parser.validate_format_strict(gen_result.text)
        
        # Syntax check
        code_valid = False
        if parsed.files:
            for f in parsed.files:
                if f.language == "python":
                    try:
                        import ast
                        ast.parse(f.content)
                        code_valid = True
                    except SyntaxError:
                        code_valid = False
                else:
                    code_valid = True  # Skip syntax check for non-Python
        
        # Check for filepath and action
        has_filepath = any("# filepath:" in gen_result.text.lower() 
                          for _ in [1])
        has_action = any("# action:" in gen_result.text.lower()
                        for _ in [1])
        
        # Build result
        tr = TestResult(
            test_id=test_id,
            category=category,
            prompt=prompt,
            passed=parsed.is_valid and code_valid,
            format_valid=parsed.is_valid,
            has_thinking=bool(parsed.thinking),
            has_files=len(parsed.files) > 0,
            has_test_cmd=bool(parsed.test_command),
            has_filepath="# filepath:" in gen_result.text.lower(),
            has_action="# action:" in gen_result.text.lower(),
            thinking_word_count=len(parsed.thinking.split()) if parsed.thinking else 0,
            code_syntax_valid=code_valid,
            tps=gen_result.metrics.tokens_per_second,
            ttft_ms=gen_result.metrics.time_to_first_token_ms,
            total_ms=gen_result.metrics.total_time_ms,
            errors=strict_errors + parsed.parse_errors,
            raw_response=gen_result.text,
        )
        
        results.append(tr)
        
        if verbose:
            status = "✅" if tr.passed else "❌"
            print(f"  {status} Format: {'✓' if tr.format_valid else '✗'} | "
                  f"Syntax: {'✓' if code_valid else '✗'} | "
                  f"TPS: {tr.tps:.1f} | {tr.total_ms:.0f}ms")
            if tr.errors:
                print(f"  Errors: {tr.errors[:3]}")
    
    return results


def print_summary(results: List[TestResult]):
    """Print a formatted summary of test results."""
    
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    format_valid = sum(1 for r in results if r.format_valid)
    syntax_valid = sum(1 for r in results if r.code_syntax_valid)
    
    avg_tps = sum(r.tps for r in results) / max(total, 1)
    avg_ttft = sum(r.ttft_ms for r in results) / max(total, 1)
    avg_thinking = sum(r.thinking_word_count for r in results) / max(total, 1)
    
    # Category breakdown
    categories = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r.passed:
            categories[cat]["passed"] += 1
    
    print("\n" + "═" * 65)
    print(f"  📊 AMAURA — Smoke Test Results")
    print("═" * 65)
    
    print(f"\n  Overall:")
    print(f"    Tests Passed:     {passed}/{total} ({passed/total*100:.0f}%)")
    print(f"    Format Valid:     {format_valid}/{total} ({format_valid/total*100:.0f}%)")
    print(f"    Syntax Valid:     {syntax_valid}/{total} ({syntax_valid/total*100:.0f}%)")
    
    print(f"\n  Performance:")
    print(f"    Avg TPS:          {avg_tps:.1f} tokens/sec")
    print(f"    Avg TTFT:         {avg_ttft:.0f}ms")
    print(f"    Avg Thinking:     {avg_thinking:.0f} words")
    
    print(f"\n  By Category:")
    for cat, stats in sorted(categories.items()):
        pct = stats['passed'] / stats['total'] * 100
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        print(f"    {cat:20s} {bar} {stats['passed']}/{stats['total']} ({pct:.0f}%)")
    
    # Failed tests detail
    failed = [r for r in results if not r.passed]
    if failed:
        print(f"\n  ❌ Failed Tests ({len(failed)}):")
        for r in failed:
            print(f"    [{r.test_id}] {r.category}: {r.errors[:2]}")
    
    print("\n" + "═" * 65)
    
    if passed / total >= 0.95:
        print(f"  ✅ EXCELLENT — Nova 3B format compliance is production-ready!")
    elif passed / total >= 0.80:
        print(f"  ⚠️  GOOD — Minor format issues. Consider more training data.")
    elif passed / total >= 0.60:
        print(f"  ⚠️  FAIR — Needs additional fine-tuning for reliability.")
    else:
        print(f"  ❌ NEEDS WORK — Format compliance too low. Re-train with more data.")
    
    print("═" * 65)


def save_report(results: List[TestResult], path: str = "smoke_test_report.json"):
    """Save detailed results to JSON."""
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": results[0].test_id if results else "unknown",
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "results": [
            {
                "id": r.test_id,
                "category": r.category,
                "passed": r.passed,
                "format_valid": r.format_valid,
                "syntax_valid": r.code_syntax_valid,
                "tps": round(r.tps, 1),
                "ttft_ms": round(r.ttft_ms, 0),
                "errors": r.errors,
            }
            for r in results
        ],
    }
    
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"\n📁 Report saved: {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Amaura — Nova 3B Smoke Test Suite",
    )
    parser.add_argument("--model", default="nova3b",
                        help="Ollama model name to test")
    parser.add_argument("--report", action="store_true",
                        help="Save detailed JSON report")
    parser.add_argument("--quiet", action="store_true",
                        help="Minimal output")
    parser.add_argument("--count", type=int, default=0,
                        help="Run only first N tests (0 = all)")
    
    args = parser.parse_args()
    
    tests = SMOKE_TESTS
    if args.count > 0:
        tests = tests[:args.count]
    
    results = run_smoke_tests(
        model=args.model,
        tests=tests,
        verbose=not args.quiet,
    )
    
    print_summary(results)
    
    if args.report:
        save_report(results)
