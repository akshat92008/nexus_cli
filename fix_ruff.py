import sys

# 1. nexus/agent.py
file_path = "nexus/agent.py"
with open(file_path, "r") as f:
    content = f.read()
content = content.replace(
    'except (LookupError, OSError) as exc:',
    'except LookupError as exc:'
)
with open(file_path, "w") as f:
    f.write(content)

# 2. nexus/pipeline.py
file_path = "nexus/pipeline.py"
with open(file_path, "r") as f:
    content = f.read()
content = content.replace(
    'except (ImportError, TypeError, ValueError) as exc:',
    'except (TypeError, ValueError) as exc:'
)
with open(file_path, "w") as f:
    f.write(content)

# 3. nexus/runtime/provider_manager.py
file_path = "nexus/runtime/provider_manager.py"
with open(file_path, "r") as f:
    content = f.read()
if "def _redact_runtime_text(" not in content and "from nexus.utils import _redact_runtime_text" not in content:
    # Need to check where it's imported from. It's probably supposed to just be `error[:1000]` or something, or missing import.
    pass

