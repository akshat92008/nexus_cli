import re

with open("nexus/run_finalizer.py", "r") as f:
    finalizer_code = f.read()

finalizer_code = finalizer_code.replace(
    "from nexus.planner import IntentType",
    "from nexus.planner import IntentType, TaskType, get_task_type\nfrom nexus.agent import _redact_runtime_text"
)

with open("nexus/run_finalizer.py", "w") as f:
    f.write(finalizer_code)

