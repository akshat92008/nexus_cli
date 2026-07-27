import json
import re
from output_parser import NovaOutputParser

with open('guardrail_events.jsonl', 'r') as f:
    lines = f.readlines()
    data = json.loads(lines[6]) # Case 6 run 1 is at index 6 (actually line 6 is index 3)

parser = NovaOutputParser()
print("FINAL STATUS:", data['final_status'])

if data.get('retry_attempts'):
    output = data['retry_attempts'][-1]['retry_output']
else:
    output = data['original_output']

parsed = parser.parse(output)
print("PARSED FILES:", len(parsed.files))
for f in parsed.files:
    print("ACTION:", f.action)
