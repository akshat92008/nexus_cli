import ast
import sys
import os

METHODS_TO_EXTRACT = {
    "provider": [
        "set_model",
        "_is_nova_model",
        "_should_use_two_node",
        "_record_provider_attempt",
        "_run_hosted_turn",
        "_run_two_node_turn",
        "_run_nova_turn",
    ],
    "tool": [
        "_coerce_capabilities",
        "_register_tool_capability",
        "_filesystem_argument_names",
        "_register_external_tool_capabilities",
        "_get_tools",
        "_format_live_tool_status",
        "_handle_tool_calls_interactive",
    ],
    "workspace": [
        "_queue_edit",
        "apply_pending_edit",
        "reject_pending_edit",
        "replace_pending_edit",
        "pending_edits_summary",
        "_queue_confirmation",
        "confirm_pending_operation",
        "cancel_pending_operation",
        "_apply_verified_workspace",
        "rollback_current_run",
    ]
}

def main():
    agent_file = "nexus/agent.py"
    with open(agent_file, "r") as f:
        source = f.read()
    
    lines = source.splitlines()
    tree = ast.parse(source)
    
    agent_class = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Agent":
            agent_class = node
            break
            
    if not agent_class:
        print("Agent class not found")
        return
        
    method_lines = {}
    for node in agent_class.body:
        if isinstance(node, ast.FunctionDef):
            # get decorators too
            start = node.lineno - 1
            if node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            end = node.end_lineno
            method_lines[node.name] = (start, end)
            
    lines_to_delete = set()
    
    for category, methods in METHODS_TO_EXTRACT.items():
        extracted_code = f"class {category.capitalize()}ManagerMixin:\n"
        for method in methods:
            if method in method_lines:
                start, end = method_lines[method]
                method_code = "\n".join(lines[start:end])
                extracted_code += method_code + "\n\n"
                for i in range(start, end):
                    lines_to_delete.add(i)
            else:
                print(f"Method {method} not found")
        
        # Write out mixin
        with open(f"nexus/runtime/{category}_manager.py", "w") as f:
            f.write("from typing import Any\nfrom pathlib import Path\nimport json\nimport os\n\n")
            f.write(extracted_code)
            
    # Update agent.py
    new_lines = []
    for i, line in enumerate(lines):
        if i not in lines_to_delete:
            new_lines.append(line)
            
    # Add imports and mixins to class definition
    agent_source = "\n".join(new_lines)
    
    import_stmt = "from nexus.runtime.provider_manager import ProviderManagerMixin\nfrom nexus.runtime.tool_manager import ToolManagerMixin\nfrom nexus.runtime.workspace_manager import WorkspaceManagerMixin\n"
    
    # insert after the last import
    # we'll just put it near the top
    agent_source = agent_source.replace("class Agent:", import_stmt + "\nclass Agent(ProviderManagerMixin, ToolManagerMixin, WorkspaceManagerMixin):")
    
    with open(agent_file, "w") as f:
        f.write(agent_source)
        
    print("Done")

if __name__ == '__main__':
    main()
