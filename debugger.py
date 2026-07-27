#!/usr/bin/env python3
"""
debugger.py - Persistent Self-Healing Debugger for jarvis-nova-1.5b
Executes test verification commands, parses error tracebacks, injects AST symbol context,
and performs GPT-5.6 Sol style execution-guided trial repair loops up to 5 iterations.
"""

import os
import sys
import re
import json
import subprocess
from router import JarvisFable5Router, ReasoningMode
from ast_indexer import ASTIndexer

class SelfHealingDebugger:
    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.router = JarvisFable5Router()
        self.indexer = ASTIndexer(self.workspace_dir)

    def parse_fable_response(self, response_text: str) -> dict:
        files = []
        test_command = ""
        thinking = ""

        thinking_match = re.search(r"<<THINKING>>(.*?)<</THINKING>>", response_text, re.DOTALL)
        if thinking_match:
            thinking = thinking_match.group(1).strip()

        files_match = re.search(r"<<FILES>>(.*?)<</FILES>>", response_text, re.DOTALL)
        if files_match:
            try:
                files = json.loads(files_match.group(1).strip())
            except Exception as e:
                print(f"[Debugger Warning] Failed to parse <<FILES>> JSON: {e}")

        test_match = re.search(r"<<TEST_COMMAND>>(.*?)<</TEST_COMMAND>>", response_text, re.DOTALL)
        if test_match:
            test_command = test_match.group(1).strip()

        return {
            "thinking": thinking,
            "files": files,
            "test_command": test_command
        }

    def apply_file_changes(self, files: list):
        for f in files:
            file_path = os.path.join(self.workspace_dir, f["path"])
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            if f.get("action") in ["write", "edit"]:
                print(f"[Debugger] Writing target file: {f['path']}")
                with open(file_path, "w", encoding="utf-8") as out:
                    out.write(f["content"])

    def run_test_command(self, test_command: str) -> tuple:
        if not test_command:
            return True, "No test command provided."

        print(f"[Debugger] Running verification test command: {test_command}")
        try:
            res = subprocess.run(
                test_command,
                shell=True,
                cwd=self.workspace_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            success = res.returncode == 0
            return success, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Test execution timed out after 30 seconds."
        except Exception as e:
            return False, str(e)

    def execute_repair_loop(self, prompt: str, max_iterations: int = 5, mode: ReasoningMode = ReasoningMode.SOL_WORKHORSE) -> dict:
        print(f"[Debugger] Initiating GPT-5.6 Sol / Nova 1.5b repair loop for task: {prompt}")
        current_prompt = prompt
        history = []

        for iteration in range(1, max_iterations + 1):
            print(f"\n--- [Debugger Iteration {iteration}/{max_iterations}] ---")
            
            # Step 1: Extract AST Symbol Graph
            symbol_graph = self.indexer.build_symbol_graph()

            # Step 2: Query local model router
            res = self.router.generate(current_prompt, mode=mode, ast_context=symbol_graph if iteration > 1 else None)
            parsed = self.parse_fable_response(res["text"])
            
            # Step 3: Apply target file changes
            if parsed["files"]:
                self.apply_file_changes(parsed["files"])

            # Step 4: Run verification test command
            test_cmd = parsed["test_command"]
            success, output = self.run_test_command(test_cmd)

            history.append({
                "iteration": iteration,
                "thinking": parsed["thinking"],
                "files_count": len(parsed["files"]),
                "test_command": test_cmd,
                "success": success,
                "output": output
            })

            if success:
                print(f"[Debugger SUCCESS] Verification tests passed on iteration {iteration}!")
                return {
                    "status": "PASSED",
                    "iterations": iteration,
                    "history": history
                }

            print(f"[Debugger FAILURE] Test failed on iteration {iteration}. Backpropagating error traceback...")

            # Build self-correction prompt for next trial
            current_prompt = (
                f"Original Task: {prompt}\n\n"
                f"Attempt #{iteration} Failed with Test Output:\n{output}\n\n"
                f"Indexed AST Symbol Graph:\n{json.dumps(symbol_graph, indent=2)}\n\n"
                f"Fix the bug. Output corrected <<THINKING>>, <<FILES>>, and <<TEST_COMMAND>> blocks."
            )

        print("[Debugger FAILED] Max iterations reached without 100% test pass.")
        return {
            "status": "FAILED",
            "iterations": max_iterations,
            "history": history
        }

if __name__ == "__main__":
    debugger = SelfHealingDebugger()
    result = debugger.execute_repair_loop("Implement a thread-safe LRU Cache in Python with TTL expiration support.")
    print(json.dumps(result, indent=2))
