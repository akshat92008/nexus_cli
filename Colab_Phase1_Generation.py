"""
Colab Phase 1: Dataset Generation (No API Keys)

Instructions for Google Colab:
1. Go to https://colab.research.google.com/
2. Create a new Notebook.
3. Go to Runtime > Change runtime type > Select "T4 GPU".
4. Upload your local `reasoning_problems.py` to the Colab files sidebar.
5. Create a new code cell, paste the code below, and run it.

This script will download Qwen-2.5-7B-Instruct into the 16GB GPU in 4-bit mode,
and use it to generate the 3,000 reasoning problems entirely for free.
"""

# ==============================================================================
# PASTE THIS ENTIRE BLOCK INTO A COLAB CELL
# ==============================================================================

# 1. Install required libraries
import os
os.system("pip install -q transformers bitsandbytes accelerate")

import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm

# Import your problem generator
try:
    from reasoning_problems import generate_all_problems
except ImportError:
    print("❌ ERROR: Please upload 'reasoning_problems.py' to Colab first!")
    import sys; sys.exit(1)

# Configuration
TEACHER_MODEL = "Qwen/Qwen2.5-7B-Instruct"
OUTPUT_FILE = "dataset_nova_custom.jsonl"
NUM_PROBLEMS = 3000

print(f"🚀 Initializing Teacher Model: {TEACHER_MODEL}")
print("Loading in 4-bit to fit perfectly inside the free T4 GPU...")

# Load Tokenizer
tokenizer = AutoTokenizer.from_pretrained(TEACHER_MODEL)

# Load Model in 4-bit precision
model = AutoModelForCausalLM.from_pretrained(
    TEACHER_MODEL,
    device_map="auto",
    load_in_4bit=True,
    torch_dtype=torch.float16,
)

print("✅ Model loaded into GPU memory!")

# Teacher Prompt (Forces deep chain of thought)
TEACHER_SYSTEM_PROMPT = """
You are an elite, world-class Senior Software Engineer.
You must solve the problem using the exact format below. Do not use markdown blocks around the output.

<<THINKING>>
Write 300+ words of deep chain-of-thought architectural reasoning.
Debate different approaches, anticipate bugs, and explain your choices.
<</THINKING>>

<<FILES>>
[
  {
    "path": "filename.py",
    "content": "perfect, production-ready code"
  }
]
<</FILES>>
"""

# Generate Problems
print("🧠 Generating problem bank permutations...")
needed_parametric = max(0, NUM_PROBLEMS - 140)
per_category = max(60, (needed_parametric // 15) + 5)
all_problems = generate_all_problems(parametric_per_category=per_category)
if NUM_PROBLEMS < len(all_problems):
    all_problems = all_problems[:NUM_PROBLEMS]

print(f"📋 Starting generation loop for {len(all_problems)} problems...")

with open(OUTPUT_FILE, "a") as f:
    for i, prob_dict in enumerate(tqdm(all_problems)):
        problem_text = prob_dict["prompt"]
        
        messages = [
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {"role": "user", "content": problem_text}
        ]
        
        # Format for Qwen
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer([text], return_tensors="pt").to("cuda")
        
        # Generate (This takes time, but it's 100% free!)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=4096,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        
        response_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[-1]:], skip_special_tokens=True)
        
        # Save to JSONL
        entry = {
            "messages": [
                {"role": "user", "content": problem_text},
                {"role": "assistant", "content": response_text}
            ],
            "metadata": prob_dict.get("metadata", {})
        }
        f.write(json.dumps(entry) + "\n")
        f.flush()

print(f"\n🎉 DONE! Generated {len(all_problems)} examples.")
print(f"📥 Download '{OUTPUT_FILE}' from the Colab sidebar to your Mac!")
