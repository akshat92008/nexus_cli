import json
from collections import Counter

def analyze(file_path):
    c = Counter()
    try:
        with open(file_path, 'r') as f:
            for line in f:
                data = json.loads(line)
                messages = data.get("messages", [])
                for m in messages:
                    if m["role"] == "assistant":
                        if "<<CLARIFICATION>>" in m["content"]:
                            c["clarification"] += 1
                        elif "<<FILES>>" in m["content"] or "```" in m["content"]:
                            c["execute"] += 1
                        else:
                            c["other"] += 1
        return c
    except Exception as e:
        return str(e)

print("V7:", analyze("dataset_nova3b_v7.jsonl"))
print("V8:", analyze("dataset_nova3b_v8.jsonl"))
