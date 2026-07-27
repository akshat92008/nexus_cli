#!/usr/bin/env python3
"""
agents.py — Autonomous ReAct Agent Architecture for Amuara Labs

Replaces the stub agents with a true ReAct (Reasoning and Acting) loop.
Features:
  - System prompt generation with available tools
  - Loop execution: Thought -> Action -> Observation -> ... -> Final Answer
  - Integration with ToolExecutor
  - State management and memory of steps taken
"""

import json
import time
from typing import List, Dict, Any, Optional

from tool_executor import ToolExecutor


class AgentState:
    """Maintains the conversational and operational state of the agent."""
    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self.scratchpad: str = ""
        self.steps_taken: int = 0

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})


class ReActAgent:
    """
    Autonomous Reasoning and Acting (ReAct) Agent.
    """
    def __init__(self, model_generate_fn, max_steps: int = 15):
        """
        Initialize the ReAct agent.
        
        Args:
            model_generate_fn: Function that takes (messages: List[Dict]) -> str (the model's response)
            max_steps: Maximum number of Tool execution loops before forcing a stop
        """
        self.tool_executor = ToolExecutor()
        self.generate_fn = model_generate_fn
        self.max_steps = max_steps
        self.tools_description = self._build_tools_description()

    def _build_tools_description(self) -> str:
        """Construct the prompt describing available tools."""
        desc = "You have access to the following tools:\n\n"
        for name, info in self.tool_executor.list_tools().items():
            desc += f"- {name}: {info['description']}\n"
        
        desc += """
To use a tool, please use the exact following format:
Thought: <your reasoning>
Action: <tool_name>
Action Input: <JSON formatted string containing arguments>

Example:
Thought: I need to read the file main.py
Action: read_file
Action Input: {"path": "main.py"}
"""
        return desc

    def _build_system_prompt(self) -> str:
        return f"""You are Nova, an autonomous software engineering agent by Amaura.
You can read files, write code, run terminal commands, and search the web to solve complex programming tasks.
Use the ReAct (Reasoning and Acting) framework to iteratively solve problems.

{self.tools_description}

When you are done and have the final answer to the user's request, use the exact following format:
Thought: I have solved the task.
Final Answer: <your final answer or summary of work>

Always provide your thought process before taking an action or providing the final answer.
"""

    def run(self, user_request: str) -> str:
        """
        Run the ReAct loop until completion or max steps.
        """
        state = AgentState()
        state.add_message("system", self._build_system_prompt())
        state.add_message("user", user_request)

        print(f"\n[Agent] Starting ReAct Loop for task: '{user_request[:50]}...'")

        for step in range(self.max_steps):
            state.steps_taken += 1
            
            # 1. Generate model output
            print(f"[Agent] Step {state.steps_taken} - Thinking...")
            try:
                response = self.generate_fn(state.history)
            except Exception as e:
                return f"Model generation failed: {e}"

            state.add_message("assistant", response)
            print(f"\n{response}\n")

            # 2. Parse Action
            parsed = self._parse_action(response)
            
            if parsed is None:
                # No action found, might be a malformed response or early termination
                if "Final Answer:" in response:
                    return response.split("Final Answer:", 1)[1].strip()
                else:
                    # Nudge the model to use tools or provide a final answer
                    state.add_message("user", "You did not provide an Action or a Final Answer. Please follow the required format.")
                    continue

            action_name, action_input = parsed

            # 3. Check for completion
            if action_name == "Final Answer":
                return action_input

            # 4. Execute Tool
            print(f"[Agent] Executing Tool: {action_name}")
            try:
                kwargs = json.loads(action_input) if action_input else {}
                result = self.tool_executor.execute(action_name, **kwargs)
                
                # Format result for the model
                if result.get("status") == "success":
                    observation = f"Observation: {result.get('output', 'Success (no output)')}"
                else:
                    observation = f"Observation (Error): {result.get('error', 'Unknown error')}"
                    
            except json.JSONDecodeError:
                observation = "Observation (Error): Invalid JSON in Action Input."
            except Exception as e:
                observation = f"Observation (Error): Tool execution failed - {e}"

            print(observation)
            state.add_message("user", observation)

        return "Agent stopped: Reached maximum number of steps."

    def _parse_action(self, text: str) -> Optional[tuple[str, str]]:
        """Extract Action and Action Input from model response."""
        import re
        
        # Check for final answer first
        final_answer_match = re.search(r'Final Answer:\s*(.*)', text, re.DOTALL)
        if final_answer_match:
            return "Final Answer", final_answer_match.group(1).strip()

        # Extract tool invocation
        action_match = re.search(r'Action:\s*([^\n]+)', text)
        input_match = re.search(r'Action Input:\s*(.*?)(?:\nThought:|\nObservation:|$)', text, re.DOTALL)
        
        if action_match and input_match:
            return action_match.group(1).strip(), input_match.group(1).strip()
            
        return None

# ============================================================================
# InternAgent — Nova 3B Execution Agent (Amaura)
# ============================================================================

class InternAgent:
    """
    Simplified agent for the Nova 3B "Intern" model.
    Unlike the full ReAct agent, this only generates code in the strict
    <<THINKING>>/<<FILES>>/<<TEST_COMMAND>> format — no tool loop.
    """

    def __init__(self, model: str = "nova3b"):
        self.model = model
        self._client = None
        self._parser = None

    @property
    def client(self):
        if self._client is None:
            from ollama_client import OllamaClient
            self._client = OllamaClient()
        return self._client

    @property
    def parser(self):
        if self._parser is None:
            from output_parser import NovaOutputParser
            self._parser = NovaOutputParser()
        return self._parser

    def execute(self, task: str, context: str = "") -> dict:
        """
        Execute a single coding task and return structured result.
        
        Returns:
            dict with keys: valid, thinking, files, test_command, raw, metrics
        """
        prompt = task
        if context:
            prompt = f"Context:\n{context}\n\nTask:\n{task}"

        result = self.client.nova_generate(prompt, model=self.model)
        parsed = self.parser.parse(result.text)

        return {
            "valid": parsed.is_valid,
            "thinking": parsed.thinking,
            "files": [f.to_dict() for f in parsed.files],
            "test_command": parsed.test_command,
            "errors": parsed.parse_errors,
            "raw": result.text,
            "metrics": result.metrics.summary(),
        }

    def batch_execute(self, tasks: List[str]) -> List[dict]:
        """Execute multiple tasks sequentially, passing context forward."""
        results = []
        context = ""

        for task in tasks:
            result = self.execute(task, context=context)
            results.append(result)

            # Accumulate context from successful executions
            if result["valid"]:
                for f in result["files"]:
                    context += f"\n# {f['path']}:\n{f['content'][:300]}\n"

        return results


# ============================================================================
# CeilingAgent — Task Decomposition Agent (Amaura)
# ============================================================================

class CeilingAgent:
    """
    Agent for the Ceiling/Reasoning node.
    Decomposes complex requests into atomic tasks for the InternAgent.
    Uses a remote API or local model.
    """

    SYSTEM_PROMPT = """You are the Ceiling Node — a Senior Architect in the Amaura pipeline.
Decompose the user's request into ATOMIC coding tasks. Each task must be:
1. A single, specific action (one file, one function, one fix)
2. Self-contained with all needed context
3. Ordered by dependency

Respond with a numbered list of tasks. Nothing else."""

    def __init__(self, generate_fn=None):
        """
        Args:
            generate_fn: Function that takes (messages: List[Dict]) -> str
        """
        self.generate_fn = generate_fn

    def decompose(self, request: str) -> List[str]:
        """Decompose a request into atomic task strings."""
        if self.generate_fn is None:
            # No ceiling model — return as single task
            return [request]

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": request},
        ]

        try:
            response = self.generate_fn(messages)
            # Parse numbered list
            import re
            tasks = re.findall(r'\d+\.\s*(.+)', response)
            return tasks if tasks else [request]
        except Exception as e:
            print(f"[CeilingAgent] Decomposition failed: {e}")
            return [request]


# ============================================================================
# Dummy model generation for testing the agent standalone
# ============================================================================
def _dummy_model_fn(history: List[Dict[str, str]]) -> str:
    """Mock model that just returns a final answer for testing."""
    last_msg = history[-1]['content']
    if "Observation:" in last_msg:
        return "Thought: I have the information I need.\nFinal Answer: Task completed successfully."
    else:
        return 'Thought: I need to check the current directory.\nAction: terminal\nAction Input: {"command": "ls -la"}'

if __name__ == "__main__":
    print("Testing Amaura Agent Architecture...")
    
    # Test ReAct Agent
    print("\n[1] ReAct Agent:")
    agent = ReActAgent(model_generate_fn=_dummy_model_fn, max_steps=3)
    final_output = agent.run("List the files in this directory.")
    print(f"    Result: {final_output[:80]}...")
    
    # Test InternAgent (requires Ollama)
    print("\n[2] InternAgent:")
    intern = InternAgent()
    if intern.client.is_running() and intern.client.has_model("nova3b"):
        result = intern.execute("Write a hello world function in Python")
        print(f"    Valid: {result['valid']}")
        print(f"    Metrics: {result['metrics']}")
    else:
        print("    ⚠️  Ollama not running or nova3b not found. Skipping.")
    
    print("\n✅ Agent architecture test complete.")
