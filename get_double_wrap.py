import json

with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()

for i in range(0, len(lines), 2):
    if i + 1 >= len(lines):
        break
    data = json.loads(lines[i])
    
    if data.get('retry_attempts'):
        output = data['retry_attempts'][-1]['retry_output']
    else:
        output = data['original_output']
        
    if "```" in output and "```python" in output: # Or JS
        if not ("<<<<<<<" in output and "=======" in output and ">>>>>>>" in output):
            # Wait, the parser logic for Double-Wrap is in evaluate_15_runs.py
            pass
            
    # Let's just use the exact logic from evaluate_15_runs.py
    from output_parser import NovaOutputParser
    parser = NovaOutputParser()
    parsed = parser.parse(output)
    if not parsed.is_valid:
        if "```" in output:
            print(f"--- Double Wrap Output Found ---")
            print(output)
            break
