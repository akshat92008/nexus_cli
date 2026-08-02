from pathlib import Path
from nexus.sandbox import SandboxRunner, CommandSpec
spec = CommandSpec.create(["echo", "ok"], str(Path.cwd()), network=False)
print(f"require_os_isolation: {spec.require_os_isolation}")
