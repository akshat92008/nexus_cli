import json
import re

def audit_dataset():
    file_path = "dataset_nova3b_v9.jsonl"
    
    total_files_examples = 0
    src_prefixed = 0
    bare_paths = 0
    other_paths = 0
    
    response_examples = 0
    response_touches_files = 0
    
    with open(file_path, "r") as f:
        for line in f:
            data = json.loads(line)
            output = ""
            for msg in data.get("messages", []):
                if msg.get("role") == "assistant":
                    output = msg.get("content", "")
            
            if "<<FILES>>" in output:
                # Find all filepath lines
                filepath_matches = re.findall(r"(?:#|//) filepath: (.*)", output)
                
                if filepath_matches:
                    total_files_examples += 1
                    for path in filepath_matches:
                        path = path.strip()
                        if path.startswith("src/"):
                            src_prefixed += 1
                        elif "/" not in path:
                            bare_paths += 1
                        else:
                            other_paths += 1
                            
            if "<<RESPONSE>>" in output:
                response_examples += 1
                if "<<FILES>>" in output or "filepath:" in output:
                    response_touches_files += 1

    print("=== DATASET AUDIT ===")
    print(f"Total <<FILES>> examples containing filepath: {total_files_examples}")
    print(f"Total filepaths extracted: {src_prefixed + bare_paths + other_paths}")
    print(f"  src/ prefixed paths: {src_prefixed} ({src_prefixed/(src_prefixed+bare_paths+other_paths)*100:.1f}%)")
    print(f"  Bare paths (no slashes): {bare_paths} ({bare_paths/(src_prefixed+bare_paths+other_paths)*100:.1f}%)")
    print(f"  Other paths: {other_paths} ({other_paths/(src_prefixed+bare_paths+other_paths)*100:.1f}%)")
    print()
    print(f"Total <<RESPONSE>> examples: {response_examples}")
    print(f"Total <<RESPONSE>> examples touching <<FILES>> or filepath: {response_touches_files}")

if __name__ == "__main__":
    audit_dataset()
