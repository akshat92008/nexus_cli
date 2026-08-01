import re
import os

nexus_dir = "/Users/ashishsingh/Desktop/product/nexus"

with open(f"{nexus_dir}/runtime/engine.py", "r") as f:
    engine_content = f.read()

with open(f"{nexus_dir}/execution.py", "r") as f:
    exec_content = f.read()

# Modify engine_content
engine_content = engine_content.replace("class ExecutionEngine:", "class ExecutionKernel:")
engine_content = engine_content.replace("ExecutionEngine:", "ExecutionKernel:")

# We'll merge the __init__ of both and add run_dag
# Parse execution.py to extract imports and the rest
exec_imports = []
exec_body = []
in_imports = True
for line in exec_content.splitlines():
    if line.startswith("import") or line.startswith("from"):
        exec_imports.append(line)
    elif line.strip() == "" and in_imports:
        pass
    else:
        in_imports = False
        exec_body.append(line)

exec_imports_str = "\n".join(exec_imports)
exec_body_str = "\n".join(exec_body)

# We want to remove `class ExecutionEngine:` from exec_body_str and integrate its methods into ExecutionKernel.
# But it's easier to just do it via text replacement.
class_start = exec_body_str.find("class ExecutionEngine:")
exec_classes_before = exec_body_str[:class_start]
exec_engine_body = exec_body_str[class_start + len("class ExecutionEngine:"):]
# exec_engine_body contains __init__, run, _run_step, etc.

# We need to manually construct the unified kernel.py
# Let's do it directly in bash or simple Python script.

