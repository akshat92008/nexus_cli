import sys
import os

# 4. Fix kernel.py
kernel_path = "nexus/runtime/kernel.py"
with open(kernel_path, "r") as f:
    content = f.read()
content = content.replace(
    'except (OSError, ValueError) as e:',
    'except Exception as e:'
)
with open(kernel_path, "w") as f:
    f.write(content)

print("Fixes applied successfully!")
