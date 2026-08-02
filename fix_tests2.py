import sys
import os

# 1. Fix pipeline.py (import Path)
pipeline_path = "nexus/pipeline.py"
with open(pipeline_path, "r") as f:
    content = f.read()
if "from pathlib import Path" not in content:
    content = content.replace("import logging\n", "import logging\nfrom pathlib import Path\n")
with open(pipeline_path, "w") as f:
    f.write(content)

# 2. Fix providers/router.py (Exception Handling)
router_path = "nexus/providers/router.py"
with open(router_path, "r") as f:
    content = f.read()
content = content.replace(
    'except (OSError, ValueError) as e:',
    'except Exception as e:'
)
content = content.replace(
    'except (OSError, ValueError) as err:',
    'except Exception as err:'
)
with open(router_path, "w") as f:
    f.write(content)

print("Fixes applied successfully!")
