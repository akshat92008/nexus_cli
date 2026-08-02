import re

with open("nexus/agent.py", "r") as f:
    code = f.read()

restore = """    def rollback_current_run(self) -> tuple[bool, str]:
        \"\"\"Atomically roll back every file operation recorded by this run.\"\"\"
        change_count = len(self.history.changes) - self._run_history_start
        if change_count <= 0:
            return False, "The current run has no applied file changes to roll back."
        success, detail = self.history.undo_changes(change_count)
        if success:
            self._run_finalizer.finish(
                "Run rolled back due to failing verification.",
                [],
                status_override=RunStatus.ROLLED_BACK,
            )
        return success, detail

"""

code = code.replace("    def _refresh_final_report_after_approval(", restore + "    def _refresh_final_report_after_approval(")

with open("nexus/agent.py", "w") as f:
    f.write(code)

with open("tests/test_agent_services.py", "r") as f:
    code = f.read()

code = code.replace("from typing import Any", "from typing import Any\nfrom unittest.mock import MagicMock")

with open("tests/test_agent_services.py", "w") as f:
    f.write(code)

