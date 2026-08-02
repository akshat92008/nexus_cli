import sys
from pathlib import Path
from nexus.sandbox import SandboxRunner, CommandSpec
runner = SandboxRunner(Path.cwd())
spec = CommandSpec.create(["echo", "ok"], str(Path.cwd()))
res = runner.run(spec)
print(f"success: {res.success}, exit_code: {res.exit_code}, stdout: {res.stdout}")
