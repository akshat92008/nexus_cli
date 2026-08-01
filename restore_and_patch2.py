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

start1 = content.find("    def _finish_managed_run(")
end1 = content.find("    def _sync_workspace(", start1)
content = content[:start1] + new_finish + "\n" + content[end1:]

start2 = content.find("    def _execute_tool_with_safety_impl(")
end2 = content.find("    def _get_tools(", start2)
content = content[:start2] + new_execute + "\n" + content[end2:]

with open("nexus/agent.py", "w") as f:
    f.write(content)

print("Agent restored and patched.")
