import sys

def run():
    with open("nexus/agent.py", "r") as f:
        lines = f.readlines()

    with open("new_finish.py", "r") as f:
        new_finish_lines = f.readlines()
        
    with open("new_execute.py", "r") as f:
        new_execute_lines = f.readlines()

    # Finish run is (699, 1044) - zero indexed is (698, 1044)
    # Execute tool is (1317, 1927) - zero indexed is (1316, 1927)

    # First we slice out execute_tool from bottom to avoid shifting finish
    top = lines[:1316]
    bottom = lines[1927:]
    
    lines = top + new_execute_lines + bottom
    
    # Now finish run (which hasn't shifted since it's above execute_tool)
    top = lines[:698]
    bottom = lines[1044:]
    
    lines = top + new_finish_lines + bottom
    
    with open("nexus/agent.py", "w") as f:
        f.writelines(lines)
        
    print("Agent patched successfully.")

run()
