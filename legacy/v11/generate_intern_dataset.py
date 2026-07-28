#!/usr/bin/env python3
"""
generate_intern_dataset.py — Intern-Persona Distillation for Nova 1.5B (V3)

Generates training data specifically for the "Junior Intern" (Execution) persona.
This version uses standard Markdown output from the LLM and parses it into strict JSON,
preventing JSONDecodeErrors and ensuring 100% clean data.

Usage:
  python generate_intern_dataset.py --count 1000
"""

import json
import os
import sys
import time
import argparse
import re
from typing import Optional, Tuple

from intern_problems import generate_intern_problems

# ═══════════════════════════════════════════════════════════════════════════════
# THE INTERN PROMPT — Uses Markdown, avoids strict JSON generation
# ═══════════════════════════════════════════════════════════════════════════════

INTERN_SYSTEM_PROMPT = """You are Nova, an elite, hyper-fast "Junior Intern" coding engine developed by Amuara Labs.
You are given highly specific, narrow coding tasks (e.g. single functions, bug fixes). Your ONLY job is to execute them perfectly.

You must solve the problem using the exact format below. 

<<THINKING>>
Write a very brief internal monologue (less than 50 words). State exactly what file you are modifying and what syntax you will use. Do not debate architecture.

<<FILES>>
Provide the code in standard markdown code blocks. The very first two lines of the code block MUST be comments specifying the filepath and action.
Example:
```python
# filepath: src/utils.py
# action: CREATE

def my_func():
    return True
```

<<TEST_COMMAND>>
pytest test_file.py"""

# ═══════════════════════════════════════════════════════════════════════════════
# Core Logic
# ═══════════════════════════════════════════════════════════════════════════════

class TokenUsage:
    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.requests = 0
        self.failed = 0

    def add(self, i: int, o: int):
        self.total_input += i
        self.total_output += o
        self.requests += 1

    def summary(self) -> str:
        return f"Requests: {self.requests} (failed: {self.failed}) | Tokens: {self.total_input:,} in + {self.total_output:,} out"

def call_nvidia(model: str, problem: str, temperature: float, max_tokens: int) -> Tuple[Optional[str], int, int]:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ.get("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1",
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": INTERN_SYSTEM_PROMPT},
            {"role": "user", "content": problem},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content
    usage = response.usage
    return text, usage.prompt_tokens, usage.completion_tokens

def parse_markdown_to_json(response_text: str) -> Tuple[bool, str, Optional[str]]:
    """
    Extracts the blocks and reformats the <<FILES>> block into a strict JSON string array,
    so that the final saved JSONL entry mimics the original expected format.
    """
    if "<<THINKING>>" not in response_text or "<<FILES>>" not in response_text or "<<TEST_COMMAND>>" not in response_text:
        return False, "Missing required blocks", None

    # Extract the parts
    try:
        thinking_part = response_text.split("<<THINKING>>")[1].split("<<FILES>>")[0].strip()
        files_part = response_text.split("<<FILES>>")[1].split("<<TEST_COMMAND>>")[0].strip()
        test_part = response_text.split("<<TEST_COMMAND>>")[1].strip()
    except IndexError:
        return False, "Malformed block delimiters", None

    # Parse the markdown code blocks
    pattern = re.compile(r'```(?:python|java|rust|js|ts|go|cpp|c)?\n(.*?)```', re.DOTALL)
    blocks = pattern.findall(files_part)
    
    if not blocks:
        return False, "No markdown code blocks found in <<FILES>>", None

    json_files = []
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 3:
            continue
            
        # Parse filepath and action from comments
        filepath_match = re.match(r'^#\s*filepath:\s*(.+)$', lines[0].strip())
        action_match = re.match(r'^#\s*action:\s*(.+)$', lines[1].strip())
        
        if not filepath_match or not action_match:
            return False, "Missing # filepath: or # action: in code block", None
            
        path = filepath_match.group(1).strip()
        action = action_match.group(1).strip()
        
        # The rest is content
        content = '\n'.join(lines[2:]).lstrip()
        
        json_files.append({
            "path": path,
            "action": action,
            "content": content
        })

    # Reconstruct the expected strict response format
    files_json_str = json.dumps(json_files, indent=2)
    
    final_response = f"<<THINKING>>\n{thinking_part}\n\n<<FILES>>\n{files_json_str}\n\n<<TEST_COMMAND>>\n{test_part}"
    
    return True, "OK", final_response

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--output", type=str, default="dataset_nova_intern_v3.jsonl")
    args = parser.parse_args()

    if not os.environ.get("NVIDIA_API_KEY"):
        print("❌ Set NVIDIA_API_KEY environment variable.")
        sys.exit(1)

    print(f"🧠 Generating {args.count} narrow-scope problems...")
    all_problems = generate_intern_problems(args.count * 3, seed=42)
    
    usage = TokenUsage()
    generated = 0
    problem_idx = 0

    while generated < args.count and problem_idx < len(all_problems):
        p = all_problems[problem_idx]
        problem_idx += 1
        
        print(f"[{generated+1}/{args.count}] {p['problem'][:80]}...")
        try:
            resp, in_t, out_t = call_nvidia("meta/llama-3.1-70b-instruct", p['problem'], 0.3, 1000)
            usage.add(in_t, out_t)
            
            is_valid, reason, reconstructed_resp = parse_markdown_to_json(resp)
            if not is_valid:
                print(f"   ⚠️ Validation failed: {reason}")
                usage.failed += 1
                continue

            entry = {
                "messages": [
                    {"role": "user", "content": p['problem']},
                    {"role": "assistant", "content": reconstructed_resp}
                ],
                "metadata": {"category": p["category"], "model": "llama-3.1-70b-instruct"}
            }

            with open(args.output, "a") as f:
                f.write(json.dumps(entry) + "\n")
            
            generated += 1
            print(f"   ✅ Generated ({out_t} tokens)")
            time.sleep(1)
        except Exception as e:
            print(f"   ❌ API Error: {e}")
            usage.failed += 1
            time.sleep(2)

    print(f"\\n✅ Done. Generated {generated}/{args.count}. {usage.summary()}")

if __name__ == "__main__":
    main()
