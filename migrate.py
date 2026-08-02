import re

with open("nexus/run_finalizer.py", "r") as f:
    finalizer_code = f.read()

with open("scratch_finalizer.py", "r") as f:
    scratch_code = f.read()

# Replace the existing finish method with the scratch_code
# First we find the boundary
# The finish method in run_finalizer.py is from line 90 to 108

# We want to insert imports as well
imports_to_add = """
import json
from fnmatch import fnmatch
from pathlib import Path
from nexus.run_state import CriterionResult, CriterionStatus, RunStatus
from nexus.planner import IntentType

def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
        return True
    except ValueError:
        return False
"""

finalizer_code = finalizer_code.replace("from typing import TYPE_CHECKING, Any", "from typing import TYPE_CHECKING, Any\n" + imports_to_add)

# Find where `def finish(` starts in finalizer_code
match = re.search(r'    def finish\(.*?    \) -> dict\[str, Any\]:.*?(?=    # ───)', finalizer_code, flags=re.DOTALL | re.MULTILINE)

if match:
    finalizer_code = finalizer_code[:match.start()] + scratch_code + "\n" + finalizer_code[match.end():]
else:
    print("Could not find finish() in run_finalizer.py")

with open("nexus/run_finalizer.py", "w") as f:
    f.write(finalizer_code)

# Now remove the methods from agent.py
with open("nexus/agent.py", "r") as f:
    agent_code = f.read()

# We need to remove lines 1160 to 1775
# Let's just find `def _evaluate_unrelated_files(` and `def _gather_context(`
start_match = re.search(r'    def _evaluate_unrelated_files\(', agent_code)
end_match = re.search(r'    # ── Message Building ───', agent_code)

if start_match and end_match:
    agent_code = agent_code[:start_match.start()] + "\n" + agent_code[end_match.start():]
else:
    print("Could not find bounds in agent.py")

# Wait, Agent._run_finalizer.finish was called inside agent.py somewhere. We need to replace it with self._run_finalizer.finish()
agent_code = agent_code.replace("self._run_finalizer.finish(", "self._run_finalizer.finish(")

with open("nexus/agent.py", "w") as f:
    f.write(agent_code)

