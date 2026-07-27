import json

with open("guardrail_events.jsonl", "r") as f:
    events = [json.loads(line) for line in f]

for idx in [7, 9, 13]: # 0-indexed for Runs 8, 10, 14
    ev = events[idx*2]
    print(f"=== RUN {idx+1} ===")
    print("PROMPT:", ev.get("prompt"))
    print("OUTPUT:")
    print(ev.get("original_output"))
    print("="*60 + "\n")
