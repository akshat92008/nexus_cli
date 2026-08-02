import ast
import sys
import os

def check_file(filepath):
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        return
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.type is None or (isinstance(handler.type, ast.Name) and handler.type.id == 'Exception'):
                    lines = source.splitlines()
                    start_lineno = node.lineno
                    handler_lineno = handler.lineno
                    print(f"--- {filepath}:{handler_lineno} ---")
                    print('\n'.join(lines[start_lineno-1:handler_lineno+2]))
                    print()

for root, dirs, files in os.walk('nexus'):
    for file in files:
        if file.endswith('.py'):
            check_file(os.path.join(root, file))
