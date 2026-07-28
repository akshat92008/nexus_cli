import json
import random
import requests
import re
from datasets import load_dataset
import traceback

def run_tests():
    print("Loading dataset...")
    dataset = load_dataset("json", data_files={"train": "dataset_nova_intern_v5.jsonl"}, split="train")
    split = dataset.train_test_split(test_size=0.15, seed=42)
    eval_dataset = split["test"]
    
    # Sample 5 examples
    random.seed(456)
    indices = random.sample(range(len(eval_dataset)), 5)
    samples = [eval_dataset[i] for i in indices]
    
    # We need the actual test assertions. The jsonl doesn't have the test assertions!
    # It only has the prompt and the assistant response.
    # We need to load the original MBPP dataset to get the test_list.
    print("Loading original MBPP dataset for test assertions...")
    mbpp = load_dataset("mbpp")
    mbpp_all = list(mbpp['train']) + list(mbpp['validation']) + list(mbpp['test'])
    
    def get_mbpp_tests(task_id):
        for item in mbpp_all:
            if item['task_id'] == task_id:
                return item['test_list']
        return []

    passes = 0
    
    for i, example in enumerate(samples):
        task_id = example['metadata']['task_id']
        tests = get_mbpp_tests(task_id)
        
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
            
        form_b = f"Can you write some Python code for this? {core_task}"
        
        print("="*60)
        print(f"EXAMPLE {i+1} (Task ID: {task_id})")
        print("RAW PROMPT:")
        print(form_b)
        print("-" * 30)
        
        # Call ollama with empty system prompt
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "nova-trained",
            "prompt": form_b,
            "system": "",  # Explicitly override the system prompt to empty!
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024}
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=60).json().get("response", "")
        except Exception as e:
            print("Ollama Error:", e)
            continue
            
        print("RAW MODEL OUTPUT:")
        print(resp)
        print("-" * 30)
        
        # Extract python code
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
                        print(f"FAILED TEST: {test_str}")
                        tests_passed = False
                        break
                    except Exception as e:
                        print(f"ERROR IN TEST {test_str}: {e}")
                        tests_passed = False
                        break
                
                if tests_passed:
                    print("✅ RESULT: ALL TESTS PASSED!")
                    passes += 1
                else:
                    print("❌ RESULT: TESTS FAILED!")
                    
            except Exception as e:
                print(f"❌ RESULT: CODE EXECUTION ERROR: {e}")
                
        else:
            print("❌ RESULT: NO CODE BLOCK FOUND!")
            
    print("="*60)
    print(f"FINAL SCORE: {passes}/5 ({(passes/5)*100:.1f}%)")

if __name__ == "__main__":
    run_tests()
