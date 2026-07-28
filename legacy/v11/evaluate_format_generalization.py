import json
import re
import requests
import random
from datasets import load_dataset
import time

def evaluate():
    print("Loading dataset and reconstructing the 85/15 split (seed=42)...")
    dataset = load_dataset("json", data_files={"train": "dataset_nova_intern_v5.jsonl"}, split="train")
    split = dataset.train_test_split(test_size=0.15, seed=42)
    eval_dataset = split["test"]
    
    total_eval = len(eval_dataset)
    print(f"Total held-out examples: {total_eval}")
    
    # We will sample 20 examples for a timely evaluation. 
    # (Running all 145 on a local M3 Mac might take >1 hour)
    num_samples = 20
    print(f"Sampling {num_samples} examples for this evaluation...\n")
    
    random.seed(123)
    indices = random.sample(range(total_eval), num_samples)
    samples = [eval_dataset[i] for i in indices]
    
    results = {
        "exact": {"format_pass": 0, "code_present": 0},
        "rephrased": {"format_pass": 0, "code_present": 0}
    }
    
    def call_ollama(prompt):
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "nova-intern-3b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024}
        }
        try:
            response = requests.post(url, json=payload, timeout=120)
            return response.json().get("response", "")
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            return ""

    def check_format(text):
        has_thinking = "<<THINKING>>" in text
        has_files = "<<FILES>>" in text
        has_code = "```python" in text
        return (has_thinking and has_files), has_code

    for idx, example in enumerate(samples):
        # Extract the original user message
        messages = example.get("messages", [])
        user_msg = ""
        for m in messages:
            if m["role"] == "user":
                user_msg = m["content"]
                break
                
        # The training prompts look like:
        # "Task: {task_desc}\nPlease implement a single python function to solve this task."
        # Let's extract the core task description.
        core_task = user_msg
        if user_msg.startswith("Task: "):
            core_task = user_msg[6:]
        if "\nPlease implement" in core_task:
            core_task = core_task.split("\nPlease implement")[0]
            
        form_a = user_msg  # Exact training phrasing
        form_b = f"Can you write some Python code for this? {core_task}"  # Natural phrasing
        
        print(f"--- Example {idx+1}/{num_samples} ---")
        
        # Test Form A
        print("Running Form A (Exact phrasing)...")
        t0 = time.time()
        resp_a = call_ollama(form_a)
        t1 = time.time()
        format_pass_a, code_pass_a = check_format(resp_a)
        if format_pass_a: results["exact"]["format_pass"] += 1
        if code_pass_a: results["exact"]["code_present"] += 1
        print(f"  [Time: {t1-t0:.1f}s] Format OK: {format_pass_a} | Code OK: {code_pass_a}")
        
        # Test Form B
        print("Running Form B (Rephrased)...")
        t0 = time.time()
        resp_b = call_ollama(form_b)
        t1 = time.time()
        format_pass_b, code_pass_b = check_format(resp_b)
        if format_pass_b: results["rephrased"]["format_pass"] += 1
        if code_pass_b: results["rephrased"]["code_present"] += 1
        print(f"  [Time: {t1-t0:.1f}s] Format OK: {format_pass_b} | Code OK: {code_pass_b}")
        print()

    print("==================================================")
    print("EVALUATION RESULTS (N={})".format(num_samples))
    print("==================================================")
    print("Form A (Exact Training Phrasing):")
    print(f"  Format Accuracy (<<THINKING>> & <<FILES>>): {results['exact']['format_pass']}/{num_samples} ({results['exact']['format_pass']/num_samples*100:.1f}%)")
    print(f"  Code Block Present: {results['exact']['code_present']}/{num_samples} ({results['exact']['code_present']/num_samples*100:.1f}%)")
    print("\nForm B (Natural Rephrased):")
    print(f"  Format Accuracy (<<THINKING>> & <<FILES>>): {results['rephrased']['format_pass']}/{num_samples} ({results['rephrased']['format_pass']/num_samples*100:.1f}%)")
    print(f"  Code Block Present: {results['rephrased']['code_present']}/{num_samples} ({results['rephrased']['code_present']/num_samples*100:.1f}%)")
    print("==================================================")

if __name__ == "__main__":
    evaluate()
