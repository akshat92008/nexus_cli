import re

with open("nexus/agent.py", "r") as f:
    content = f.read()

# Replace the giant _execute_tool_with_safety_impl with our decomposed methods.
# Since it's a huge method, we will find its boundaries and replace it.
# We'll use AST to find it, or simple regex.
import ast

class AgentVisitor(ast.NodeVisitor):
    def __init__(self):
        self.start = None
        self.end = None
    def visit_FunctionDef(self, node):
        if node.name == '_execute_tool_with_safety_impl':
            self.start = node.lineno
            self.end = node.end_lineno
        self.generic_visit(node)

tree = ast.parse(content)
v = AgentVisitor()
v.visit(tree)

lines = content.split('\n')
if v.start and v.end:
    pre = lines[:v.start-1]
    post = lines[v.end:]
    
    new_impl = """
    def _execute_tool_with_safety_impl(
        self,
        name: str,
        args: dict,
        *,
        _user_confirmed: bool = False,
        _edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        \"\"\"Execute a tool with full safety checks, hooks, and context tracking.\"\"\"
        from nexus.tools import normalize_tool_arguments
        args = normalize_tool_arguments(name, args)
        pending_args = dict(args)
        
        file_path = args.get("path", "") or args.get("file_path", "")
        command = args.get("command", "")
        if name == "run_process":
            import shlex
            raw_argv = args.get("argv", [])
            command = shlex.join(str(item) for item in raw_argv) if raw_argv else ""

        mutation_tools = ("write_file", "edit_file", "patch_file", "multi_edit")
        
        # 1. Enforce Tool Policy
        ok, res = self._enforce_tool_policy(name, args, command, pending_args, _user_confirmed, _edit_confirmed)
        if not ok:
            return res
            
        # 2. Enforce Network Safety
        ok, res = self._enforce_network_safety(name, args, command, pending_args, _user_confirmed, _edit_confirmed)
        if not ok:
            return res

        # 3. Enforce Package Safety
        ok, package_warning, res = self._enforce_package_safety(name, args, command, pending_args, _user_confirmed, _edit_confirmed)
        if not ok:
            return res

        # 4. Prepare Mutation Diff
        ok, mutation_diff, res = self._prepare_mutation_diff(name, args, pending_args, _user_confirmed, _edit_confirmed)
        if not ok:
            return res
            
        # Resolve scope outside workspace
        ok, res = self._enforce_workspace_scope(name, args, pending_args, _user_confirmed, _edit_confirmed)
        if not ok:
            return res

        # 5. Dispatch
        return self._dispatch_tool_execution(
            name, args, command, mutation_diff, package_warning
        )

    def _enforce_tool_policy(self, name: str, args: dict, command: str, pending_args: dict, _user_confirmed: bool, _edit_confirmed: bool) -> tuple[bool, tuple[str, bool]]:
        # Omitted for brevity in scratch. Let's write the actual logic.
        return True, ("", False)
"""
# I will not run this yet until I have the full new_impl strings.
