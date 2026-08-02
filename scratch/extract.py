import ast
import sys

def main(filename):
    with open(filename, "r") as f:
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
        
    for node in agent_class.body:
        if isinstance(node, ast.FunctionDef):
            print(f"{node.name}: {node.lineno} - {node.end_lineno}")

if __name__ == '__main__':
    main(sys.argv[1])
