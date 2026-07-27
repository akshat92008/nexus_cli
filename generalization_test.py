#!/usr/bin/env python3
"""
generalization_test.py — 5 brand-new prompts to test generalization after retraining.

These prompts are NOT in any training data, regression suite, or prior evaluation.
They test whether the model genuinely learned the decision boundary (missing info → refuse,
file path present → execute) rather than memorizing specific prompts.

Mix:
  1. Messy Rust prompt with typo-laden file path (expect: execute)
  2. Multi-file Go project with JIRA prefix, 3 files (expect: execute, 3+ files)
  3. Genuinely vague ML pipeline (expect: clarify)
  4. TypeScript single-file with slang (expect: execute)
  5. Multi-language Python + YAML + Dockerfile (expect: execute, 3+ files)
"""

import urllib.request
import json
import re
import sys
import time

MODEL_NAME = "nova3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

GENERALIZATION_PROMPTS = {
    "G1_messy_rust": {
        "prompt": "yo nova theres a panic in src/parser.rs when the input is empty. add a guard at the top of parse_input() that returns an empty Vec if input.is_empty(). dont touch anythign else plz",
        "expect": "execute",
        "description": "Messy Rust prompt with typos + specific file path → must execute",
    },
    "G2_multifile_go_jira": {
        "prompt": "JIRA-7721: implement a simple HTTP server in Go. Need 3 files: cmd/server/main.go (starts the server on :8080), internal/handlers/health.go (GET /health returns 200 OK), and internal/handlers/echo.go (POST /echo returns the request body). Keep it stdlib only.",
        "expect": "multifile_3",
        "description": "Multi-file Go project with JIRA prefix → must produce 3+ files",
    },
    "G3_vague_data": {
        "prompt": "We need to process terabytes of sensor data from IoT devices and derive actionable insights for predictive maintenance.",
        "expect": "clarify",
        "description": "Genuinely vague IoT/data prompt → must clarify",
    },
    "G4_slang_typescript": {
        "prompt": "bruh just make a debounce util in src/utils/debounce.ts. generic type, takes a fn and delay in ms, returns the debounced version. standard stuff",
        "expect": "execute",
        "description": "TypeScript prompt with slang + specific file → must execute",
    },
    "G5_multilang_project": {
        "prompt": "Set up a Python FastAPI project with these 3 files: app/main.py (FastAPI app with a GET / endpoint), config.yaml (host: 0.0.0.0, port: 8000, debug: true), and Dockerfile (python:3.11-slim, install requirements, run uvicorn).",
        "expect": "multifile_3",
        "description": "Multi-language project (Python + YAML + Dockerfile) → must produce 3+ files",
    },
}


def query_model(prompt: str, timeout: int = 120) -> dict:
    """Send prompt to Ollama and return parsed result."""
    req_data = json.dumps({
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 4096}
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=req_data,
        headers={"Content-Type": "application/json"}
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            duration = time.time() - start
            return {"response": result["response"], "duration": duration, "error": None}
    except Exception as e:
        return {"response": "", "duration": time.time() - start, "error": str(e)}


def check_result(test_id: str, expect: str, response: str) -> dict:
    """Evaluate whether a response meets the expected behavior."""
    has_clarification = "<<CLARIFICATION>>" in response
    has_files = "<<FILES>>" in response
    has_thinking = "<<THINKING>>" in response
    file_declarations = re.findall(r'# filepath:|// filepath:', response)
    file_count = len(file_declarations)
    format_bug = has_clarification and has_files

    result = {
        "test_id": test_id,
        "passed": False,
        "reason": "",
        "has_thinking": has_thinking,
        "has_clarification": has_clarification,
        "has_files": has_files,
        "file_count": file_count,
        "format_bug": format_bug,
    }

    if expect == "execute":
        if has_files and file_count >= 1 and not has_clarification:
            result["passed"] = True
            result["reason"] = f"✅ Correct execution ({file_count} file(s))"
        elif has_clarification:
            result["passed"] = False
            result["reason"] = "❌ FALSE REFUSAL"
        else:
            result["passed"] = False
            result["reason"] = f"❌ Missing <<FILES>> (clar={has_clarification}, files={has_files})"

    elif expect == "clarify":
        if has_clarification and not has_files:
            result["passed"] = True
            result["reason"] = "✅ Correct clarification (no <<FILES>>)"
        elif has_clarification and has_files:
            result["passed"] = False
            result["reason"] = "❌ FORMAT BUG — both tags present"
        elif has_files:
            result["passed"] = False
            result["reason"] = "❌ FALSE EXECUTION — should have clarified"
        else:
            result["passed"] = False
            result["reason"] = "❌ No <<CLARIFICATION>> found"

    elif expect.startswith("multifile_"):
        min_files = int(expect.split("_")[1])
        if has_files and file_count >= min_files and not has_clarification:
            result["passed"] = True
            result["reason"] = f"✅ Correct multi-file ({file_count} files, needed {min_files}+)"
        elif has_clarification:
            result["passed"] = False
            result["reason"] = "❌ FALSE REFUSAL on multi-file prompt"
        elif file_count < min_files:
            result["passed"] = False
            result["reason"] = f"❌ Expected {min_files}+ files, got {file_count}"
        else:
            result["passed"] = False
            result["reason"] = f"❌ Unexpected"

    return result


def run_generalization():
    """Run the 5-prompt generalization test."""
    print("=" * 70)
    print("  NOVA 3B — GENERALIZATION TEST (5 brand-new prompts)")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = []
    failures = []
    raw_outputs = {}

    for test_id, test in GENERALIZATION_PROMPTS.items():
        print(f"\n--- {test_id}: {test['description']} ---")
        print(f"  Prompt: {test['prompt'][:80]}...")
        print(f"  Expect: {test['expect']}")

        resp = query_model(test["prompt"])

        if resp["error"]:
            print(f"  ❌ REQUEST FAILED: {resp['error']}")
            results.append({"test_id": test_id, "passed": False, "reason": f"Request failed: {resp['error']}"})
            failures.append(test_id)
            continue

        result = check_result(test_id, test["expect"], resp["response"])
        result["duration"] = resp["duration"]
        results.append(result)
        raw_outputs[test_id] = resp["response"]

        print(f"  {result['reason']}")
        print(f"  Duration: {resp['duration']:.1f}s")

        if not result["passed"]:
            failures.append(test_id)

    # Summary
    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    print("\n" + "=" * 70)
    print(f"  GENERALIZATION RESULTS: {passed}/{total}")
    print("=" * 70)

    # ALWAYS print raw outputs for this test (per user request)
    print(f"\n📋 RAW OUTPUTS:")
    for test_id in GENERALIZATION_PROMPTS:
        status = "✅" if any(r["test_id"] == test_id and r["passed"] for r in results) else "❌"
        print(f"\n{'='*30} {status} {test_id} {'='*30}")
        if test_id in raw_outputs:
            output = raw_outputs[test_id]
            # Print full output for failures, truncated for passes
            if test_id in failures:
                print(output)
            else:
                print(output[:500])
                if len(output) > 500:
                    print(f"  ... ({len(output)} chars total)")
        else:
            print("  (no output — request failed)")

    if failures:
        print(f"\n🛑 {len(failures)} generalization test(s) FAILED.")
        print("   Review raw outputs above before proceeding.")
    else:
        print(f"\n✅ ALL {total} generalization tests PASSED.")

    return passed == total


if __name__ == "__main__":
    success = run_generalization()
    sys.exit(0 if success else 1)
