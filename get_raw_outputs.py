import json

runs = []
with open("guardrail_events.jsonl", "r") as f:
    events = [json.loads(line) for line in f]

for i in range(0, len(events), 2):
    runs.append(events[i])

target_runs = [6, 11, 12, 14]

for r in target_runs:
    idx = r - 1
    if idx < len(runs):
        run_data = runs[idx]
        print(f"--- RUN {r} ---")
        print(f"Failed Check: {run_data.get('check_failed')}")
        print("Raw Output:")
        print(run_data.get('original_output'))
        print("="*60 + "\n")
