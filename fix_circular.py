import re

with open("nexus/run_finalizer.py", "r") as f:
    code = f.read()

# Remove the import from nexus.agent
code = code.replace("from nexus.agent import _redact_runtime_text\n", "")

# Add local import in finish()
local_import = "        from nexus.agent import _redact_runtime_text\n"
# Find def finish(
match = re.search(r'    def finish\(.*?    \) -> dict\[str, Any\]:', code, flags=re.DOTALL)
if match:
    code = code[:match.end()] + "\n" + local_import + code[match.end():]
else:
    print("Could not find finish method")

with open("nexus/run_finalizer.py", "w") as f:
    f.write(code)
