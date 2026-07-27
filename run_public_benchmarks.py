#!/usr/bin/env python3
"""
run_public_benchmarks.py — Standalone Evaluation Suite for Nova 1.5b (nova_codex)

Executes the 4 required benchmark categories for the model-only public release:
1. MBPP Pass@1 Execution-Verified Benchmark (all 145 held-out test examples).
2. 15-Case Realistic File-Editing Suite (raw model output only, no pipeline guardrails/retry).
3. 4 Vague-Prompt Standalone Evaluation (no pre-check, must produce <<CLARIFICATION>> only).
4. Format Compliance Benchmark (20 fresh varied prompts).

Outputs raw X/Y scores and includes every single failing raw output.
"""

import json
import os
import re
import requests
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path
from datasets import load_dataset

from output_parser import NovaOutputParser
from constraint_checker import ConstraintExtractor, ConstraintVerifier
from pipeline import CeilingInternPipeline
from run_realistic_baseline import create_complex_file

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "nova_codex"

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Execution timed out")

def call_ollama(prompt: str, temperature: float = 0.2, num_predict: int = 1024, timeout: int = 60) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict
        }
    }
    try:
        res = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        if res.status_code == 200:
            return res.json().get("response", "")
        return f"<<ERROR>> HTTP {res.status_code}: {res.text}"
    except Exception as e:
        return f"<<ERROR>> Request failed: {str(e)}"

def extract_func_name(test_str: str) -> str:
    match = re.search(r"assert\s+([a-zA-Z0-9_]+)\s*\(", test_str)
    if match:
        return match.group(1)
    return "solution"

def run_mbpp_benchmark(report_lines: list):
    print("Running Category 1: MBPP Pass@1 Execution-Verified Benchmark...")
    report_lines.append("## 1. MBPP Pass@1 Execution-Verified Benchmark (Standalone)\n")
    
    dataset = load_dataset("json", data_files={"train": "dataset_nova_intern_v5.jsonl"}, split="train")
    split = dataset.train_test_split(test_size=0.15, seed=42)
    eval_dataset = split["test"]
    
    mbpp = load_dataset("mbpp")
    mbpp_all = list(mbpp['train']) + list(mbpp['validation']) + list(mbpp['test'])
    
    def get_mbpp_tests(task_id):
        for item in mbpp_all:
            if item['task_id'] == task_id:
                return item['test_list']
        return []

    total = len(eval_dataset)
    format_passes = 0
    code_passes = 0
    logic_errors = 0
    execution_errors = 0
    timeouts = 0
    failures = []

    for i, example in enumerate(eval_dataset):
        task_id = example['metadata']['task_id']
        tests = get_mbpp_tests(task_id)
        
        func_name = "solution"
        if tests:
            func_name = extract_func_name(tests[0])
            
        user_msg = ""
        for m in example.get("messages", []):
            if m["role"] == "user":
                user_msg = m["content"]
                break
                
        core_task = user_msg
        if user_msg.startswith("Task: "):
            core_task = user_msg[6:]
        if "\nPlease implement" in core_task:
            core_task = core_task.split("\nPlease implement")[0]
            
        form_b = f"Can you write some Python code for this? Name the function `{func_name}`. {core_task}"
        
        resp = call_ollama(form_b, temperature=0.1, num_predict=1024)
        
        has_thinking = "<<THINKING>>" in resp
        has_files = "<<FILES>>" in resp
        if has_thinking and has_files:
            format_passes += 1
            
        match = re.search(r"```python\n(.*?)\n```", resp, re.DOTALL)
        if match:
            code = match.group(1)
            code = "\n".join([line for line in code.split("\n") if not line.startswith("# filepath") and not line.startswith("# action")])
            
            try:
                namespace = {}
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(3)
                exec(code, namespace)
                
                tests_passed = True
                for test_str in tests:
                    try:
                        exec(test_str, namespace)
                    except AssertionError as e:
                        logic_errors += 1
                        tests_passed = False
                        failures.append((task_id, core_task, "Logic Error / Assertion Failed", resp))
                        break
                    except TimeoutException:
                        raise
                    except Exception as e:
                        execution_errors += 1
                        tests_passed = False
                        failures.append((task_id, core_task, f"Execution Error in test: {e}", resp))
                        break
                
                signal.alarm(0)
                if tests_passed:
                    code_passes += 1
            except TimeoutException:
                timeouts += 1
                signal.alarm(0)
                failures.append((task_id, core_task, "Timeout Error (3s limit exceeded)", resp))
            except Exception as e:
                execution_errors += 1
                signal.alarm(0)
                failures.append((task_id, core_task, f"Syntax/Execution Error in code: {e}", resp))
        else:
            failures.append((task_id, core_task, "Format Error: No ```python code block found in response", resp))

        if (i + 1) % 25 == 0 or (i + 1) == total:
            print(f"  MBPP Progress: {i+1}/{total} | Passes: {code_passes}")

    pass_rate = (code_passes / total) * 100 if total > 0 else 0
    format_rate = (format_passes / total) * 100 if total > 0 else 0

    report_lines.append(f"- **Total Examples:** {total}")
    report_lines.append(f"- **Pass@1 Execution-Verified Score:** **{code_passes}/{total} ({pass_rate:.1f}%)**")
    report_lines.append(f"- **Format Compliance Score (THINKING + FILES tags):** {format_passes}/{total} ({format_rate:.1f}%)")
    report_lines.append(f"- **Logic Errors (Assertion Failed):** {logic_errors}")
    report_lines.append(f"- **Execution / Syntax Errors:** {execution_errors}")
    report_lines.append(f"- **Timeouts (3s limit):** {timeouts}\n")

    report_lines.append("### Raw Failing Outputs (MBPP Standalone)\n")
    if not failures:
        report_lines.append("No failures recorded.\n")
    else:
        for fid, fprompt, ftype, fresp in failures:
            report_lines.append(f"#### Task ID: `{fid}` | Failure Type: {ftype}")
            report_lines.append(f"**Task:** {fprompt}\n")
            report_lines.append("**Raw Model Output:**")
            report_lines.append("```text")
            report_lines.append(fresp.strip())
            report_lines.append("```\n")

def run_realistic_15_benchmark(report_lines: list):
    print("Running Category 2: 15-Case Realistic File-Editing Suite (Standalone)...")
    report_lines.append("## 2. 15-Case Realistic File-Editing Suite (Standalone / Raw Model Output Only)\n")
    report_lines.append("Evaluated without pipeline guardrails, pre-checks, or retry prompts. The raw model output is tested directly against disk application and constraint verification.\n")

    cases = [
        {"name": "Case 5 — profile picture", "prompt": "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing.", "file": "src/auth.py", "lang": "python", "line": 40, "target": "    # This endpoint crashes if the user has no profile picture\n    profile_pic_url = current_user.profile_pic_url"},
        {"name": "Case 6 — healthcheck", "prompt": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails.", "file": "src/app.js", "lang": "js", "line": 85, "target": "app.get('/healthcheck', (req, res) => {\n    const connection = db.getConnection();\n    res.status(200).json({ status: 'healthy' });\n});"},
        {"name": "Fresh Case 1 — retry default", "prompt": "URGENT: the retry logic is looping infinitely. in src/utils.py around line 75, if max_retries is not provided, set it to 3 instead of 5.", "file": "src/utils.py", "lang": "python", "line": 75, "target": "def execute_with_retry(task, max_retries=None):\n    if max_retries is None:\n        max_retries = 5 # BUG: too high"},
        {"name": "Fresh Case 2 — payment", "prompt": "URGENT: payment endpoint is returning wrong code. in src/routes/api.js at line 90, change the failure response to return 402 with status: 'Payment Required'.", "file": "src/routes/api.js", "lang": "js", "line": 90, "target": "router.post('/payment', (req, res) => {\n    if (!req.body.token) {\n        return res.status(200).json({ error: 'failed' });\n    }\n});"},
        {"name": "Fresh Case 3 — worker timeout", "prompt": "URGENT: logging monitor is missing timeouts. in src/worker.py line 50, change the exception print output to exactly 'Worker Timeout'.", "file": "src/worker.py", "lang": "python", "line": 50, "target": "def process_job(job_id):\n    try:\n        do_work(job_id)\n    except TimeoutError:\n        print('Failed')\n"}
    ]

    parser = NovaOutputParser()
    ceiling = CeilingInternPipeline(ceiling_provider="mock", intern_model="nova_codex", workspace_dir=".", run_tests=False)
    extractor = ConstraintExtractor(ceiling)
    verifier = ConstraintVerifier(ceiling)

    passed_count = 0
    total_runs = 15
    results_table = []
    failures = []

    for case_idx, case in enumerate(cases):
        for run_idx in range(1, 4):
            workspace = tempfile.mkdtemp(prefix="standalone_real_")
            try:
                target_path = os.path.join(workspace, *case["file"].split("/"))
                create_complex_file(target_path, 150, case["line"], case["target"], case["lang"])
                
                resp = call_ollama(case["prompt"], temperature=0.2, num_predict=1024)
                parsed = parser.parse(resp)
                
                category = "Unknown"
                status = "fail"
                
                if not parsed.is_valid:
                    if "```" in resp or "```python" in resp:
                        category = "Double-Wrap"
                    else:
                        category = "Format-Error"
                elif len(parsed.files) == 0:
                    category = "No-File-Output"
                else:
                    f = parsed.files[0]
                    if "dummy_func" in resp or "dummyFunc" in resp:
                        category = "Top-Grab"
                    else:
                        # Test patch application on disk without guardrails
                        test_pipe = CeilingInternPipeline(ceiling_provider="mock", intern_model="nova_codex", workspace_dir=workspace, run_tests=False)
                        try:
                            test_pipe.test_executor.write_files(parsed.files)
                            constraints = extractor.extract(case["prompt"])
                            verified_pass, reason = verifier.verify(constraints, parsed.files)
                            if verified_pass:
                                category = "Success"
                                status = "pass"
                                passed_count += 1
                            else:
                                category = "Failed-Relevance"
                        except Exception as e:
                            category = f"Patch-Apply-Failed ({str(e)[:40]})"

                results_table.append((case["name"], run_idx, status, category))
                if status != "pass":
                    failures.append((case["name"], run_idx, category, resp))
                print(f"  Realistic Suite | {case['name']} (Run {run_idx}/3) -> {status.upper()} ({category})")
            finally:
                shutil.rmtree(workspace, ignore_errors=True)

    pass_rate = (passed_count / total_runs) * 100
    report_lines.append(f"- **Total Runs:** {total_runs}")
    report_lines.append(f"- **Standalone First-Attempt Pass Rate:** **{passed_count}/{total_runs} ({pass_rate:.1f}%)**\n")
    report_lines.append("| Case | Run | Raw Status | Failure Category |")
    report_lines.append("|---|---:|---|---|")
    for cname, run_num, st, cat in results_table:
        report_lines.append(f"| {cname} | {run_num} | `{st}` | {cat} |")
    report_lines.append("")

    report_lines.append("### Raw Failing Outputs (Realistic 15-Case Suite Standalone)\n")
    if not failures:
        report_lines.append("No failures recorded.\n")
    else:
        for cname, rnum, cat, fresp in failures:
            report_lines.append(f"#### Case: `{cname}` (Run {rnum}) | Category: {cat}")
            report_lines.append("**Raw Model Output:**")
            report_lines.append("```text")
            report_lines.append(fresp.strip())
            report_lines.append("```\n")

def run_vague_prompts_benchmark(report_lines: list):
    print("Running Category 3: Vague-Prompt Standalone Evaluation...")
    report_lines.append("## 3. Vague-Prompt Standalone Evaluation (No Pre-Check)\n")
    report_lines.append("Evaluates whether the model correctly outputs <<CLARIFICATION>> without generating code (no <<FILES>>) when given underspecified architectural prompts.\n")

    prompts = [
        ("B1_vague_chat", "Build a scalable, cloud-native microservice architecture for a real-time chat application."),
        ("B2_vague_db", "How should I structure my database for a global social network?"),
        ("B3_vague_ml", "Design a machine learning pipeline that can predict customer churn with 99% accuracy."),
        ("B4_vague_blockchain", "Create a secure, decentralized authentication system using blockchain.")
    ]

    passed_count = 0
    total = len(prompts)
    results_table = []
    failures = []

    for pid, prompt in prompts:
        resp = call_ollama(prompt, temperature=0.2, num_predict=1024)
        has_clar = "<<CLARIFICATION>>" in resp
        has_files = "<<FILES>>" in resp
        
        status = "fail"
        reason = ""
        if has_clar and not has_files:
            status = "pass"
            reason = "Correct clarification (no <<FILES>>)"
            passed_count += 1
        elif has_clar and has_files:
            reason = "FORMAT BUG — <<CLARIFICATION>> present but <<FILES>> also appears"
        elif has_files and not has_clar:
            reason = "FALSE EXECUTION — model generated code instead of asking for clarification"
        else:
            reason = "No <<CLARIFICATION>> tag found"
            
        results_table.append((pid, prompt, status, reason))
        if status != "pass":
            failures.append((pid, prompt, reason, resp))
        print(f"  Vague Prompts | {pid} -> {status.upper()} ({reason})")

    pass_rate = (passed_count / total) * 100
    report_lines.append(f"- **Total Prompts:** {total}")
    report_lines.append(f"- **Correct Clarification Score:** **{passed_count}/{total} ({pass_rate:.1f}%)**\n")
    report_lines.append("| ID | Prompt | Status | Outcome / Reason |")
    report_lines.append("|---|---|---:|---|")
    for pid, ptext, st, rsn in results_table:
        report_lines.append(f"| `{pid}` | {ptext} | `{st}` | {rsn} |")
    report_lines.append("")

    report_lines.append("### Raw Failing Outputs (Vague Prompts Standalone)\n")
    if not failures:
        report_lines.append("No failures recorded.\n")
    else:
        for pid, ptext, rsn, fresp in failures:
            report_lines.append(f"#### Prompt ID: `{pid}` | Reason: {rsn}")
            report_lines.append(f"**Prompt:** {ptext}\n")
            report_lines.append("**Raw Model Output:**")
            report_lines.append("```text")
            report_lines.append(fresp.strip())
            report_lines.append("```\n")

def run_format_compliance_benchmark(report_lines: list):
    print("Running Category 4: Format Compliance Benchmark (20 Fresh Varied Prompts)...")
    report_lines.append("## 4. Format Compliance Benchmark (20 Fresh Varied Prompts / Standalone)\n")
    report_lines.append("Measures how often the standalone model strictly follows the <<THINKING>> / <<FILES>> / <<TEST_COMMAND>> structure with correct filepath/action headers without any orchestrator correction.\n")

    prompts = [
        # 10 from format_compliance
        "Create a simple React component for a to-do list.",
        "Write a python script that parses a CSV file and prints the 3rd column.",
        "How do I reverse a string in C++?",
        "Write a basic HTML layout with a CSS grid.",
        "I need a bash script to backup a directory to a tar.gz file.",
        "Provide a Rust function to calculate the factorial of a number.",
        "Show me how to make a GET request in Go.",
        "Implement a binary search in Java.",
        "Write a Ruby script to rename all .txt files to .md in a folder.",
        "Give me a PHP script that connects to a MySQL database.",
        # 5 from in_distribution
        "Write a Python script that calculates the fibonacci sequence up to N. Save it to fib.py",
        "Write a JavaScript function to filter even numbers from an array. Save it to filter.js",
        "Write a Go program that prints 'Hello World'. Save it to main.go",
        "Write a Python script to reverse a list. Save it to rev.py",
        "Write a JS script to fetch a URL and print its content. Save it to fetch.js",
        # 5 from messy_phrasing
        "plz fix teh bug in login.py it crashes when no username",
        "halp i need a scrip to delete all pdfs in curr folder ASAP",
        "make index.js use arrow funcs everywhere rn",
        "bro just give me a python snippet to read json file config.json",
        "need 2 replace all spaces with dashes in filenames bash script quick"
    ]

    parser = NovaOutputParser()
    passed_count = 0
    total = len(prompts)
    results_table = []
    failures = []

    for idx, prompt in enumerate(prompts):
        resp = call_ollama(prompt, temperature=0.2, num_predict=1024)
        parsed = parser.parse(resp)
        
        status = "pass" if parsed.is_valid else "fail"
        errors_str = "None"
        if not parsed.is_valid:
            errors_str = "; ".join(parsed.parse_errors) if parsed.parse_errors else "Missing required blocks or headers"
            failures.append((idx + 1, prompt, errors_str, resp))
        else:
            passed_count += 1
            
        results_table.append((idx + 1, prompt[:45] + ("..." if len(prompt) > 45 else ""), status, errors_str))
        print(f"  Format Compliance | Prompt {idx+1}/20 -> {status.upper()}")

    pass_rate = (passed_count / total) * 100
    report_lines.append(f"- **Total Prompts:** {total}")
    report_lines.append(f"- **Format Compliance Score:** **{passed_count}/{total} ({pass_rate:.1f}%)**\n")
    report_lines.append("| # | Prompt | Status | Parse Errors / Notes |")
    report_lines.append("|---:|---|---:|---|")
    for num, ptext, st, errs in results_table:
        report_lines.append(f"| {num} | {ptext} | `{st}` | {errs} |")
    report_lines.append("")

    report_lines.append("### Raw Failing Outputs (Format Compliance Standalone)\n")
    if not failures:
        report_lines.append("No failures recorded.\n")
    else:
        for num, ptext, errs, fresp in failures:
            report_lines.append(f"#### Prompt #{num} | Errors: {errs}")
            report_lines.append(f"**Prompt:** {ptext}\n")
            report_lines.append("**Raw Model Output:**")
            report_lines.append("```text")
            report_lines.append(fresp.strip())
            report_lines.append("```\n")

def main():
    print("=" * 60)
    print("STARTING STANDALONE BENCHMARK SUITE FOR NOVA 1.5B")
    print("=" * 60)
    
    report_lines = [
        "# Standardized Standalone Benchmark Suite for Nova 1.5b (`nova_codex`)",
        "",
        "All evaluations run against standalone Ollama deployment `nova_codex` (Qwen2.5-Coder-3B Q4_K_M base + v11 positively-worded Modelfile system prompt). No orchestrator corrections, guardrails, pre-checks, or retry loops were active.",
        "",
        "---",
        ""
    ]
    
    start_time = time.time()
    
    run_mbpp_benchmark(report_lines)
    report_lines.append("---\n")
    
    run_realistic_15_benchmark(report_lines)
    report_lines.append("---\n")
    
    run_vague_prompts_benchmark(report_lines)
    report_lines.append("---\n")
    
    run_format_compliance_benchmark(report_lines)
    
    elapsed = time.time() - start_time
    print(f"\nBenchmark suite completed in {elapsed:.1f} seconds.")
    
    full_report = "\n".join(report_lines)
    
    with open("public_benchmarks_report.md", "w") as f:
        f.write(full_report)
    with open("public_benchmarks_report.txt", "w") as f:
        f.write(full_report)
        
    print("\nReport saved to public_benchmarks_report.md and public_benchmarks_report.txt")
    print("Done!")

if __name__ == "__main__":
    main()
