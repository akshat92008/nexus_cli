import json
with open("guardrail_events.jsonl") as f:
    for i, line in enumerate(f):
        data = json.loads(line)
        if "final_status" in data:
            print(f"Run {i//2 + 1}: {data['final_status']} (Failed check: {data.get('check_failed')})")
