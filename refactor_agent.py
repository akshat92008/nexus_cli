import ast

with open("nexus/agent.py", "r") as f:
    content = f.read()

class TargetVisitor(ast.NodeVisitor):
    def __init__(self):
        self.finish_run = None
        self.execute_tool = None
    
    def visit_FunctionDef(self, node):
        if node.name == '_finish_managed_run':
            self.finish_run = (node.lineno, node.end_lineno)
        elif node.name == '_execute_tool_with_safety_impl':
            self.execute_tool = (node.lineno, node.end_lineno)
        self.generic_visit(node)

v = TargetVisitor()
v.visit(ast.parse(content))

print(f"_finish_managed_run: {v.finish_run}")
print(f"_execute_tool_with_safety_impl: {v.execute_tool}")

