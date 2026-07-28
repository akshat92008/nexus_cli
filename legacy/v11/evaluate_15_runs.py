import json
import re
from output_parser import NovaOutputParser
from constraint_checker import ConstraintExtractor, ConstraintVerifier
from pipeline import CeilingNode

cases = [
    {"name": "Case 5 (Context + Assignment)", "prompt": "URGENT: users without profile pictures are crashing the app when viewing their profile. the bug is in src/auth.py at line 40. if profile_pic_url is null, set it to an empty string instead of crashing.", "file": "src/auth.py", "target": "profile_pic_url"},
    {"name": "Case 6 (Context + Status/String)", "prompt": "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails.", "file": "src/app.js", "target": "healthcheck"},
    {"name": "Fresh Case 1 (Assignment)", "prompt": "URGENT: the retry logic is looping infinitely. in src/utils.py around line 75, if max_retries is not provided, set it to 3 instead of 5.", "file": "src/utils.py", "target": "max_retries"},
    {"name": "Fresh Case 2 (Status Code + String JS)", "prompt": "URGENT: payment endpoint is returning wrong code. in src/routes/api.js at line 90, change the failure response to return 402 with status: 'Payment Required'.", "file": "src/routes/api.js", "target": "payment"},
    {"name": "Fresh Case 3 (String Output Python)", "prompt": "URGENT: logging monitor is missing timeouts. in src/worker.py line 50, change the exception print output to exactly 'Worker Timeout'.", "file": "src/worker.py", "target": "worker"}
]

ceiling = CeilingNode(provider="mock")
extractor = ConstraintExtractor(ceiling)
verifier = ConstraintVerifier(ceiling)
parser = NovaOutputParser()

with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()

results = []

for i in range(0, len(lines), 2):
    if i + 1 >= len(lines):
        break
    data = json.loads(lines[i])
    case_idx = (i // 2) // 3
    run_idx = ((i // 2) % 3) + 1
    if case_idx >= len(cases):
        break
        
    case = cases[case_idx]
    
    # Determine narrowing trigger
    prompt_desc = case['prompt']
    match_type = "None"
    match_val = ""
    line_match = re.search(r'line\s+(\d+)', prompt_desc, re.IGNORECASE)
    if line_match:
        match_type = "Line"
        match_val = line_match.group(1)
    else:
        words = re.findall(r'\b[a-zA-Z_]\w{4,}\b', prompt_desc)
        words = sorted(words, key=len, reverse=True)
        for w in words:
            if w.lower() in ["urgent", "endpoint", "returning", "because", "variable", "undefined", "catch", "status"]:
                continue
            match_type = "Identifier"
            match_val = w
            break
            
    trigger_str = f"{match_type} ({match_val})"
    
    if data.get('retry_attempts'):
        output = data['retry_attempts'][-1]['retry_output']
    else:
        output = data['original_output']
        
    parsed = parser.parse(output)
    
    constraints = extractor.extract(case['prompt'])
    passed, reason = verifier.verify(constraints, parsed.files)
    
    category = "Unknown"
    is_valid_fix = False
    
    if not parsed.is_valid:
        if "```" in output or "```python" in output:
            category = "Double-Wrap"
        else:
            category = "Format-Error"
    elif len(parsed.files) == 0:
        category = "No-File-Output"
    else:
        f = parsed.files[0]
        if f.action.upper() == "CREATE":
            category = "Full-Dump"
            if passed:
                is_valid_fix = True
                
        elif f.action.upper() == "MODIFY":
            if "dummy_func" in output or "dummyFunc" in output:
                category = "Top-Grab"
            elif passed:
                category = "Success"
                is_valid_fix = True
            else:
                category = "Failed-Relevance"

    results.append({
        "case": case['name'],
        "run": run_idx,
        "category": category,
        "is_valid": is_valid_fix,
        "trigger": trigger_str
    })

print(f"Total runs processed: {len(results)}")
print("-" * 105)
print(f"{'Case':<40} | {'Run':<3} | {'Category':<16} | {'Valid?':<6} | {'Narrowing Trigger':<25}")
print("-" * 105)
for r in results:
    valid_str = "YES" if r['is_valid'] else "NO"
    print(f"{r['case']:<40} | {r['run']:<3} | {r['category']:<16} | {valid_str:<6} | {r['trigger']:<25}")
print("-" * 105)

counts = {}
for r in results:
    counts[r['category']] = counts.get(r['category'], 0) + 1

print("\nFailure Mode Counts:")
for k, v in counts.items():
    print(f"- {k}: {v}")
