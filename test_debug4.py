import sys
from pathlib import Path
from nexus.sandbox import SandboxRunner, CommandSpec

spec = CommandSpec.create(["echo", "ok"], str(Path.cwd()), require_os_isolation=False)
runner = SandboxRunner(Path.cwd())
print(f"require_os_isolation: {spec.require_os_isolation}")
try:
    runner.prepare(spec)
    print("Prepared OK")
except Exception as e:
    print(f"Exception: {e}")
