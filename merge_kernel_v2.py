import re
import os

nexus_dir = "/Users/ashishsingh/Desktop/product/nexus"
engine_path = f"{nexus_dir}/runtime/engine.py"
exec_path = f"{nexus_dir}/execution.py"
kernel_path = f"{nexus_dir}/runtime/kernel.py"

with open(engine_path, "r") as f:
    engine_content = f.read()

with open(exec_path, "r") as f:
    exec_content = f.read()

# Extract imports and components from execution.py
exec_lines = exec_content.splitlines()
exec_imports = []
exec_classes_before = []
exec_engine_body = []
in_imports = True
in_engine = False

for line in exec_lines:
    if in_imports:
        if line.startswith("import") or line.startswith("from"):
            exec_imports.append(line)
        elif line.strip() != "":
            in_imports = False
            exec_classes_before.append(line)
    else:
        if line.startswith("class ExecutionEngine:"):
            in_engine = True
            continue
        if in_engine:
            exec_engine_body.append(line)
        else:
            exec_classes_before.append(line)

# Rename engine.py's ExecutionEngine to ExecutionKernel
engine_content = engine_content.replace("class ExecutionEngine:", "class ExecutionKernel:")
engine_content = engine_content.replace("ExecutionEngine:", "ExecutionKernel:")

# Change `def run(` to `def run_interactive(` in engine_content
engine_content = re.sub(r"def run\(\s*self,", "def run_interactive(self,", engine_content)
# Or just a simple replace
engine_content = engine_content.replace("    def run(\n", "    def run_interactive(\n")
engine_content = engine_content.replace("    def run(self", "    def run_interactive(self")

# Merge __init__ arguments
# Current engine __init__:
#     def __init__(
#         self,
#         provider: Provider,
#         max_turns: int = 50,
#         model_id: str | None = None,
#         run_id: str | None = None,
#     ):
# Current exec __init__:
#     def __init__(
#         self,
#         plan: ExecutionPlan,
#         ledger: RunLedger,
#         *,
#         max_total_repairs: int | None = None,
#     ):
new_init = """    def __init__(
        self,
        provider: Provider | None = None,
        max_turns: int = 50,
        model_id: str | None = None,
        run_id: str | None = None,
        plan: ExecutionPlan | None = None,
        ledger: RunLedger | None = None,
        max_total_repairs: int | None = None,
    ):
        self.provider = provider
        self.max_turns = max_turns
        if provider:
            self.model_id = (
                model_id
                or getattr(provider, "model_id", None)
                or getattr(provider, "id", "unknown")
            )
        else:
            self.model_id = model_id or "unknown"
        self.run_id = run_id
        self.state_machine = StateMachine()
        self.tool_executor: Callable[[str, dict], tuple[bool, str]] | None = None
        self.before_tool_hook: Callable[[str, dict], None] | None = None
        self.after_tool_hook: Callable[[str, dict, bool, str], None] | None = None

        self.plan = plan
        self.ledger = ledger
        configured = int(plan.retry_policy.get("total_repairs", 5)) if plan else 5
        self.max_total_repairs = max(0, configured if max_total_repairs is None else max_total_repairs)
        self.repairs = 0"""

# Replace __init__ in engine_content
init_start = engine_content.find("    def __init__(")
init_end = engine_content.find("    def run_interactive(", init_start)
engine_content = engine_content[:init_start] + new_init + "\n\n" + engine_content[init_end:]

# Add `run_dag` and other methods from exec_engine_body
# In exec_engine_body, replace `def run(` with `def run_dag(`
exec_engine_str = "\n".join(exec_engine_body)
exec_engine_str = exec_engine_str.replace("    def run(", "    def run_dag(")

kernel_content = "\n".join(exec_imports) + "\n" + "\n".join(exec_classes_before) + "\n\n" + engine_content + "\n\n" + exec_engine_str

with open(kernel_path, "w") as f:
    f.write(kernel_content)
print("kernel.py created")

