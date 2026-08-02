import re

with open("scratch_agent.py", "r") as f:
    code = f.read()

# Replace self. calls with self._agent. EXCEPT for self._evaluate_* 
# because those will be moved to RunFinalizer too.

def replacer(match):
    prop = match.group(1)
    if prop.startswith("_evaluate_"):
        return f"self.{prop}"
    return f"self._agent.{prop}"

code = re.sub(r'self\.([a-zA-Z_]\w*)', replacer, code)

with open("scratch_finalizer.py", "w") as f:
    f.write(code)

