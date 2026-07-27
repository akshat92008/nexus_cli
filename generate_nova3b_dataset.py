#!/usr/bin/env python3
"""
generate_nova3b_dataset.py — Unified Dataset Generator for Nova 3B (Amaura)

Generates a large-scale, diverse training dataset for fine-tuning the Nova 3B
"Intern" model. Supports two generation paths:

  1. FREE COLAB PATH: Uses Qwen2.5-7B-Instruct as teacher (4-bit on T4 GPU)
  2. API PATH: Uses OpenAI/Anthropic/DeepSeek (paid, higher quality)

The dataset combines:
  - Existing MBPP-verified examples (dataset_nova_intern_v5.jsonl)
  - Parametrically generated new examples across 7 task categories
  - Format adversarial examples (messy prompts → clean output)
  - Boundary/refusal examples (out-of-scope requests)

Output: ChatML JSONL format compatible with Unsloth/TRL fine-tuning.

Usage:
  # On Google Colab (free T4 GPU):
  python generate_nova3b_dataset.py --mode colab --count 3000

  # Local with API:
  python generate_nova3b_dataset.py --mode api --provider deepseek --count 1000

  # Dry run (generate prompts only, no LLM calls):
  python generate_nova3b_dataset.py --mode dry-run --count 100

Part of the Nova model family by Amaura.
"""

import json
import os
import sys
import time
import random
import hashlib
import argparse
from typing import Optional, Tuple, Dict, List, Any
from pathlib import Path

from dataset_categories import (
    CATEGORIES, VARIABLE_BANK, fill_template,
    get_weighted_category, generate_task, TaskCategory,
)


# ═══════════════════════════════════════════════════════════════════════════════
# System Prompts — What we train the model to BE
# ═══════════════════════════════════════════════════════════════════════════════

NOVA_SYSTEM_PROMPT = """You are Nova, an elite coding execution engine developed by Amaura.
You receive specific, narrow coding tasks and execute them with surgical precision.

You MUST respond using this EXACT format — no exceptions:

<<THINKING>>
Brief internal monologue (1-3 sentences). State what you will do.

<<FILES>>
```<language>
# filepath: path/to/file.ext
# action: CREATE | MODIFY

[your code here]
```

<<TEST_COMMAND>>
[exact shell command to verify]"""


TEACHER_SYSTEM_PROMPT = """You are a world-class Senior Software Engineer. You must generate training data for a small, fast coding model called Nova.

Nova uses this EXACT output format. You MUST follow it precisely:

<<THINKING>>
Write 1-3 brief sentences stating what you will implement. Be terse. No architecture debates. Just state your intent.

<<FILES>>
Provide your code in a SINGLE markdown code block. The first two lines of the block MUST be comments specifying filepath and action:
```python
# filepath: src/solution.py
# action: CREATE

def actual_code_here():
    pass
```

<<TEST_COMMAND>>
pytest test_solution.py

CRITICAL RULES:
1. The <<THINKING>> block must be BRIEF (under 50 words). Nova is an executor, not an architect.
2. The code must be CORRECT, COMPLETE, and RUNNABLE — no placeholders, no "TODO" comments.
3. Include proper error handling and edge case coverage.
4. The test command must be a real, executable command.
5. Do NOT wrap the entire output in markdown. The blocks ARE the format.
6. For Python: always include type hints and docstrings.
7. DO NOT add any text outside of the three blocks."""


BOUNDARY_RESPONSE_TEMPLATE = """<<THINKING>>
This request requires complex architectural planning beyond my scope as an execution engine. I will provide a minimal starting point instead.

<<FILES>>
```python
# filepath: src/main.py
# action: CREATE

# NOTE: This task requires architectural planning.
# Please break it down into specific, atomic sub-tasks.
# For example:
#   1. "Create the User model in src/models.py"
#   2. "Add the /api/users endpoint in src/routes.py"
#   3. "Write tests for the User model in tests/test_models.py"
#
# I work best with specific, narrow tasks.

def main():
    \"\"\"Entry point — implement after decomposing the architecture.\"\"\"
    raise NotImplementedError("Break this into smaller tasks for Nova to execute.")

if __name__ == "__main__":
    main()
```

<<TEST_COMMAND>>
python -c "print('Task needs decomposition — see comments in src/main.py')"
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Response Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_response(response: str, category: str = "") -> Tuple[bool, str]:
    """Validate that a generated response follows the Nova protocol."""
    
    if not response or not response.strip():
        return False, "Empty response"
    
    # Check all three blocks exist
    if "<<THINKING>>" not in response:
        return False, "Missing <<THINKING>> block"
    if "<<FILES>>" not in response:
        return False, "Missing <<FILES>> block"
    if "<<TEST_COMMAND>>" not in response:
        return False, "Missing <<TEST_COMMAND>> block"
    
    # Check block order
    t_pos = response.find("<<THINKING>>")
    f_pos = response.find("<<FILES>>")
    tc_pos = response.find("<<TEST_COMMAND>>")
    
    if not (t_pos < f_pos < tc_pos):
        return False, "Blocks out of order"
    
    # Extract thinking and check brevity
    thinking = response[t_pos + len("<<THINKING>>"):f_pos].strip()
    if len(thinking.split()) > 100:
        return False, f"Thinking too verbose ({len(thinking.split())} words)"
    if len(thinking.split()) < 3:
        return False, "Thinking too short"
    
    # Check for code block in FILES
    files_section = response[f_pos + len("<<FILES>>"):tc_pos].strip()
    if "```" not in files_section:
        return False, "No code block in <<FILES>>"
    
    # Check for filepath comment
    if "# filepath:" not in files_section.lower():
        return False, "Missing # filepath: comment in code block"
    
    # Check test command exists
    test_cmd = response[tc_pos + len("<<TEST_COMMAND>>"):].strip()
    if len(test_cmd) < 3:
        return False, "Test command too short"
    
    return True, "OK"


# ═══════════════════════════════════════════════════════════════════════════════
# Generation Backends
# ═══════════════════════════════════════════════════════════════════════════════

class ColabGenerator:
    """Free generation path using Qwen 7B on Google Colab T4 GPU."""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self):
        """Load the teacher model. Call this once at the start."""
        if self._loaded:
            return
        
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        model_name = "Qwen/Qwen2.5-7B-Instruct"
        print(f"🚀 Loading teacher model: {model_name}")
        print("   Loading in 4-bit to fit inside free T4 GPU...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map="auto",
            quantization_config=quantization_config,
            torch_dtype=torch.float16,
        )
        self._loaded = True
        print("✅ Teacher model loaded!")

    def generate(self, prompt: str, category: str = "") -> Tuple[Optional[str], int, int]:
        """Generate a single response using the local teacher model."""
        import torch
        
        if not self._loaded:
            self.load()
        
        messages = [
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to("cuda")
        input_len = inputs.input_ids.shape[-1]
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=2048,
                temperature=0.4,
                do_sample=True,
                top_p=0.9,
                pad_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.1,
            )
        
        response = self.tokenizer.decode(
            outputs[0][input_len:], skip_special_tokens=True
        )
        
        output_len = outputs[0].shape[0] - input_len
        return response, input_len, output_len


class APIGenerator:
    """API-based generation using OpenAI/Anthropic/DeepSeek."""
    
    def __init__(self, provider: str = "deepseek"):
        self.provider = provider
        self.client = None
        self._init_client()
    
    def _init_client(self):
        if self.provider == "deepseek":
            from openai import OpenAI
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise ValueError("Set DEEPSEEK_API_KEY environment variable")
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )
            self.model_name = "deepseek-chat"
        
        elif self.provider == "openai":
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("Set OPENAI_API_KEY environment variable")
            self.client = OpenAI(api_key=api_key)
            self.model_name = "gpt-4o-mini"
        
        elif self.provider == "nvidia":
            from openai import OpenAI
            api_key = os.environ.get("NVIDIA_API_KEY")
            if not api_key:
                raise ValueError("Set NVIDIA_API_KEY environment variable")
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://integrate.api.nvidia.com/v1",
            )
            self.model_name = "meta/llama-3.1-70b-instruct"
        
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def generate(self, prompt: str, category: str = "") -> Tuple[Optional[str], int, int]:
        """Generate a single response via API."""
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=2048,
        )
        text = response.choices[0].message.content
        usage = response.usage
        return text, usage.prompt_tokens, usage.completion_tokens


class DryRunGenerator:
    """No LLM calls — just generates the prompt and a stub response."""
    
    def generate(self, prompt: str, category: str = "") -> Tuple[Optional[str], int, int]:
        stub = (
            '<<THINKING>>\n'
            'I will implement the requested function in src/solution.py.\n\n'
            '<<FILES>>\n'
            '```python\n'
            '# filepath: src/solution.py\n'
            '# action: CREATE\n\n'
            'def stub():\n'
            '    """Stub generated in dry-run mode."""\n'
            '    pass\n'
            '```\n\n'
            '<<TEST_COMMAND>>\n'
            'pytest test_solution.py'
        )
        return stub, len(prompt.split()), len(stub.split())


# ═══════════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class DatasetPipeline:
    """Orchestrates the full dataset generation pipeline."""

    def __init__(
        self,
        generator,
        output_path: str = "dataset_nova3b_generated.jsonl",
        existing_dataset: str = "dataset_nova_intern_v5.jsonl",
        checkpoint_path: str = ".generation_checkpoint.json",
    ):
        self.generator = generator
        self.output_path = output_path
        self.existing_dataset = existing_dataset
        self.checkpoint_path = checkpoint_path
        self.stats = {
            "generated": 0,
            "failed": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_category": {},
        }
        self.seen_hashes = set()
    
    def _hash_prompt(self, prompt: str) -> str:
        return hashlib.md5(prompt.encode()).hexdigest()
    
    def _load_checkpoint(self) -> int:
        """Resume from checkpoint if it exists."""
        if os.path.exists(self.checkpoint_path):
            with open(self.checkpoint_path, "r") as f:
                data = json.load(f)
                self.stats = data.get("stats", self.stats)
                self.seen_hashes = set(data.get("seen_hashes", []))
                return data.get("generated", 0)
        return 0
    
    def _save_checkpoint(self):
        with open(self.checkpoint_path, "w") as f:
            json.dump({
                "generated": self.stats["generated"],
                "stats": self.stats,
                "seen_hashes": list(self.seen_hashes),
            }, f)
    
    def _load_existing(self) -> List[Dict]:
        """Load existing v5 dataset entries."""
        entries = []
        if os.path.exists(self.existing_dataset):
            with open(self.existing_dataset, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return entries
    
    def generate_prompts(self, count: int, seed: int = 42) -> List[Dict[str, Any]]:
        """Generate `count` diverse task prompts across all categories."""
        random.seed(seed)
        prompts = []
        
        for _ in range(count):
            task = generate_task()
            prompt_hash = self._hash_prompt(task["prompt"])
            
            # Skip duplicates
            if prompt_hash in self.seen_hashes:
                continue
            self.seen_hashes.add(prompt_hash)
            
            prompts.append(task)
        
        # Print distribution
        cat_counts = {}
        for p in prompts:
            cat_counts[p["category"]] = cat_counts.get(p["category"], 0) + 1
        
        print(f"\n📊 Prompt Distribution ({len(prompts)} total):")
        for cat, count in sorted(cat_counts.items()):
            print(f"   {cat}: {count} ({count/len(prompts)*100:.1f}%)")
        
        return prompts
    
    def run(self, target_count: int, resume: bool = False, seed: int = 42):
        """Execute the full generation pipeline."""
        
        print("=" * 70)
        print("  AMAURA — Nova 3B Dataset Generation Pipeline")
        print("=" * 70)
        
        # Resume or start fresh
        start_idx = 0
        if resume:
            start_idx = self._load_checkpoint()
            print(f"📂 Resuming from checkpoint: {start_idx} already generated")
        
        remaining = target_count - start_idx
        if remaining <= 0:
            print(f"✅ Already generated {start_idx}/{target_count}. Done!")
            return
        
        # Generate prompts
        prompts = self.generate_prompts(remaining + 200, seed=seed)  # Extra for failures
        
        print(f"\n🚀 Starting generation: {remaining} examples needed")
        print(f"   Output: {self.output_path}")
        print("-" * 70)
        
        generated = 0
        failed = 0
        
        for i, task in enumerate(prompts):
            if generated >= remaining:
                break
            
            prompt = task["prompt"]
            category = task["category"]
            
            # Special handling for boundary tasks
            if category == "boundary":
                response = BOUNDARY_RESPONSE_TEMPLATE
                in_tokens, out_tokens = 0, 0
            else:
                try:
                    response, in_tokens, out_tokens = self.generator.generate(
                        prompt, category
                    )
                except Exception as e:
                    print(f"   ❌ [{i+1}] Error: {e}")
                    failed += 1
                    time.sleep(2)
                    continue
            
            # Validate response
            is_valid, reason = validate_response(response, category)
            
            if not is_valid:
                print(f"   ⚠️  [{i+1}] Invalid: {reason}")
                failed += 1
                continue
            
            # Save entry
            entry = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": response},
                ],
                "metadata": {
                    "category": category,
                    "language": task.get("language", "python"),
                    "difficulty": task.get("difficulty", 0),
                    "source": "nova3b_generator",
                },
            }
            
            with open(self.output_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            
            generated += 1
            self.stats["generated"] += 1
            self.stats["total_input_tokens"] += in_tokens
            self.stats["total_output_tokens"] += out_tokens
            self.stats["by_category"][category] = \
                self.stats["by_category"].get(category, 0) + 1
            
            # Progress
            if generated % 10 == 0 or generated == 1:
                print(f"   ✅ [{generated}/{remaining}] {category}: {prompt[:60]}...")
                self._save_checkpoint()
            
            # Rate limiting for API calls
            if category != "boundary":
                time.sleep(0.5)
        
        # Final save
        self._save_checkpoint()
        
        print("\n" + "=" * 70)
        print(f"  ✅ DONE — Generated {generated} new examples")
        print(f"  ❌ Failed: {failed}")
        print(f"  📊 Tokens: {self.stats['total_input_tokens']:,} in / "
              f"{self.stats['total_output_tokens']:,} out")
        print(f"  📁 Output: {self.output_path}")
        print("=" * 70)
    
    def merge_with_existing(self, output_merged: str = "dataset_nova3b_combined.jsonl"):
        """Merge generated data with existing v5 dataset."""
        existing = self._load_existing()
        
        new_entries = []
        if os.path.exists(self.output_path):
            with open(self.output_path, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            new_entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        
        # Combine and shuffle
        combined = existing + new_entries
        random.shuffle(combined)
        
        with open(output_merged, "w") as f:
            for entry in combined:
                f.write(json.dumps(entry) + "\n")
        
        print(f"\n📦 Merged dataset: {len(combined)} total examples")
        print(f"   Existing: {len(existing)}")
        print(f"   New: {len(new_entries)}")
        print(f"   Output: {output_merged}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Amaura — Nova 3B Dataset Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate on Google Colab (free T4):
  python generate_nova3b_dataset.py --mode colab --count 3000

  # Generate via DeepSeek API:
  python generate_nova3b_dataset.py --mode api --provider deepseek --count 1000

  # Dry run (test prompts without LLM):
  python generate_nova3b_dataset.py --mode dry-run --count 100 --merge
        """,
    )
    parser.add_argument("--mode", choices=["colab", "api", "dry-run"],
                        default="dry-run", help="Generation mode")
    parser.add_argument("--provider", choices=["deepseek", "openai", "nvidia"],
                        default="deepseek", help="API provider (for --mode api)")
    parser.add_argument("--count", type=int, default=100,
                        help="Number of new examples to generate")
    parser.add_argument("--output", type=str, default="dataset_nova3b_generated.jsonl",
                        help="Output JSONL file")
    parser.add_argument("--existing", type=str, default="dataset_nova_intern_v5.jsonl",
                        help="Existing dataset to merge with")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from checkpoint")
    parser.add_argument("--merge", action="store_true",
                        help="Merge generated data with existing dataset after generation")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    
    args = parser.parse_args()
    
    # Select generator backend
    if args.mode == "colab":
        generator = ColabGenerator()
    elif args.mode == "api":
        generator = APIGenerator(args.provider)
    else:
        generator = DryRunGenerator()
    
    # Run pipeline
    pipeline = DatasetPipeline(
        generator=generator,
        output_path=args.output,
        existing_dataset=args.existing,
    )
    
    pipeline.run(args.count, resume=args.resume, seed=args.seed)
    
    # Optionally merge
    if args.merge:
        pipeline.merge_with_existing()


if __name__ == "__main__":
    main()
