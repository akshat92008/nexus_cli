import ast
import os

def analyze_try_body(body):
    calls = []
    for node in ast.walk(ast.Module(body=body)):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
    return calls

for root, dirs, files in os.walk('nexus'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r') as f:
                    source = f.read()
                tree = ast.parse(source)
            except Exception:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    for handler in node.handlers:
                        if handler.type is None or (isinstance(handler.type, ast.Name) and handler.type.id == 'Exception'):
                            calls = analyze_try_body(node.body)
                            print(f"{filepath}:{handler.lineno} - {calls}")
