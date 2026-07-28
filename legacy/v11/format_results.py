import json

runs = []
events = []
with open("guardrail_events.jsonl", "r") as f:
    for line in f:
        events.append(json.loads(line))

for i in range(0, len(events), 2):
    run_info = events[i]
    merged_info = events[i+1] if i+1 < len(events) else {}
    runs.append((run_info, merged_info))

out = ""
passes = 0
reasons = {}

for idx, (run, merged) in enumerate(runs):
    status = run.get("final_status", "unknown")
    if status == "pass":
        passes += 1
    else:
        reason = run.get("check_failed", "unknown")
        reasons[idx+1] = reason
        
    out += f"--- RUN {idx+1} ---\n"
    out += f"Status: {status}\n"
    out += f"Failed Check: {run.get('check_failed', 'None')}\n"
    out += f"Original Output:\n{run.get('original_output', '')}\n"
    out += f"Retry Attempts: {json.dumps(run.get('retry_attempts', []), indent=2)}\n"
    out += f"Merged Content:\n{merged.get('merged_content', '')}\n"
    out += "="*80 + "\n\n"

print(f"Total Passed: {passes}/15")
print("Failure Reasons:")
for k, v in reasons.items():
    print(f"Run {k}: {v}")
    
with open("baseline_15_runs_retry_formatted.txt", "w") as f:
    f.write(out)
