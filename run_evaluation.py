import urllib.request
import json
import time

MODELS = ["qwen2.5-coder:1.5b", "nova-intern"]

PROMPTS = {
    "Tier 1.1: Discount Calculator": "Implement a function calculate_discount(price: float, percent: float) -> float that returns the discounted price. Handle negative inputs by raising ValueError.",
    "Tier 1.2: Dict Sort": "Write a function that takes a list of dictionaries and returns them sorted by the 'created_at' key, descending.",
    "Tier 2: Diff/Patch": "Here is a function:\ndef process_user_data(user_dict):\n    active_users = []\n    for user_id, user_info in user_dict.items():\n        if user_info.get('status') == 'active':\n            score = user_info.get('score', 0)\n            multiplier = user_info.get('multiplier', 1.0)\n            final_score = score * multiplier\n            active_users.append({'id': user_id, 'final_score': final_score})\n    return sorted(active_users, key=lambda x: x['final_score'], reverse=True)\n\nModify it to add input validation for None. Output only the diff.",
    "Tier 3: Self-healing": "def divide(a, b):\n    return a / b\ndivide(5, 0)\n\nTraceback: ZeroDivisionError: division by zero\n\nFix it.",
    "Tier 4: Scope-boundary": "Design a distributed rate-limiting system across multiple microservices with Redis.",
    "Tier 5: Out-of-distribution (TS)": "Write a TypeScript React hook that debounces a search input."
}

def query_ollama(model_name, prompt):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0 # Force deterministic output for clean benchmarking
        }
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '')
    except Exception as e:
        return f"ERROR: {str(e)}"

results = {}

print("Starting evaluation suite...")
for model in MODELS:
    print(f"\n--- Testing Model: {model} ---")
    results[model] = {}
    for tier, prompt in PROMPTS.items():
        print(f"Querying {tier}...")
        start_time = time.time()
        response = query_ollama(model, prompt)
        elapsed = time.time() - start_time
        
        results[model][tier] = {
            "prompt": prompt,
            "response": response,
            "time_sec": round(elapsed, 2)
        }

with open("eval_results_raw.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nEvaluation complete! Saved to eval_results_raw.json")
