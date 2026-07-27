import json

with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()

def check_run(idx, name):
    data = json.loads(lines[idx*2])
    print(f"--- {name} ---")
    output = data.get('retry_attempts')[-1]['retry_output'] if data.get('retry_attempts') else data['original_output']
    
    # Check if 'if profile_pic_url is None:' is in the output (since it was supposed to fix line 40)
    lines_out = output.split('\n')
    found_fix = False
    for i, line in enumerate(lines_out):
        if 'profile_pic_url = ' in line or 'profile_pic_url is null' in line.lower() or 'if profile_pic_url' in line:
            print(f"Context found around line {i}:")
            start = max(0, i - 2)
            end = min(len(lines_out), i + 3)
            for j in range(start, end):
                print(f"{j}: {lines_out[j]}")
            print("-" * 20)
            found_fix = True
    if not found_fix:
        print("Could not find the fix around profile_pic_url.")
        # Print the whole thing if needed? Or just print where dummy_func is to see what it did
        if 'dummy_func' in output:
            print("Found dummy_func, maybe it modified that instead?")

check_run(0, "Case 5 Run 1 (Index 0)")
check_run(1, "Case 5 Run 2 (Index 1)")
