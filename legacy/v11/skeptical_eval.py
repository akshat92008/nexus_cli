import urllib.request
import urllib.error
import json
import time
import re
import sys

MODEL_NAME = "nova3b"
OLLAMA_URL = "http://localhost:11434/api/generate"

PROMPTS = {
    "Messy Handoff": [
        "uh so the ceiling model said we need a cache. just use redis or whatever in src/cache.py and make it set/get with a ttl. dont overcomplicate it just do it fast.",
        "fix the bug where the user login fails if they dont have a profile pic. i think its in auth.py somewhere around line 40? just make it use a default empty string instead of crashing.",
        "yo nova make a go script that pings a database every 5 seconds. pg connection string is in env. put it in cmd/pinger/main.go. thx.",
        "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."
    ],
    "Massive Multi-File Refactor": [
        "Refactor the entire `auth` module. Split `src/auth.py` into `src/auth/models.py`, `src/auth/routes.py`, `src/auth/middleware.py`, and `src/auth/utils.py`. Update all imports across the 4 files.",
        "We are migrating from Express to Fastify. Rewrite `server.js`, `routes/api.js`, `routes/users.js`, and `middleware/logger.js` to use Fastify syntax. Return all 4 files.",
        "Take the monolithic `calculator.py` and break it into a package. I need `__init__.py`, `operations/basic.py`, `operations/advanced.py`, and `cli.py`.",
        "Separate our CSS. Take `styles.css` and split it out into `components/buttons.css`, `components/cards.css`, `layout/grid.css`, and `variables.css`."
    ],
    "Vague / Architectural": [
        "Build a scalable, cloud-native microservice architecture for a real-time chat application.",
        "How should I structure my database for a global social network?",
        "Design a machine learning pipeline that can predict customer churn with 99% accuracy.",
        "Create a secure, decentralized authentication system using blockchain."
    ],
    "In-Distribution Control": [
        "Write a Python script `src/metrics.py` that parses a CSV file and calculates the 95th percentile of the 'latency' column.",
        "Create a function in `utils/math.py` that calculates the factorial of a number iteratively.",
        "Implement a REST endpoint in `app.py` using Flask that returns the current UTC time in ISO format.",
        "Write a bash script `backup.sh` that zips the `/data` directory and moves it to `/backup`."
    ]
}

def analyze_response(response_text, duration):
    has_thinking = "<<THINKING>>" in response_text
    has_files = "<<FILES>>" in response_text
    has_test = "<<TEST_COMMAND>>" in response_text
    
    thinking_match = re.search(r'<<THINKING>>(.*?)<<FILES>>', response_text, re.DOTALL)
    thinking_words = len(thinking_match.group(1).split()) if thinking_match else 0
    
    # Very basic plausibility check (are there code blocks?)
    code_blocks = re.findall(r'```(.*?)```', response_text, re.DOTALL)
    file_declarations = re.findall(r'# filepath:(.*?)\n', response_text)
    
    is_plausible = len(code_blocks) > 0
    
    return {
        "format": has_thinking and has_files and has_test,
        "thinking_words": thinking_words,
        "is_plausible": is_plausible,
        "files_generated": len(file_declarations),
        "tps": len(response_text.split()) / duration if duration > 0 else 0 # Rough token estimate
    }

def run_evaluation():
    print(f"Starting rigorous evaluation of {MODEL_NAME}...\n")
    
    for category, prompts in PROMPTS.items():
        print(f"=== Category: {category} ===")
        for i, prompt in enumerate(prompts):
            print(f"\nPrompt {i+1}: {prompt[:80]}...")
            
            req_data = json.dumps({
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_ctx": 4096}
            }).encode('utf-8')
            
            req = urllib.request.Request(OLLAMA_URL, data=req_data, headers={'Content-Type': 'application/json'})
            
            start_time = time.time()
            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    end_time = time.time()
                    
                    duration = end_time - start_time
                    analysis = analyze_response(result['response'], duration)
                    
                    print(f"  Format EXACT: {'Yes' if analysis['format'] else 'No'}")
                    print(f"  Plausible/Valid Code Blocks: {'Yes' if analysis['is_plausible'] else 'No'}")
                    print(f"  Files Generated: {analysis['files_generated']}")
                    print(f"  Thinking Words: {analysis['thinking_words']}")
                    print(f"  Duration: {duration:.2f}s (~{analysis['tps']:.1f} rough TPS)")
                    
                    if not analysis['format']:
                        print(f"  [!] Failed format validation.")
                        
            except Exception as e:
                print(f"  [!] Request failed: {e}")
        print("\n" + "-"*50 + "\n")

if __name__ == "__main__":
    run_evaluation()
