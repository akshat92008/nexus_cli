import re

with open("nexus/agent.py", "r") as f:
    content = f.read()

# Restore ExecutionSession
content = content.replace(
    "from nexus.runtime.kernel import ExecutionKernel",
    "from nexus.runtime.session import ExecutionSession"
)

old_loop = """        # --- NEW ENGINE EXECUTION LOOP ---
        _run_id = self.run_ledger.session_id if hasattr(self, "run_ledger") and self.run_ledger else None
        engine = ExecutionKernel(
            self.client,
            max_turns=max_iterations,
            model_id=self.model_cfg["id"],
            run_id=_run_id,
        )"""

new_loop = """        # --- NEW ENGINE EXECUTION LOOP ---
        _run_id = self.run_ledger.session_id if hasattr(self, "run_ledger") and self.run_ledger else None
        session = ExecutionSession(
            provider=self.client,
            max_turns=max_iterations,
            model_id=self.model_cfg["id"],
            run_id=_run_id,
        )
        engine = session.interactive"""

content = content.replace(old_loop, new_loop)

with open("new_finish.py", "r") as f:
    new_finish = f.read()

with open("new_execute.py", "r") as f:
    new_execute = f.read()

# Replace _finish_managed_run block
# From "    def _finish_managed_run(" to just before "    def _sync_workspace("
finish_pattern = re.compile(
    r"    def _finish_managed_run\(.*?    def _sync_workspace\(",
    re.DOTALL
)
content = finish_pattern.sub(new_finish + "\n    def _sync_workspace(", content)

# Replace _execute_tool_with_safety_impl block
# From "    def _execute_tool_with_safety_impl(" to just before "    def _get_tools("
execute_pattern = re.compile(
    r"    def _execute_tool_with_safety_impl\(.*?    def _get_tools\(",
    re.DOTALL
)
content = execute_pattern.sub(new_execute + "\n    def _get_tools(", content)

with open("nexus/agent.py", "w") as f:
    f.write(content)

print("Agent restored and patched.")
