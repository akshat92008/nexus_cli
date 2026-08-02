import sys
from pathlib import Path
from nexus.sandbox import SandboxRunner, CommandSpec, SandboxBackend
runner = SandboxRunner(Path.cwd())
SandboxRunner._backend_cache = SandboxBackend.RESTRICTED
spec = CommandSpec.create(["echo", "ok"], str(Path.cwd()))
print(f"spec.require_os_isolation = {spec.require_os_isolation}")
try:
    runner.prepare(spec)
    print("Prepared OK")
except Exception as e:
    print(f"Exception: {e}")
