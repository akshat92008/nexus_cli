import json

def count_dataset(filename):
    total = 0
    clarification = 0
    files = 0
    responses = 0

    try:
        with open(filename, 'r') as f:
            for line in f:
                if not line.strip(): continue
                total += 1
                data = json.loads(line)
                messages = data.get('messages', [])
                output = messages[-1]['content'] if messages else ""
                
                if '<<CLARIFICATION>>' in output:
                    clarification += 1
                elif '<<FILES>>' in output:
                    files += 1
                elif '<<RESPONSE>>' in output:
                    responses += 1

        print(f"Stats for {filename}:")
        print(f"  Total examples: {total}")
        print(f"  <<FILES>>: {files}")
        print(f"  <<CLARIFICATION>>: {clarification}")
        print(f"  <<RESPONSE>>: {responses}")
        print("-" * 40)
    except FileNotFoundError:
        print(f"{filename} not found.")

count_dataset('/Users/ashishsingh/Desktop/nova-1.5b/dataset_nova3b_v9.jsonl')
