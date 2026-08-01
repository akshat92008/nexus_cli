import re
import os

nexus_dir = "/Users/ashishsingh/Desktop/product/nexus"

# 1. Update nexus/agent.py
agent_path = f"{nexus_dir}/agent.py"
with open(agent_path, "r") as f:
    agent_content = f.read()

agent_content = agent_content.replace(
    "from nexus.runtime.engine import ExecutionEngine",
    "from nexus.runtime.kernel import ExecutionKernel"
)
agent_content = agent_content.replace(
    "engine = ExecutionEngine(",
    "engine = ExecutionKernel("
)
agent_content = agent_content.replace(
    "events = engine.run(",
    "events = engine.run_interactive("
)

with open(agent_path, "w") as f:
    f.write(agent_content)

# 2. Update nexus/two_node_backend.py
two_node_path = f"{nexus_dir}/two_node_backend.py"
with open(two_node_path, "r") as f:
    two_node_content = f.read()

two_node_content = two_node_content.replace(
    "from nexus.execution import (",
    "from nexus.runtime.kernel import ("
)
two_node_content = two_node_content.replace(
    "    ExecutionEngine,",
    "    ExecutionKernel,"
)
two_node_content = two_node_content.replace(
    "ExecutionEngine(",
    "ExecutionKernel("
)
two_node_content = two_node_content.replace(
    ").run(",
    ").run_dag("
)

with open(two_node_path, "w") as f:
    f.write(two_node_content)

# 3. Update nexus/runtime/__init__.py
runtime_init_path = f"{nexus_dir}/runtime/__init__.py"
with open(runtime_init_path, "r") as f:
    runtime_init_content = f.read()

runtime_init_content = runtime_init_content.replace(
    "from nexus.runtime.engine import ExecutionEngine",
    "from nexus.runtime.kernel import ExecutionKernel"
)
runtime_init_content = runtime_init_content.replace(
    '"ExecutionEngine",',
    '"ExecutionKernel",'
)

with open(runtime_init_path, "w") as f:
    f.write(runtime_init_content)

# Remove old files
try:
    os.remove(f"{nexus_dir}/runtime/engine.py")
except FileNotFoundError:
    pass

try:
    os.remove(f"{nexus_dir}/execution.py")
except FileNotFoundError:
    pass

print("Imports fixed and old files removed.")

