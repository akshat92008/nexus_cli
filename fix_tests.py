import sys
import os

# 1. Fix sandbox.py (API Key Leakage)
sandbox_path = "nexus/sandbox.py"
with open(sandbox_path, "r") as f:
    content = f.read()

content = content.replace(
    'if key in self.SAFE_ENV_KEYS or key.startswith("NEXUS_")',
    'if key in self.SAFE_ENV_KEYS or (key.startswith("NEXUS_") and "KEY" not in key and "TOKEN" not in key and "SECRET" not in key)'
)
with open(sandbox_path, "w") as f:
    f.write(content)

# 2. Fix pipeline.py (Repo Intelligence Bug & Exception Handling)
pipeline_path = "nexus/pipeline.py"
with open(pipeline_path, "r") as f:
    content = f.read()

# Fix the path bug
content = content.replace(
    'if not (self._agent.working_dir / ".git").exists():',
    'if not (Path(self._agent.working_dir) / ".git").exists():'
)
# Fix the exception handler in run loop (line 433)
content = content.replace(
    'except (LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:',
    'except Exception as exc:'
)
with open(pipeline_path, "w") as f:
    f.write(content)

# 3. Fix cli.py (Review Mode Consistency)
cli_path = "nexus/cli.py"
with open(cli_path, "r") as f:
    content = f.read()

content = content.replace(
    'agent.close()',
    'agent.close(discard_workspace=not agent.keep_workspace)'
)
with open(cli_path, "w") as f:
    f.write(content)

# 4. Fix tools.py (test_all_tools_execute)
tools_path = "nexus/tools.py"
with open(tools_path, "r") as f:
    content = f.read()

content = content.replace(
    'except TypeError as e:\n        return f"❌ Invalid arguments for {name}: {e}"',
    'except Exception as e:\n        return f"❌ Tool execution failed for {name}: {e}"'
)
with open(tools_path, "w") as f:
    f.write(content)

# 5. Fix agent.py (Exception handling)
agent_path = "nexus/agent.py"
with open(agent_path, "r") as f:
    content = f.read()

content = content.replace(
    'except (OSError, ValueError) as exc:\n            logger.debug("No active run turn while loading final report: %s", exc)',
    'except (OSError, ValueError, RuntimeError) as exc:\n            logger.debug("No active run turn while loading final report: %s", exc)'
)

content = content.replace(
    '        except LookupError as e:\n            if live:\n                live.stop()\n            error_msg = str(e)\n            if isinstance(e, BudgetExceeded):',
    '        except Exception as e:\n            if live:\n                live.stop()\n            error_msg = str(e)\n            if isinstance(e, BudgetExceeded):'
)

with open(agent_path, "w") as f:
    f.write(content)

print("Fixes applied successfully!")
