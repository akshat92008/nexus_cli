import sys

# 3. nexus/runtime/provider_manager.py
file_path = "nexus/runtime/provider_manager.py"
with open(file_path, "r") as f:
    content = f.read()

if "from nexus.agent import _redact_runtime_text" not in content:
    content = content.replace(
        'from nexus.runtime.kernel import ExecutionKernel',
        'from nexus.runtime.kernel import ExecutionKernel\nfrom nexus.agent import _redact_runtime_text'
    )
    with open(file_path, "w") as f:
        f.write(content)

print("Fixes applied successfully!")
