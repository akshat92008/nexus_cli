import sys

def main():
    agent_file = "nexus/agent.py"
    with open(agent_file, "r") as f:
        lines = f.readlines()
        
    imports = []
    for line in lines[13:80]:
        if line.startswith("def ") or line.startswith("class "):
            break
        imports.append(line)
        
    imports_str = "".join(imports)
    
    for filename in ["nexus/runtime/provider_manager.py", "nexus/runtime/tool_manager.py", "nexus/runtime/workspace_manager.py"]:
        with open(filename, "r") as f:
            content = f.read()
        
        # Replace the hardcoded imports at the top
        content = content.replace("from typing import Any\nfrom pathlib import Path\nimport json\nimport os\n\n", imports_str + "\n")
        with open(filename, "w") as f:
            f.write(content)
            
if __name__ == '__main__':
    main()
