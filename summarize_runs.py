import json

with open("guardrail_events.jsonl", "r") as f:
    lines = [json.loads(l) for l in f]

# Print summary per prompt group
for i in range(0, len(lines), 2):
    run_num = (i // 2) + 1
    ev = lines[i]
    print(f"--- Run {run_num} ---")
    print("Prompt:", ev.get("prompt", "")[:70])
    print("Check Failed:", ev.get("check_failed"))
    print("Original Output:")
    print(ev.get("original_output", "")[:200])
    print("\n" + "="*50)
