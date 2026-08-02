import re
import os

path = 'nexus'
for root, dirs, files in os.walk(path):
    for f in files:
        if f.endswith('.py'):
            with open(os.path.join(root, f)) as file:
                content = file.read()
                if 'global ' in content or '_cache' in content or 'registry' in content.lower():
                    print(f"Found potential global in {os.path.join(root, f)}")
