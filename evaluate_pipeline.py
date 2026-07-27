import json
import os
import subprocess

# 1. Parse the weirdly formatted JSONL file to extract calculate_metrics
content = ""
with open('dataset_nova_intern_v3.jsonl', 'r') as f:
    text = f.read()
    # It contains two json objects. Let's split by '{"messages":' and grab the last one
    parts = text.split('{"messages":')
    if len(parts) >= 3:
        valid_json = '{"messages":' + parts[2].strip()
        try:
            data = json.loads(valid_json)
            content = data['messages'][1]['content']
        except Exception as e:
            print("Failed to parse JSON manually:", e)
            
if content:
    files_str = content.split("<<FILES>>\n")[1].split("\n\n<<TEST_COMMAND>>")[0]
    files = json.loads(files_str)
    for file in files:
        os.makedirs(os.path.dirname(file['path']) or '.', exist_ok=True)
        with open(file['path'], 'w') as out_f:
            out_f.write(file['content'])
    print("✅ Extracted src/utils.py successfully.")
    
    # 2. Write tests
    test_code = """
import pytest
from src.utils import calculate_metrics

def test_calculate_metrics_none():
    assert calculate_metrics(None) == []

def test_calculate_metrics_nested():
    payload = {"a": 3, "b": {"c": 1, "d": [5, 2]}, "e": 4}
    assert calculate_metrics(payload) == [1, 2, 3, 4, 5]
"""
    with open('test_utils.py', 'w') as f:
        f.write(test_code)
    
    # 3. Run pytest
    print("Running pytest on calculate_metrics...")
    result = subprocess.run(["pytest", "test_utils.py", "-v"], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print("❌ Pytest failed!")
        print(result.stderr)
    else:
        print("✅ Pytest passed perfectly!")

