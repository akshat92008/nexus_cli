import json

with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()

def check_run(idx, name):
    data = json.loads(lines[idx*2])
    print(f"--- {name} ---")
    output = data.get('retry_attempts')[-1]['retry_output'] if data.get('retry_attempts') else data['original_output']
    
    lines_out = output.split('\n')
    for i, line in enumerate(lines_out):
        if '""' in line or "''" in line:
            print(f"Empty string found around line {i}:")
            start = max(0, i - 2)
            end = min(len(lines_out), i + 3)
            for j in range(start, end):
                print(f"{j}: {lines_out[j]}")
            print("-" * 20)

check_run(0, "Case 5 Run 1 (Index 0)")
