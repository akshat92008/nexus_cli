import re

with open("nexus/agent.py", "r") as f:
    code = f.read()

# I will add it right before `def _gather_context`
restore = """    def _refresh_final_report_after_approval(self) -> None:
        \"\"\"Recompute the final status after an approval queue changes.\"\"\"
        if not self.run_ledger.turn_dir or not self._active_objective:
            return
        prior = self.run_ledger.resume_summary().get("final_report", {})
        content = prior.get("metadata", {}).get("response_excerpt", "")
        self._run_finalizer.finish(content, [])

"""

code = code.replace("    def _gather_context(", restore + "    def _gather_context(")

with open("nexus/agent.py", "w") as f:
    f.write(code)

