import json

with open('guardrail_events.jsonl') as f:
    lines = f.readlines()

# We only care about the last 15 runs (which correspond to 30 lines since each run has 2 lines: run_data, merged_data)
# Let's just grab the last 30 lines.
last_lines = lines[-30:]

runs = []
for i in range(0, len(last_lines), 2):
    if i+1 >= len(last_lines): break
    try:
        run_data = json.loads(last_lines[i])
        merged_data = json.loads(last_lines[i+1])
        runs.append((run_data, merged_data))
    except Exception as e:
        pass

pass_count = 0
fail_reasons = []

for idx, (run_data, _) in enumerate(runs):
    status = run_data.get('final_status')
    if status == 'pass':
        pass_count += 1
    else:
        reason = run_data.get('check_failed', 'Unknown')
        fail_reasons.append(f"Run {idx+1} ({run_data.get('prompt')[:20]}...): {reason}")

print(f"Tally: {pass_count}/15 passed")
print("Failures:")
for f in fail_reasons:
    print(f)

print("\n--- Example Retry ---")
for idx, (run_data, _) in enumerate(runs):
    if run_data.get('retry_attempts'):
        print(f"Run {idx+1} retry prompt:\n{run_data['retry_attempts'][0].get('retry_prompt', '')}")
        break

