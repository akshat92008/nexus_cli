#!/usr/bin/env python3
"""
cli.py - Interactive Terminal Interface for jarvis-nova-1.5b
Allows users to issue coding tasks, toggle between Claude Nova 1.5b Architectural Mode
and GPT-5.6 Sol Workhorse Mode, and run self-healing test execution loops interactively.
"""

import os
import sys
import json
import argparse
import re
from router import JarvisFable5Router, ReasoningMode
from debugger import SelfHealingDebugger
from ast_indexer import ASTIndexer

NEXUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coding_agent")
if NEXUS_DIR not in sys.path:
    sys.path.insert(0, NEXUS_DIR)

def print_banner():
    print("=" * 72)
    print("  JARVIS FABLE 5 & GPT-5.6 SOL OFFLINE CODING ENGINE v2.0  ")
    print("  Capabilities: Claude Nova 1.5b Architectural CoT + Sol Self-Healing Loop")
    print("  VRAM Footprint: ~1.18 GB | Platform: Apple Silicon / Offline Local")
    print("=" * 72)
    print()

def main():
    print_banner()
    
    parser = argparse.ArgumentParser(description="JARVIS Nova 1.5b CLI")
    parser.add_argument("--mode", type=str, default="nova_architectural", choices=["nova_architectural", "sol_workhorse", "nexus_two_node", "nexus"], help="Default reasoning mode")
    parser.add_argument("--task", type=str, help="Single-shot task execution")
    parser.add_argument("--auto_repair", action="store_true", help="Run self-healing repair loop automatically")
    args = parser.parse_args()

    if args.mode in ["nexus_two_node", "nexus"]:
        mode = ReasoningMode.NEXUS_TWO_NODE
    elif args.mode == "sol_workhorse":
        mode = ReasoningMode.SOL_WORKHORSE
    else:
        mode = ReasoningMode.FABLE5_ARCHITECTURAL
    router = JarvisFable5Router()
    debugger = SelfHealingDebugger()
    indexer = ASTIndexer(".")

    if args.task:
        run_task(args.task, mode, args.auto_repair, router, debugger, indexer)
        return

    # Interactive Loop
    while True:
        try:
            print("\n------------------------------------------------------------------------")
            print(f"Current Mode: [{mode.value.upper()}]")
            print("Commands: 'switch' (cycle mode), 'switch <mode>' (nova, sol, nexus), 'index' (view AST graph), 'exit' (quit)")
            print("------------------------------------------------------------------------")
            user_input = input("nova> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting JARVIS Nova 1.5b Coding Engine. Goodbye!")
                break

            if user_input.lower().startswith("switch"):
                parts = user_input.lower().split(maxsplit=1)
                if len(parts) > 1:
                    target = parts[1].strip()
                    if target in ["nexus", "nexus_two_node"]:
                        mode = ReasoningMode.NEXUS_TWO_NODE
                    elif target in ["sol", "sol_workhorse"]:
                        mode = ReasoningMode.SOL_WORKHORSE
                    elif target in ["nova", "nova_architectural"]:
                        mode = ReasoningMode.FABLE5_ARCHITECTURAL
                    else:
                        print(f"[CLI] Unknown mode '{target}'. Available: nova, sol, nexus")
                        continue
                else:
                    if mode == ReasoningMode.FABLE5_ARCHITECTURAL:
                        mode = ReasoningMode.SOL_WORKHORSE
                    elif mode == ReasoningMode.SOL_WORKHORSE:
                        mode = ReasoningMode.NEXUS_TWO_NODE
                    else:
                        mode = ReasoningMode.FABLE5_ARCHITECTURAL
                print(f"[CLI] Switched mode to: {mode.value.upper()}")
                continue

            if user_input.lower() == "index":
                graph = indexer.build_symbol_graph()
                print(f"[AST Indexer] Found {len(graph)} indexed files:")
                print(json.dumps(graph, indent=2))
                continue

            # Run task
            run_task(user_input, mode, True, router, debugger, indexer)

        except (KeyboardInterrupt, EOFError):
            print("\nExiting JARVIS Nova 1.5b Coding Engine. Goodbye!")
            break

def run_nexus_task(prompt: str, debugger: SelfHealingDebugger):
    print("\n[Nexus Two-Node Backend] Initiating Task Orchestration (Ceiling + Intern)...")
    
    try:
        from nexus.api import NvidiaClient, _load_env_file
        from nexus.two_node_backend import TwoNodeBackend
        from nexus.models import DEFAULT_MODEL, resolve_model
    except ImportError as e:
        print(f"[Nexus CLI Error] Failed to import Nexus modules: {e}")
        return

    _load_env_file()
    api_key = os.environ.get("NVIDIA_API_KEY") or os.environ.get("GROQ_API_KEY") or "nvapi-placeholder-fallback"
    try:
        client = NvidiaClient(api_key=api_key)
    except Exception as e:
        print(f"[Nexus CLI Error] Could not initialize API client: {e}")
        return

    model_cfg = resolve_model(DEFAULT_MODEL) or {"id": "deepseek-ai/deepseek-v4-pro", "name": "DeepSeek V4 Pro"}
    
    backend = TwoNodeBackend(
        client=client,
        ceiling_model_id=model_cfg["id"],
        ceiling_model_name=model_cfg["name"],
        working_dir=os.getcwd(),
        intern_model="nova_codex",
    )
    
    try:
        result = backend.run(prompt)
    except Exception as e:
        print(f"[Nexus Orchestration Error] {e}")
        return

    print("\n" + "=" * 60)
    print(result.format_breakdown())
    print("=" * 60 + "\n")

    for idx, exec_rec in enumerate(result.executions, 1):
        print(f"\n<<< SUBTASK [{exec_rec.task.id}] CoT ANALYSIS & STATUS >>>")
        print(f"Description: {exec_rec.task.description}")
        print(f"Executed by: {exec_rec.node} | Verdict: {exec_rec.verdict} | Attempts: {exec_rec.attempts}")
        
        thinking_match = re.search(r"<<THINKING>>(.*?)<</THINKING>>", exec_rec.raw_output, re.DOTALL | re.IGNORECASE)
        if not thinking_match:
            thinking_match = re.search(r"<<THINKING>>(.*?)(?=<<FILES>>|<<TEST_COMMAND>>|<<RESPONSE>>|$)", exec_rec.raw_output, re.DOTALL | re.IGNORECASE)
        if thinking_match and thinking_match.group(1).strip():
            print("\n--- Reasoning (CoT) ---")
            print(thinking_match.group(1).strip())
        
        if exec_rec.error:
            print(f"\n[Guardrail / Execution Error]: {exec_rec.error}")
            
    if result.proposals:
        print(f"\n<<< APPLYING GENERATED NEXUS FILE PROPOSALS ({len(result.proposals)}) >>>")
        files_to_apply = []
        for prop in result.proposals:
            args = prop.args
            raw_path = args.get("path", "")
            # Resolve desktop/ relative paths to ~/Desktop if requested
            if raw_path.lower().startswith("desktop/"):
                rel_sub = raw_path.split("/", 1)[1]
                path = os.path.join(os.path.expanduser("~/Desktop"), rel_sub)
            elif "desktop" in prompt.lower() and not os.path.isabs(raw_path):
                filename = os.path.basename(raw_path)
                path = os.path.join(os.path.expanduser("~/Desktop"), filename)
            else:
                path = raw_path

            if prop.name == "write_file":
                content = args.get("content", "")
                files_to_apply.append({"path": path, "action": "write", "content": content})
                print(f"[Nexus Proposal] Write file: {path} (status: APPROVED by guardrails)")
            elif prop.name == "edit_file":
                old_text = args.get("old_text", "")
                new_text = args.get("new_text", "")
                full_path = os.path.abspath(path)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as f:
                        curr_content = f.read()
                    if old_text in curr_content:
                        new_content = curr_content.replace(old_text, new_text, 1)
                        files_to_apply.append({"path": path, "action": "edit", "content": new_content})
                        print(f"[Nexus Proposal] Edit file: {path} (status: APPROVED by guardrails)")
                    else:
                        print(f"[Nexus Proposal Error] Edit target text not found in {path}")
                else:
                    print(f"[Nexus Proposal Error] File {path} does not exist for edit_file")
        if files_to_apply:
            debugger.apply_file_changes(files_to_apply)
            print("[Nexus] All approved file changes applied to workspace successfully.")
    else:
        print("\n[Nexus] No file proposals were generated or approved.")


def run_task(prompt: str, mode: ReasoningMode, auto_repair: bool, router: JarvisFable5Router, debugger: SelfHealingDebugger, indexer: ASTIndexer):
    if mode == ReasoningMode.NEXUS_TWO_NODE:
        run_nexus_task(prompt, debugger)
        return

    print(f"\n[Nova 1.5b Engine] Processing Task in {mode.value.upper()} Mode...")
    print(f"Task Prompt: {prompt}\n")

    if auto_repair or mode == ReasoningMode.SOL_WORKHORSE:
        # Run agentic repair loop
        result = debugger.execute_repair_loop(prompt, max_iterations=3, mode=mode)
        print("\n" + "=" * 60)
        print(f"REPAIR EXECUTION STATUS: {result['status']}")
        print(f"TOTAL ITERATIONS: {result['iterations']}")
        print("=" * 60)
    else:
        # Single-shot generation
        symbol_graph = indexer.build_symbol_graph()
        response = router.generate(prompt, mode=mode, ast_context=symbol_graph)
        parsed = debugger.parse_fable_response(response["text"])

        if parsed["thinking"]:
            print("<<< THINKING (CoT Analysis) >>>")
            print(parsed["thinking"])
            print()

        if parsed["files"]:
            print(f"<<< GENERATED FILES ({len(parsed['files'])}) >>>")
            debugger.apply_file_changes(parsed["files"])
            print()

        if parsed["test_command"]:
            print(f"<<< VERIFICATION TEST COMMAND >>>")
            print(parsed["test_command"])
            success, output = debugger.run_test_command(parsed["test_command"])
            print(f"\nTest Pass: {success}")
            print(f"Output:\n{output}")

if __name__ == "__main__":
    main()
