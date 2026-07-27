import re

with open("ADVANCED_STRESS_RESULTS.md", "r") as f:
    text = f.read()

for task_id in ["11", "13", "20"]:
    match = re.search(rf"(### Task {task_id}.*?)(?=### Task |\n## |\Z)", text, re.DOTALL)
    if match:
        print(match.group(1))
        print("-" * 50)
