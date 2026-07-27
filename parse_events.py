import json

with open("guardrail_events.jsonl", "r") as f:
    events = [json.loads(line) for line in f]

# Each run logs an initial evaluation event and a final result event
# Let's group by run
runs = []
for i in range(0, len(events), 2):
    init_ev = events[i]
    final_ev = events[i+1] if i+1 < len(events) else {}
    runs.append((init_ev, final_ev))

print(f"Total runs recorded: {len(runs)}")
passed = 0
failed = 0

for idx, (init, final) in enumerate(runs, 1):
    status = final.get("status", "unknown")
    prompt = init.get("prompt", "")[:60] + "..."
    check_failed = init.get("check_failed") or final.get("check_failed")
    if status == "pass":
        passed += 1
        print(f"Run {idx:02d}: PASS | Prompt: {prompt}")
    else:
        failed += 1
        print(f"Run {idx:02d}: FAIL ({status}) | Reason: {check_failed} | Prompt: {prompt}")

print(f"\nFinal Tally: {passed}/{len(runs)} Passed ({passed/len(runs)*100:.1f}%)")
