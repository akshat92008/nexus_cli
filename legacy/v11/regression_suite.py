#!/usr/bin/env python3
"""
regression_suite.py — Frozen regression test suite for Nova 3B.

This suite contains 18 LOCKED prompts that must ALL pass after every retraining.
DO NOT modify, replace, or rewrite these prompts between rounds.

Categories:
  A. In-distribution single-file (4 prompts) — must produce <<FILES>> code
  B. Vague/architectural (4 prompts) — must produce <<CLARIFICATION>> only
  C. Messy-but-legitimate proven (4 prompts) — must produce <<FILES>> code
  D. Messy-but-legitimate new (5 prompts) — must produce <<FILES>> code
  E. CSS 4-file split (1 prompt) — must produce 4 files in <<FILES>> block
  F. Path Fidelity (1 prompt) — must output to explicitly named file path

Pass criteria: 19/19
"""

import urllib.request
import json
import re
import sys
import time

MODEL_NAME = "nova3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

# =============================================================================
# FROZEN PROMPTS — DO NOT CHANGE BETWEEN ROUNDS
# =============================================================================

REGRESSION_SUITE = {
    # --- A. In-distribution single-file (must produce <<FILES>> code) ---
    "A1_indist_metrics": {
        "prompt": "Write a Python script `src/metrics.py` that parses a CSV file and calculates the 95th percentile of the 'latency' column.",
        "expect": "execute",
    },
    "A2_indist_factorial": {
        "prompt": "Create a function in `utils/math.py` that calculates the factorial of a number iteratively.",
        "expect": "execute",
    },
    "A3_indist_flask": {
        "prompt": "Implement a REST endpoint in `app.py` using Flask that returns the current UTC time in ISO format.",
        "expect": "execute",
    },
    "A4_indist_bash": {
        "prompt": "Write a bash script `backup.sh` that zips the `/data` directory and moves it to `/backup`.",
        "expect": "execute",
    },

    # --- B. Vague/architectural (must produce <<CLARIFICATION>> ONLY, no <<FILES>>) ---
    "B1_vague_chat": {
        "prompt": "Build a scalable, cloud-native microservice architecture for a real-time chat application.",
        "expect": "clarify",
    },
    "B2_vague_db": {
        "prompt": "How should I structure my database for a global social network?",
        "expect": "clarify",
    },
    "B3_vague_ml": {
        "prompt": "Design a machine learning pipeline that can predict customer churn with 99% accuracy.",
        "expect": "clarify",
    },
    "B4_vague_blockchain": {
        "prompt": "Create a secure, decentralized authentication system using blockchain.",
        "expect": "clarify",
    },

    # --- C. Messy-but-legitimate proven (must produce <<FILES>> code) ---
    "C1_messy_go_pinger": {
        "prompt": "yo nova make a go script that pings a database every 5 seconds. pg connection string is in env. put it in cmd/pinger/main.go. thx.",
        "expect": "execute",
    },
    "C2_messy_quicksort": {
        "prompt": "we need a fast quick sort in python. throw it in src/sort.py. dont care about edge cases just the standard algo.",
        "expect": "execute",
    },
    "C3_messy_css_btn": {
        "prompt": "the boss wants a red button on the dashboard. put a css class .red-btn with background red in styles.css.",
        "expect": "execute",
    },
    "C4_messy_dockerfile": {
        "prompt": "need a dockerfile for a node app. port 3000. index.js is the entrypoint. just give me the raw file nothing fancy.",
        "expect": "execute",
    },

    # --- D. Messy-but-legitimate new (must produce <<FILES>> code) ---
    "D1_messy_cache": {
        "prompt": "uh so the ceiling model said we need a cache. just use redis or whatever in src/cache.py and make it set/get with a ttl. dont overcomplicate it just do it fast.",
        "expect": "execute",
    },
    "D2_messy_authbug": {
        "prompt": "fix the bug where the user login fails if they dont have a profile pic. i think its in auth.py somewhere around line 40? just make it use a default empty string instead of crashing.",
        "expect": "execute",
    },
    "D3_messy_healthcheck": {
        "prompt": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails.",
        "expect": "execute",
    },
    "D4_messy_health_api": {
        "prompt": "yo just add a /health endpoint returning 200 to api.py, thx",
        "expect": "execute",
    },
    "D5_messy_react_bump": {
        "prompt": "hey can you quickly update package.json to bump react to version 18? literally just change the number.",
        "expect": "execute",
    },

    # --- E. CSS 4-file split (must produce 4 files, no <<CLARIFICATION>>) ---
    "E1_css_split": {
        "prompt": "Separate our CSS. Take `styles.css` and split it out into `components/buttons.css`, `components/cards.css`, `layout/grid.css`, and `variables.css`.",
        "expect": "multifile_4",
    },

    # --- F. Path Fidelity (must output to explicitly named file path) ---
    "F1_path_fidelity_signup": {
        "prompt": "Add input validation to the signup form in `forms/signup.py` — email must be valid, password must be at least 8 characters.",
        "expect": "execute",
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

    # Count file declarations
    file_declarations = re.findall(r'# filepath:|// filepath:', response)
    file_count = len(file_declarations)

    # Check for format mixing (both tags present)
    format_mixed = has_clarification and has_files and "(none" not in response.split("<<FILES>>")[-1][:50] if has_files else False
    # Stricter: any co-occurrence is a format bug
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
            result["reason"] = "❌ FALSE REFUSAL — model refused a legitimate prompt"
        elif not has_files:
            result["passed"] = False
            result["reason"] = "❌ No <<FILES>> tag found"
        elif format_bug:
            result["passed"] = False
            result["reason"] = "❌ FORMAT BUG — both <<CLARIFICATION>> and <<FILES>> present"
        else:
            result["passed"] = False
            result["reason"] = f"❌ Unexpected (files={has_files}, clar={has_clarification}, count={file_count})"

    elif expect == "clarify":
        if has_clarification and not has_files:
            result["passed"] = True
            result["reason"] = "✅ Correct clarification (no <<FILES>>)"
        elif has_clarification and has_files:
            result["passed"] = False
            result["reason"] = "❌ FORMAT BUG — <<CLARIFICATION>> present but <<FILES>> also appears"
        elif has_files and not has_clarification:
            result["passed"] = False
            result["reason"] = "❌ FALSE EXECUTION — model should have asked for clarification"
        else:
            result["passed"] = False
            result["reason"] = "❌ No <<CLARIFICATION>> tag found"

    elif expect == "multifile_4":
        if has_files and file_count >= 4 and not has_clarification:
            result["passed"] = True
            result["reason"] = f"✅ Correct multi-file output ({file_count} files)"
        elif has_clarification:
            result["passed"] = False
            result["reason"] = "❌ FALSE REFUSAL on multi-file prompt"
        elif file_count < 4:
            result["passed"] = False
            result["reason"] = f"❌ Expected 4 files, got {file_count}"
        elif format_bug:
            result["passed"] = False
            result["reason"] = "❌ FORMAT BUG — both tags present"
        else:
            result["passed"] = False
            result["reason"] = f"❌ Unexpected output"

    return result


def run_suite():
    """Run the full frozen regression suite."""
    print("=" * 70)
    print("  NOVA 3B — FROZEN REGRESSION SUITE")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Prompts: {len(REGRESSION_SUITE)}")
    print("=" * 70)

    results = []
    failures = []
    raw_outputs = {}

    for test_id, test in REGRESSION_SUITE.items():
        print(f"\n--- {test_id} ---")
        print(f"  Prompt: {test['prompt'][:80]}...")
        print(f"  Expect: {test['expect']}")

        resp = query_model(test["prompt"])

        if resp["error"]:
            print(f"  ❌ REQUEST FAILED: {resp['error']}")
            results.append({
                "test_id": test_id,
                "passed": False,
                "reason": f"Request failed: {resp['error']}",
            })
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
    print(f"  RESULTS: {passed}/{total}")
    print("=" * 70)

    if failures:
        print(f"\n❌ FAILURES ({len(failures)}):")
        for fid in failures:
            r = next(r for r in results if r["test_id"] == fid)
            print(f"  {fid}: {r['reason']}")

        print(f"\n⚠️  RAW OUTPUTS FOR FAILURES:")
        for fid in failures:
            if fid in raw_outputs:
                print(f"\n{'='*40} {fid} {'='*40}")
                print(raw_outputs[fid][:1000])
                if len(raw_outputs[fid]) > 1000:
                    print(f"  ... ({len(raw_outputs[fid])} chars total)")

        # STOP AND FLAG per user's instruction
        print(f"\n🛑 REGRESSION DETECTED — {len(failures)} test(s) failed.")
        print("   Do NOT proceed with further changes until failures are addressed.")
    else:
        print(f"\n✅ ALL {total} TESTS PASSED — regression suite clear.")

    return passed == total


if __name__ == "__main__":
    success = run_suite()
    sys.exit(0 if success else 1)
