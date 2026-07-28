import urllib.request
import json
import time
import re

PROMPTS = [
    "Create a React app with a Python FastAPI backend and CSS modules.",
    "Build a full-stack to-do app using Vue.js, Node.js Express, and MongoDB. Provide all necessary files.",
    "Implement a chat application with a Go WebSocket server and a plain HTML/JS/CSS frontend.",
    "Create a blog engine with a Ruby on Rails backend and a React frontend.",
    "Set up a project with a Django backend and a Svelte frontend, including a docker-compose.yml."
]

def query_model(prompt):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "nova3b:latest",
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8")).get("response", "")
    except Exception as e:
        return f"Error: {e}"

print("Running Multi-File Category (5 prompts)...")
passed = 0
results = []
for i, p in enumerate(PROMPTS):
    out = query_model(p)
    file_count = len(re.findall(r'# filepath:|// filepath:|<!-- filepath:|/\* filepath:', out))
    is_pass = file_count >= 2
    if is_pass: passed += 1
    results.append(f"Prompt {i+1}: {'PASS' if is_pass else 'FAIL'} ({file_count} files generated)")
    print(results[-1])

print(f"\nMULTI-FILE SCORE: {passed}/5")
