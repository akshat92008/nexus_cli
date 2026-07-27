import json
import os
import subprocess

with open('dataset_nova_intern_v3.jsonl', 'r') as f:
    lines = f.readlines()

# Grab the last line (the successfully generated one)
valid_line = lines[-1]
data = json.loads(valid_line)
content = data['messages'][1]['content']

files_str = content.split("<<FILES>>\n")[1].split("\n\n<<TEST_COMMAND>>")[0]
files = json.loads(files_str)
for file in files:
    os.makedirs(os.path.dirname(file['path']) or '.', exist_ok=True)
    with open(file['path'], 'w') as out_f:
        out_f.write(file['content'])

print("✅ Extracted src/utils.py")

# Create a test file to verify the model's code handles None and nested JSON correctly
test_code = """
import pytest
from src.utils import calculate_metrics

def test_calculate_metrics_none():
    assert calculate_metrics(None) == []

def test_calculate_metrics_nested():
    payload = {"a": 3, "b": {"c": 1, "d": [5, 2]}, "e": 4}
    # metrics extracted: 3, 1, 5, 2, 4 -> sorted: 1, 2, 3, 4, 5
    assert calculate_metrics(payload) == [1, 2, 3, 4, 5]
"""

with open('test_utils.py', 'w') as f:
    f.write(test_code)

print("✅ Created test_utils.py. Running pytest...")
