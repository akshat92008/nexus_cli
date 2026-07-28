import urllib.request
import json
import time

PROMPTS = [
    "Write a Python function to reverse a list in place.",
    "Show me a Hello World program in Go.",
    "Explain the CAP theorem in 3 bullet points.",
    "Write a bash script to find all .txt files and count them.",
    "How does a database index work?",
    "Write a React component for a simple counter.",
    "Write a C++ function that calculates the factorial of a number.",
    "What is the difference between REST and GraphQL?",
    "Create a SQL query to get the top 5 highest paid employees.",
    "Explain microservices vs monolith architecture."
]

def query_ollama(prompt, model_name="nova3b-test"):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '')
    except Exception as e:
        return f"Error: {e}"

def main():
    print("Testing nova3b-test model...")
    results = {}
    
    for i, prompt in enumerate(PROMPTS):
        print(f"\n[{i+1}/{len(PROMPTS)}] Prompt: {prompt}")
        
        start_time = time.time()
        output = query_ollama(prompt)
        duration = time.time() - start_time
        
        if "<<CLARIFICATION>>" in output:
            result_type = "REFUSED (<<CLARIFICATION>>)"
        elif "<<FILES>>" in output:
            result_type = "ACCEPTED (<<FILES>>)"
        elif "<<RESPONSE>>" in output:
            result_type = "ACCEPTED (<<RESPONSE>>)"
        else:
            result_type = "UNKNOWN FORMAT"
            
        print(f"Result: {result_type} ({duration:.2f}s)")
        print(f"Snippet: {output[:150].strip()}...\n")
        
if __name__ == "__main__":
    main()
