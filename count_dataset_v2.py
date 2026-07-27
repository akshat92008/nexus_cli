import json

def count_dataset(filename):
    total = 0
    clarification = 0
    files = 0
    response = 0
    clarification_coding = 0
    clarification_noncoding = 0
    response_coding = 0
    response_noncoding = 0

    try:
        with open(filename, 'r') as f:
            for line in f:
                if not line.strip(): continue
                total += 1
                data = json.loads(line)
                messages = data.get('messages', [])
                output = messages[-1]['content'] if messages else ""
                prompt = messages[1]['content'] if len(messages) > 1 else ""

                if '<<CLARIFICATION>>' in output:
                    clarification += 1
                    if '```' in prompt or 'code' in prompt.lower() or 'function' in prompt.lower():
                        clarification_coding += 1
                    else:
                        clarification_noncoding += 1
                elif '<<FILES>>' in output:
                    files += 1
                elif '<<RESPONSE>>' in output:
                    response += 1
                    if '```' in prompt or 'code' in prompt.lower() or 'function' in prompt.lower():
                        response_coding += 1
                    else:
                        response_noncoding += 1

        print(f"Stats for {filename}:")
        print(f"  Total examples: {total}")
        print(f"  <<FILES>>: {files}")
        print(f"  <<CLARIFICATION>>: {clarification} (Coding prompts: {clarification_coding}, Non-coding prompts: {clarification_noncoding})")
        print(f"  <<RESPONSE>>: {response} (Coding prompts: {response_coding}, Non-coding prompts: {response_noncoding})")
        print("-" * 40)
    except FileNotFoundError:
        print(f"{filename} not found.")

count_dataset('/Users/ashishsingh/Desktop/nova-1.5b/dataset_nova3b_v7.jsonl')
count_dataset('/Users/ashishsingh/Desktop/nova-1.5b/dataset_nova3b_v8.jsonl')
