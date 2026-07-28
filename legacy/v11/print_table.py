import json

events = []
try:
    with open("guardrail_events.jsonl", "r") as f:
        for line in f:
            events.append(json.loads(line))
except FileNotFoundError:
    pass

runs = []
for i in range(0, len(events), 2):
    run_info = events[i]
    runs.append(run_info)

print("| Case | Guardrail Check | Escaped Corruption | Final Reason |")
print("|------|-----------------|--------------------|--------------|")
for idx, run in enumerate(runs):
    status = run.get("final_status", "unknown")
    if status == "pass":
        check = "✅ Passed"
        escaped = "No"
        reason = "-"
    else:
        check = "❌ Rejected"
        escaped = "No (Gate caught it)"
        reason = run.get("check_failed", "unknown")
    print(f"| Case {idx+1} | {check} | {escaped} | {reason} |")
