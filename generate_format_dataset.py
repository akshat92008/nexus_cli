import json
import random

def generate_format_dataset(num_examples=20):
    dataset = []
    
    for i in range(num_examples):
        start_line = random.randint(10, 100)
        end_line = start_line + 40
        
        target_block = f"""def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total"""

        replace_block = f"""def calculate_total(items):
    total = 0
    for item in items:
        # Include tax
        total += item.price * 1.2
    return total"""
        
        noise_before = "\n".join([f"# noise {j}" for j in range(start_line, start_line + 15)])
        noise_after = "\n".join([f"# noise {j}" for j in range(start_line + 22, end_line)])
        
        excerpt = f"--- EXCERPT (Lines {start_line} to {end_line}) ---\n" + noise_before + "\n" + target_block + "\n" + noise_after + "\n--- END EXCERPT ---"
        
        task_context = f"\n# Existing File: src/calc.py\n```\n{excerpt}\n```\n"
        prompt = "URGENT: calculate_total is missing tax calculation. add a 20% tax to the item price."
        
        # Ground truth MUST NOT include excerpt headers
        output = f"""<<THINKING>>
Adding tax calculation to calculate_total. I must use the exact search block without any excerpt markers.
<<FILES>>
```python
# filepath: src/calc.py
# action: MODIFY
<<<<<<<
{target_block}
=======
{replace_block}
>>>>>>>
```"""

        messages = [
            {"role": "system", "content": "You are Nova, an autonomous coding agent. You follow instructions perfectly."},
            {"role": "user", "content": task_context + "\n" + prompt},
            {"role": "assistant", "content": output}
        ]
        
        dataset.append({"messages": messages})
        
    return dataset

dataset = generate_format_dataset()
with open("dataset_format.jsonl", "w") as f:
    for d in dataset:
        f.write(json.dumps(d) + "\n")
        
print(f"Generated {len(dataset)} format examples.")
