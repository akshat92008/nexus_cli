import re

with open("scratch_finalizer.py", "r") as f:
    code = f.read()

# Replace def _run_finalizer.finish with def finish
code = code.replace("def _run_finalizer.finish(", "def finish(")

# Write back
with open("scratch_finalizer.py", "w") as f:
    f.write(code)
