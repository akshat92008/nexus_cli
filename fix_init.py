import re

with open("nexus/agent.py", "r") as f:
    code = f.read()

# 1. Add import
code = code.replace("from nexus.run_catalog import RunCatalog", "from nexus.run_catalog import RunCatalog\nfrom nexus.run_finalizer import RunFinalizer")

# 2. Add initialization
init_addition = """
        # Fire session start hook
        self.hooks.fire(HookEvent.ON_SESSION_START, HookContext(event=HookEvent.ON_SESSION_START))
        self._run_finalizer = RunFinalizer(self)
"""
code = code.replace("        # Fire session start hook\n        self.hooks.fire(HookEvent.ON_SESSION_START, HookContext(event=HookEvent.ON_SESSION_START))\n", init_addition)

with open("nexus/agent.py", "w") as f:
    f.write(code)

