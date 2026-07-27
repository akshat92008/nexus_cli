import json
import re
import requests
import time
import signal
from datasets import load_dataset

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Execution timed out")

def extract_func_name(test_str):
    match = re.search(r"assert\s+([a-zA-Z0-9_]+)\s*\(", test_str)
    if match:
        return match.group(1)
    return "solution"

def run_tests():
    dataset = load_dataset("json", data_files={"train": "dataset_nova_intern_v5.jsonl"}, split="train")
    split = dataset.train_test_split(test_size=0.15, seed=42)
    eval_dataset = split["test"]
    
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
    timeouts = 0
    
    # File to save logic error details for analysis
    error_log = open("logic_errors_analysis.txt", "w")
    
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
        
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "nova-trained",
            "prompt": form_b,
            "system": "",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024}
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=60).json().get("response", "")
        except Exception as e:
            continue
            
        has_thinking = "<<THINKING>>" in resp
        has_files = "<<FILES>>" in resp
        if has_thinking and has_files:
            format_passes += 1
            
        match = re.search(r"```python\n(.*?)\n```", resp, re.DOTALL)
        if match:
            code = match.group(1)
            code = "\n".join([line for line in code.split("\n") if not line.startswith("# filepath") and not line.startswith("# action")])
            
            try:
                namespace = {}
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(3)  # 3 second timeout for execution
                exec(code, namespace)
                
                tests_passed = True
                for test_str in tests:
                    try:
                        exec(test_str, namespace)
                    except AssertionError:
                        logic_errors += 1
                        error_log.write(f"TASK ID: {task_id}\nTASK: {core_task}\nTEST: {test_str}\nCODE:\n{code}\n{'-'*40}\n")
                        tests_passed = False
                        break
                    except TimeoutException:
                        raise
                    except Exception as e:
                        execution_errors += 1
                        tests_passed = False
                        break
                
                signal.alarm(0) # clear alarm
                
                if tests_passed:
                    code_passes += 1
                    
            except TimeoutException:
                timeouts += 1
                signal.alarm(0)
            except Exception as e:
                execution_errors += 1
                signal.alarm(0)
                
    error_log.close()
    
    with open("eval_robust_summary.txt", "w") as f:
        f.write(f"Total: {total}\n")
        f.write(f"Format Passes: {format_passes}\n")
        f.write(f"Code Passes: {code_passes}\n")
        f.write(f"Logic Errors: {logic_errors}\n")
        f.write(f"Execution Errors: {execution_errors}\n")
        f.write(f"Timeouts (Infinite loops): {timeouts}\n")

if __name__ == "__main__":
    run_tests()
