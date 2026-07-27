import json
with open('guardrail_events.jsonl') as f:
    lines = f.readlines()
last_lines = lines[-30:]
runs = []
for i in range(0, len(last_lines), 2):
    if i+1 >= len(last_lines): break
    try:
        run_data = json.loads(last_lines[i])
        runs.append(run_data)
    except:
        pass

run11 = runs[10]
print("Run 11 final_status:", run11['final_status'])
print("Run 11 retry count:", len(run11['retry_attempts']))
print("Run 11 last retry result:", run11['retry_attempts'][-1].get('result'))
print("Run 11 last retry output:\n", run11['retry_attempts'][-1].get('retry_output'))
