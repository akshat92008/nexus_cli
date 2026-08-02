import sys
import os

# 1. Fix cli.py
cli_path = "nexus/cli.py"
with open(cli_path, "r") as f:
    content = f.read()
content = content.replace(
    'agent.close(discard_workspace=not agent.keep_workspace)',
    'agent.close(discard_workspace=not getattr(agent, "keep_workspace", False))'
)
with open(cli_path, "w") as f:
    f.write(content)

# 2. Fix sandbox.py
sandbox_path = "nexus/sandbox.py"
with open(sandbox_path, "r") as f:
    content = f.read()
content = content.replace('        "PYTHONPATH",\n', '')
content = content.replace('        "NODE_PATH",\n', '')
with open(sandbox_path, "w") as f:
    f.write(content)

# 3. Fix router.py
router_path = "nexus/providers/router.py"
with open(router_path, "r") as f:
    content = f.read()
content = content.replace(
    'except (OSError, ValueError) as exc:',
    'except Exception as exc:'
)
with open(router_path, "w") as f:
    f.write(content)

print("Fixes applied successfully!")
