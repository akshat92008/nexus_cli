#!/usr/bin/env python3
"""
ttc_inference.py — Test-Time Compute & MCTS Code Generation for Nova 1.5b

Implements Monte Carlo Tree Search (MCTS) and Tree of Thoughts for inference-time compute scaling.
Instead of returning the first generation, the model:
  1. Generates N candidate paths.
  2. Executes them in the Sandbox.
  3. Uses execution errors as feedback to self-heal and backtrack.
  4. Returns the verified best solution.
"""

import json
import time
import math
import argparse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from tool_executor import SandboxExecutor

@dataclass
class SearchNode:
    """A node in the Monte Carlo search tree representing a partial or complete code solution."""
    id: str
    prompt: str
    code: str = ""
    parent: Optional['SearchNode'] = None
    children: List['SearchNode'] = field(default_factory=list)
    visits: int = 0
    value: float = 0.0
    passed: bool = False
    error_msg: str = ""
    is_terminal: bool = False

    def ucb1(self, c_param: float = 1.41) -> float:
        """Calculate Upper Confidence Bound applied to Trees (UCT)."""
        if self.visits == 0:
            return float('inf')
        if not self.parent or self.parent.visits == 0:
            return self.value / self.visits
        
        exploitation = self.value / self.visits
        exploration = c_param * math.sqrt(math.log(self.parent.visits) / self.visits)
        return exploitation + exploration


class MCTSCodeGenerator:
    """Test-Time Compute Engine using MCTS."""
    
    def __init__(self, model_generate_fn, sandbox_timeout: int = 5, max_depth: int = 3, num_rollouts: int = 5):
        self.generate_fn = model_generate_fn
        self.sandbox = SandboxExecutor(timeout_sec=sandbox_timeout)
        self.max_depth = max_depth
        self.num_rollouts = num_rollouts
        self.node_counter = 0

    def _next_id(self) -> str:
        self.node_counter += 1
        return f"node_{self.node_counter}"

    def run(self, initial_prompt: str, test_code: str = "") -> Optional[SearchNode]:
        """
        Run the MCTS search.
        Returns the winning node, or the node with the highest value if none passed.
        """
        print("\n" + "=" * 60)
        print(" TEST-TIME COMPUTE: MCTS CODE GENERATION")
        print("=" * 60)
        
        root = SearchNode(id=self._next_id(), prompt=initial_prompt)
        best_node = None

        for i in range(self.num_rollouts):
            print(f"\n[TTC] Starting Rollout {i+1}/{self.num_rollouts}")
            
            # 1. Selection
            node = self._select(root)
            
            # 2. Expansion (if not terminal and not passed)
            if not node.is_terminal and not node.passed:
                node = self._expand(node)
                
            # 3. Simulation (Execution)
            if not node.passed and node.code:
                reward, passed, error = self._simulate(node, test_code)
                node.passed = passed
                node.error_msg = error
                node.is_terminal = passed or (self._get_depth(node) >= self.max_depth)
                
                # Check if we won
                if passed:
                    print(f"  [TTC] 🌟 SUCCESS on rollout {i+1} at depth {self._get_depth(node)}")
                    best_node = node
                    break
            else:
                reward = 1.0 if node.passed else 0.0

            # 4. Backpropagation
            self._backpropagate(node, reward)

        if not best_node:
            print(f"\n[TTC] Max rollouts reached. Returning best attempt.")
            best_node = self._get_best_child(root)

        return best_node

    def _select(self, node: SearchNode) -> SearchNode:
        """Traverse the tree choosing the node with the highest UCB1 score."""
        current = node
        while current.children and all(c.visits > 0 for c in current.children):
            current = max(current.children, key=lambda c: c.ucb1())
        return current

    def _expand(self, node: SearchNode) -> SearchNode:
        """Generate a new candidate code solution from the model."""
        print(f"  [TTC] Expanding {node.id} at depth {self._get_depth(node)}")
        
        # Build prompt: if it's a root node, use the initial prompt.
        # If it's a child, we must feed back the error from the parent.
        if node.parent and node.parent.error_msg:
            # Self-healing prompt
            prompt = f"{node.parent.prompt}\n\nYour previous solution generated this error:\n{node.parent.error_msg}\n\nPlease fix the code."
        else:
            prompt = node.prompt

        try:
            generated_text = self.generate_fn(prompt)
            code = self._extract_code(generated_text)
        except Exception as e:
            print(f"  [TTC] Model generation failed: {e}")
            code = ""
            generated_text = ""

        child = SearchNode(
            id=self._next_id(),
            prompt=prompt,
            code=code,
            parent=node
        )
        node.children.append(child)
        return child

    def _simulate(self, node: SearchNode, test_code: str) -> Tuple[float, bool, str]:
        """Execute the code in the sandbox and return (reward, passed, error_msg)."""
        if not node.code:
            return 0.0, False, "No code generated."

        print(f"  [TTC] Simulating (executing) {node.id}...")
        
        full_code = node.code
        if test_code:
            full_code += f"\n\n{test_code}"

        result = self.sandbox.execute("python", full_code)
        
        if result.get("exit_code") == 0:
            return 1.0, True, ""
        
        # Failure
        error = result.get("stderr", result.get("stdout", ""))[:500]
        # Partial reward based on heuristics could go here. For now, binary.
        # Syntactic errors get 0.0, logical test failures get 0.2, etc.
        reward = 0.0
        if "AssertionError" in error:
            reward = 0.2
            
        print(f"  [TTC] Execution failed: {error.split(chr(10))[0]}")
        return reward, False, error

    def _backpropagate(self, node: SearchNode, reward: float):
        """Update node values up the tree."""
        current = node
        while current is not None:
            current.visits += 1
            current.value += reward
            current = current.parent

    def _get_best_child(self, node: SearchNode) -> SearchNode:
        """Get the most visited child (robustness)."""
        current = node
        while current.children:
            current = max(current.children, key=lambda c: c.visits)
        return current

    def _get_depth(self, node: SearchNode) -> int:
        depth = 0
        current = node
        while current.parent:
            depth += 1
            current = current.parent
        return depth

    def _extract_code(self, text: str) -> str:
        """Extract Python code from markdown blocks."""
        import re
        match = re.search(r'```(?:python)?\n(.*?)\n```', text, re.DOTALL)
        if match:
            return match.group(1)
        return text


# ============================================================================
# Dummy model generation for testing the TTC engine standalone
# ============================================================================
def _dummy_model_fn(prompt: str) -> str:
    """Mock model that eventually gets it right on self-healing."""
    if "error" in prompt.lower():
        # It's a self-healing prompt
        return "```python\ndef add(a, b):\n    return a + b\n```"
    else:
        # Deliberate bug
        return "```python\ndef add(a, b):\n    return a - b\n```"

def _self_test():
    print("Testing TTC Inference (MCTS)...")
    prompt = "Write a function `add(a, b)` that adds two numbers."
    test_code = "assert add(2, 2) == 4\nassert add(10, 5) == 15\nprint('Pass')"
    
    engine = MCTSCodeGenerator(model_generate_fn=_dummy_model_fn, max_depth=3, num_rollouts=5)
    best_node = engine.run(prompt, test_code)
    
    if best_node and best_node.passed:
        print("\n✓ TTC Inference SUCCESS: Model self-healed and found correct solution.")
        print(f"Final Code:\n{best_node.code}")
    else:
        print("\n✗ TTC Inference FAILED.")

if __name__ == "__main__":
    _self_test()
