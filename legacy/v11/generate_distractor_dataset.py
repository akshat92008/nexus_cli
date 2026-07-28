import json
import random

def generate_distractor_dataset(num_examples=40):
    dataset = []
    
    # Bug templates
    templates = [
        {
            "prompt": "URGENT: fix the bug in src/utils.py around line {target_line}. {instruction}.",
            "target": "def target_func_{id}(data):\n    # TODO: {instruction}\n    return data",
            "replace": "def target_func_{id}(data):\n    # FIXED: {instruction}\n    return process(data)",
            "decoy": "def dummy_func_{id}(data):\n    # DO NOT EDIT\n    return data"
        },
        {
            "prompt": "URGENT: production issue. the {target_name} function in src/api.js is failing. {instruction}.",
            "target": "function {target_name}(req, res) {{\n    // {instruction}\n    res.send(500);\n}}",
            "replace": "function {target_name}(req, res) {{\n    // FIXED\n    res.status(200).send('ok');\n}}",
            "decoy": "function dummyFunc{id}(req, res) {{\n    // DO NOT EDIT\n    res.send(200);\n}}"
        }
    ]

    instructions = [
        "ensure it returns a valid response",
        "add error handling",
        "prevent the infinite loop",
        "return an empty string instead of null",
        "change status code to 404"
    ]
    
    for i in range(num_examples):
        t = random.choice(templates)
        inst = random.choice(instructions)
        target_name = f"processData_{i}"
        
        # We need 4 functions (1 target, 3 decoys)
        funcs = []
        target_idx = random.randint(0, 3)
        
        target_line = 0
        
        for j in range(4):
            if j == target_idx:
                func_str = t["target"].format(id=j, instruction=inst, target_name=target_name)
                funcs.append((True, func_str))
            else:
                func_str = t["decoy"].format(id=j, target_name=target_name)
                funcs.append((False, func_str))
                
        # Build file content and excerpt
        content_lines = []
        start_line = 10
        current_line = start_line
        
        target_line = 0
        
        for is_target, f_str in funcs:
            if is_target:
                target_line = current_line + 1 # rough target line
            for line in f_str.split('\n'):
                content_lines.append(line)
                current_line += 1
            content_lines.append(f"# noise {current_line}")
            current_line += 1
            
        file_content = "\n".join(content_lines)
        
        prompt = t["prompt"].format(target_line=target_line, instruction=inst, target_name=target_name)
        
        # Format the excerpt the way pipeline does
        excerpt = f"--- EXCERPT (Lines {start_line} to {current_line}) ---\n" + file_content + "\n--- END EXCERPT ---"
        
        task_context = f"\n# Existing File: src/test_file.py\n```\n{excerpt}\n```\n"
        
        # Ground truth
        target_block = t["target"].format(id=target_idx, instruction=inst, target_name=target_name)
        replace_block = t["replace"].format(id=target_idx, instruction=inst, target_name=target_name)
        
        output = f"""<<THINKING>>
Found the target at the specified location. Modifying {target_name} or line {target_line}.
<<FILES>>
```python
# filepath: src/test_file.py
# action: MODIFY
<<<<<<<
{target_block}
=======
{replace_block}
>>>>>>>
```"""

        # Using the standard message format for the dataset
        messages = [
            {"role": "system", "content": "You are Nova, an autonomous coding agent. You follow instructions perfectly."},
            {"role": "user", "content": task_context + "\n" + prompt},
            {"role": "assistant", "content": output}
        ]
        
        dataset.append({"messages": messages})
        
    return dataset

dataset = generate_distractor_dataset()
with open("dataset_distractor.jsonl", "w") as f:
    for d in dataset:
        f.write(json.dumps(d) + "\n")
        
print(f"Generated {len(dataset)} distractor examples.")
