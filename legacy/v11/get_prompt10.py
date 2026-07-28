import urllib.request
import json

def query_ollama(prompt, model_name="nova3b-test"):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '')
    except Exception as e:
        return f"Error: {e}"

out = query_ollama("Explain microservices vs monolith architecture.")
print("--- FULL OUTPUT FOR PROMPT 10 ---")
print(out)
print("---------------------------------")
