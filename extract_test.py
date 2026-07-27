import json

with open('dataset_nova_intern.jsonl', 'r') as f:
    lines = f.readlines()

# Find the log aggregator example, or just use the last few
for line in reversed(lines):
    if 'log_aggregator.py' in line:
        data = json.loads(line)
        content = data['messages'][1]['content']
        # The content has <<FILES>> ... JSON block. 
        # Let's parse it carefully.
        import re
        files_block = re.search(r'<<FILES>>\n(\[.*\])\n\n<<TEST_COMMAND>>', content, re.DOTALL)
        if files_block:
            files = json.loads(files_block.group(1))
            for file in files:
                with open(file['path'], 'w') as out_f:
                    out_f.write(file['content'])
            print("Extracted files successfully.")
            break
