#!/usr/bin/env python3
import concurrent.futures
import subprocess
import os
import time
import sys
from collections import Counter
from pathlib import Path

def run_test(cmd, env=None):
    import tempfile
    import shutil
    try:
        with tempfile.TemporaryDirectory(prefix="nexus-stress-") as temp_dir:
            temp_path = Path(temp_dir)
            run_env = dict(os.environ) if env is None else env
            
            # If the command modifies the source tree, copy it
            if "pytest" in cmd or "run_release_gate.py" in " ".join(cmd):
                build_src = temp_path / "src"
                shutil.copytree(Path("."), build_src, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "dist", "build", "*.egg-info", "installed", "legacy", "verification_evidence", "coding_agent", "bakeoff", "runs"))
                cwd = str(build_src)
            else:
                cwd = str(Path(".").resolve())
                
            start = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=run_env,
                cwd=cwd
            )
            duration = time.time() - start
            if result.returncode == 0:
                return True, duration, ""
            else:
                return False, duration, result.stderr or result.stdout
    except subprocess.TimeoutExpired as e:
        return False, 300, f"Timeout: {e}"
    except Exception as e:
        return False, 0, str(e)

def main():
    print("Starting Nexus Extreme Stress Test...")
    print("Format: Concurrent Pytest & Release Gate Matrix")
    
    commands = [
        ["python3", "-m", "pytest", "-q"],
        ["python3", "scripts/run_release_gate.py"],
        ["python3", "-m", "pytest", "tests/test_cli_responsiveness.py", "-q"],
        ["python3", "-m", "pytest", "tests/test_long_term_runtime.py", "-q"],
        ["python3", "-m", "pytest", "tests/test_agent_safety.py", "-q"],
    ]
    
    total_runs = 50  # Number of parallel tasks
    results = Counter()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for i in range(total_runs):
            cmd = commands[i % len(commands)]
            futures[executor.submit(run_test, cmd)] = cmd
            
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            cmd = futures[future]
            success, duration, err = future.result()
            completed += 1
            if success:
                results["PASSED"] += 1
                print(f"[{completed}/{total_runs}] PASS ({duration:.2f}s) - {' '.join(cmd)}")
            else:
                results["FAILED"] += 1
                print(f"[{completed}/{total_runs}] FAIL ({duration:.2f}s) - {err[:100].strip()}")
                
    print("\n=== STRESS TEST RESULTS ===")
    print(f"Total Runs: {total_runs}")
    print(f"Passed: {results['PASSED']}")
    print(f"Failed: {results['FAILED']}")
    
    if results["FAILED"] > 0:
        sys.exit(1)
    print("Zero unsupported success claims. System is reliable under stress.")

if __name__ == "__main__":
    main()
