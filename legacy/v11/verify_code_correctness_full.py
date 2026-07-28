import json
import re
import requests
import time
from datasets import load_dataset

def extract_func_name(test_str):
    match = re.search(r"assert\s+([a-zA-Z0-9_]+)\s*\(", test_str)
    if match:
        return match.group(1)
    return "solution"

def run_tests():
    print("Loading dataset...")
    dataset = load_dataset("json", data_files={"train": "dataset_nova_intern_v5.jsonl"}, split="train")
    split = dataset.train_test_split(test_size=0.15, seed=42)
    eval_dataset = split["test"]
    
    print("Loading original MBPP dataset for test assertions...")
    mbpp = load_dataset("mbpp")
    mbpp_all = list(mbpp['train']) + list(mbpp['validation']) + list(mbpp['test'])
    
    def get_mbpp_tests(task_id):
        for item in mbpp_all:
            if item['task_id'] == task_id:
                return item['test_list']
        return []

    total = len(eval_dataset)
    format_passes = 0
    code_passes = 0
    logic_errors = 0
    execution_errors = 0
    
    print(f"Evaluating {total} held-out examples...")
    
    for i, example in enumerate(eval_dataset):
        task_id = example['metadata']['task_id']
        tests = get_mbpp_tests(task_id)
        
        func_name = "solution"
        if tests:
            func_name = extract_func_name(tests[0])
            
        user_msg = ""
        for m in example.get("messages", []):
            if m["role"] == "user":
                user_msg = m["content"]
                break
                
        core_task = user_msg
        if user_msg.startswith("Task: "):
            core_task = user_msg[6:]
        if "\nPlease implement" in core_task:
            core_task = core_task.split("\nPlease implement")[0]
            
        form_b = f"Can you write some Python code for this? Name the function `{func_name}`. {core_task}"
        
        # Call ollama with empty system prompt
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "nova-trained",
            "prompt": form_b,
            "system": "",  # Explicitly override the system prompt to empty
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024}
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=60).json().get("response", "")
        except Exception as e:
            print(f"[{i+1}/{total}] ID {task_id}: API Error")
            continue
            
        # Extract python code
        has_thinking = "<<THINKING>>" in resp
        has_files = "<<FILES>>" in resp
        has_format = has_thinking and has_files
        
        if has_format:
            format_passes += 1
            
        match = re.search(r"```python\n(.*?)\n```", resp, re.DOTALL)
        if match:
            code = match.group(1)
            # Remove filepath and action comments
            code = "\n".join([line for line in code.split("\n") if not line.startswith("# filepath") and not line.startswith("# action")])
            
            # Execute code and tests
            try:
                namespace = {}
                exec(code, namespace)
                
                tests_passed = True
                for test_str in tests:
                    try:
                        exec(test_str, namespace)
                    except AssertionError:
                        logic_errors += 1
                        print(f"[{i+1}/{total}] ID {task_id}: ❌ LOGIC ERROR")
                        tests_passed = False
                        break
                    except Exception as e:
                        execution_errors += 1
                        print(f"[{i+1}/{total}] ID {task_id}: ❌ EXECUTION ERROR: {e}")
                        tests_passed = False
                        break
                
                if tests_passed:
                    code_passes += 1
                    print(f"[{i+1}/{total}] ID {task_id}: ✅ PASS")
                    
            except Exception as e:
                execution_errors += 1
                print(f"[{i+1}/{total}] ID {task_id}: ❌ SYNTAX/EXECUTION ERROR: {e}")
                
        else:
            print(f"[{i+1}/{total}] ID {task_id}: ❌ NO CODE BLOCK")
            
    print("="*60)
    print("FINAL RESULTS:")
    print(f"Total Evaluated: {total}")
    print(f"Format Accuracy: {format_passes}/{total} ({(format_passes/total)*100:.1f}%)")
    print(f"Code Correctness: {code_passes}/{total} ({(code_passes/total)*100:.1f}%)")
    print(f"Logic Errors (Failed Assertion): {logic_errors}")
    print(f"Execution Errors (Crash/NameError): {execution_errors}")
    print("="*60)

if __name__ == "__main__":
    run_tests()
