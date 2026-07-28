#!/usr/bin/env python3
"""
multi_agent.py — Hierarchical Multi-Agent Orchestration for Nova 1.5b

Splits the monolithic ReAct loop into specialized sub-agents:
  1. Architect (Planner) - Analyzes the prompt and repository, writes a step-by-step master plan.
  2. Coder (Executor) - Takes the plan and implements the code, leveraging TTC (Test-Time Compute).
  3. Reviewer (Auditor) - Analyzes the Coder's output for bugs, security flaws, and performance.

This design mirrors the internal orchestration of Kimi K3 and Claude Fable 5.
"""

import json
from typing import List, Dict, Any, Optional

from ttc_inference import MCTSCodeGenerator
from agents import ReActAgent, AgentState

class ArchitectAgent:
    """Creates a structured execution plan."""
    def __init__(self, model_generate_fn):
        self.generate_fn = model_generate_fn
        self.system_prompt = (
            "You are the Nova Architect. Your job is to analyze the user's request and write "
            "a highly detailed, step-by-step implementation plan. Do not write code. "
            "Output your plan as a numbered list of tasks."
        )

    def plan(self, user_request: str) -> str:
        print("\n[Architect] Analyzing request and creating master plan...")
        history = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Create a master plan for the following request:\n{user_request}"}
        ]
        return self.generate_fn(history)


class ReviewerAgent:
    """Critiques generated code for flaws and security issues."""
    def __init__(self, model_generate_fn):
        self.generate_fn = model_generate_fn
        self.system_prompt = (
            "You are the Nova Reviewer. Analyze the provided code for security vulnerabilities, "
            "memory leaks, off-by-one errors, and architectural flaws. "
            "If the code is perfect, reply with 'APPROVED'. "
            "If there are issues, reply with 'REJECTED' followed by a detailed list of required fixes."
        )

    def review(self, original_plan: str, code: str) -> Tuple[bool, str]:
        print("\n[Reviewer] Auditing code...")
        history = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Plan:\n{original_plan}\n\nCode to review:\n{code}"}
        ]
        response = self.generate_fn(history)
        
        if "APPROVED" in response.upper():
            return True, response
        return False, response


class MultiAgentOrchestrator:
    """Coordinates the Architect, Coder, and Reviewer."""
    
    def __init__(self, model_generate_fn):
        self.model_generate_fn = model_generate_fn
        self.architect = ArchitectAgent(model_generate_fn)
        # Coder is represented by the TTC MCTS Engine for robust generation
        # We wrap the model_generate_fn for TTC which expects a single string prompt
        self.coder = MCTSCodeGenerator(
            model_generate_fn=lambda p: model_generate_fn([{"role": "user", "content": p}]),
            sandbox_timeout=10, 
            max_depth=3, 
            num_rollouts=3
        )
        self.reviewer = ReviewerAgent(model_generate_fn)

    def solve(self, user_request: str, test_code: str = "") -> str:
        """Execute the multi-agent workflow."""
        print("====================================================")
        print(" NOVA MULTI-AGENT ORCHESTRATION")
        print("====================================================")
        
        # 1. Plan
        plan = self.architect.plan(user_request)
        print(f"\n--- Architect Plan ---\n{plan}\n----------------------")
        
        max_revisions = 3
        current_attempt = 1
        
        while current_attempt <= max_revisions:
            print(f"\n[Orchestrator] Coder Attempt {current_attempt}/{max_revisions}")
            
            # 2. Code (via Test-Time Compute)
            prompt = f"Implement the following plan:\n\n{plan}\n\nOriginal Request: {user_request}"
            best_node = self.coder.run(initial_prompt=prompt, test_code=test_code)
            
            if not best_node or not best_node.code:
                return "Error: Coder failed to generate any code."
                
            code = best_node.code
            
            # 3. Review
            approved, feedback = self.reviewer.review(plan, code)
            print(f"\n--- Reviewer Feedback ---\n{feedback}\n-------------------------")
            
            if approved:
                print("\n[Orchestrator] Solution approved by Reviewer!")
                return code
                
            # Update plan with feedback for next attempt
            plan += f"\n\nCRITICAL FIXES REQUIRED (Attempt {current_attempt}):\n{feedback}"
            current_attempt += 1

        print("\n[Orchestrator] Max revisions reached. Returning latest code.")
        return code


# ============================================================================
# Dummy model generation for testing the Orchestrator standalone
# ============================================================================
def _dummy_multi_agent_fn(history: List[Dict[str, str]]) -> str:
    sys_msg = history[0]['content'] if history else ""
    user_msg = history[-1]['content']
    
    if "Nova Architect" in sys_msg:
        return "1. Create function add(a, b).\n2. Return a + b."
    elif "Nova Reviewer" in sys_msg:
        if "REJECTED" in user_msg:
            return "APPROVED. Code is now correct."
        return "REJECTED. You forgot to add type hints."
    else:
        # Coder response
        if "type hints" in user_msg:
            return "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"
        return "```python\ndef add(a, b):\n    return a + b\n```"

def _self_test():
    print("Testing Multi-Agent Orchestrator...")
    orchestrator = MultiAgentOrchestrator(model_generate_fn=_dummy_multi_agent_fn)
    final_code = orchestrator.solve("Write a function to add two numbers.")
    print("\n[Final Approved Code]")
    print(final_code)

if __name__ == "__main__":
    from typing import Tuple
    _self_test()
