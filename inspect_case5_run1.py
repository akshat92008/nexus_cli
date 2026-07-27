import json
with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()
data = json.loads(lines[0])
print("Final Status:", data['final_status'])
if data.get('retry_attempts'):
    for i, r in enumerate(data['retry_attempts']):
        print(f"Retry {i} result: {r['result']}")
