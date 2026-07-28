import json
import re

with open('dataset_nova_intern.jsonl', 'r') as f:
    lines = f.readlines()

valid_json = 0
problems = []

for line in lines[-15:]:
    data = json.loads(line)
    problem = data['messages'][0]['content']
    problems.append(problem)
    
    content = data['messages'][1]['content']
    files_block_match = re.search(r'<<FILES>>\n(.*?)(\n<<TEST_COMMAND>>|$)', content, re.DOTALL)
    if files_block_match:
        try:
            files = json.loads(files_block_match.group(1))
            valid_json += 1
        except json.JSONDecodeError:
            pass

print(f"Sampled 15 problems. Valid JSON files blocks: {valid_json}/15")
print("\nRecent Problems Generated:")
for idx, p in enumerate(problems[:5]):
    print(f"{idx+1}. {p[:120]}...")
