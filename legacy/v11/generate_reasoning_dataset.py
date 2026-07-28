#!/usr/bin/env python3
"""
generate_reasoning_dataset.py — Frontier Model Reasoning Distillation for Nova 1.5B

Calls a frontier model API (OpenAI GPT-4o, Anthropic Claude 3.5 Sonnet, or DeepSeek V3)
to generate deep chain-of-thought training data for Nova 1.5B.

The frontier model is forced to produce 500+ word self-debating <<THINKING>> blocks
with architecture debates, edge-case anticipation, and bug prevention.

Features:
  - Multi-provider support (OpenAI, Anthropic, DeepSeek)
  - Checkpoint/resume (safe to interrupt and restart)
  - Response validation (rejects shallow thinking)
  - Cost tracking (logs token usage)
  - Rate limiting with exponential backoff

Usage:
  # Set your API key
  export OPENAI_API_KEY="sk-..."      # for OpenAI
  export ANTHROPIC_API_KEY="sk-..."   # for Anthropic
  export DEEPSEEK_API_KEY="sk-..."    # for DeepSeek

  # Generate 5 test examples
  python generate_reasoning_dataset.py --provider openai --count 5

  # Generate full dataset (1000+ examples)
  python generate_reasoning_dataset.py --provider deepseek --count 1000

  # Resume from checkpoint
  python generate_reasoning_dataset.py --provider openai --count 1000 --resume
"""

import json
import os
import sys
import time
import hashlib
import argparse
import traceback
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# Import the problem bank
from reasoning_problems import generate_all_problems


# ═══════════════════════════════════════════════════════════════════════════════
# THE TEACHER PROMPT — Forces deep reasoning from the frontier model
# ═══════════════════════════════════════════════════════════════════════════════

TEACHER_SYSTEM_PROMPT = """You are an elite, world-class Senior Software Engineer with 20+ years of experience at companies like Google, Meta, and Stripe. I am going to give you a complex software problem.

You must solve the problem using the exact format below. Do not output markdown code blocks around the final output. You must strictly use the following blocks:

<<THINKING>>
You must write a highly detailed, stream-of-consciousness internal monologue (minimum 500 words). This is the most important part. You MUST:

1. BREAK DOWN the problem into logical sub-problems. Identify what data structures, algorithms, and patterns are needed.

2. DEBATE at least two different approaches. For example:
   - "I could use approach A (hash map with chaining) which gives O(1) average lookup but O(n) worst case, OR approach B (balanced BST) which guarantees O(log n) worst case. For this problem, approach A is better because..."
   - "Should I use async/await or threading here? Let me think about the tradeoffs..."

3. JUSTIFY your choice with specific technical reasoning. Mention time complexity, space complexity, memory limits, or edge cases that make one approach superior.

4. ANTICIPATE potential bugs before writing code:
   - "Wait, I need to be careful about [specific edge case]. If I don't handle this, the code will [specific failure mode]."
   - "There's a subtle bug risk here with [specific issue] — I'll prevent it by [specific technique]."

5. Think through EDGE CASES explicitly:
   - Empty inputs, single-element inputs, maximum-size inputs
   - Concurrency issues if applicable
   - Error handling and recovery
   - Unicode, encoding, or serialization edge cases

Your thinking must read like a brilliant engineer talking to themselves while pacing the room. Use phrases like "Hmm, wait...", "Actually, let me reconsider...", "The tricky part here is...", "I almost forgot about...", etc.

Do NOT write a shallow summary. Do NOT just list the steps. THINK deeply and show your reasoning process.

<<FILES>>
[
  {
    "path": "path/to/file.ext",
    "action": "CREATE",
    "content": "complete_working_code_here"
  }
]

The FILES block must contain valid JSON. The code must be complete, working, and production-quality:
- Proper error handling
- Type hints (for Python/TypeScript)
- Docstrings and comments for complex logic
- No placeholder comments like "implement this" or "TODO"

<<TEST_COMMAND>>
The exact command to run to verify the solution works (e.g., "python -m pytest test_file.py -v")"""


# ═══════════════════════════════════════════════════════════════════════════════
# API Provider Abstraction
# ═══════════════════════════════════════════════════════════════════════════════

class TokenUsage:
    """Track API token usage and cost."""
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.failed_requests = 0

    def add(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_requests += 1

    def add_failure(self):
        self.failed_requests += 1

    def estimate_cost(self, provider: str) -> float:
        """Estimate cost in USD based on provider pricing (approx mid-2025)."""
        pricing = {
            "openai":    {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},  # gpt-4o
            "anthropic": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},  # claude-3.5-sonnet
            "deepseek":  {"input": 0.14 / 1_000_000, "output": 0.28 / 1_000_000},   # deepseek-chat
            "nvidia":    {"input": 1.00 / 1_000_000, "output": 1.00 / 1_000_000},   # nim default
        }
        p = pricing.get(provider, pricing["openai"])
        return self.total_input_tokens * p["input"] + self.total_output_tokens * p["output"]

    def summary(self, provider: str) -> str:
        cost = self.estimate_cost(provider)
        return (
            f"Requests: {self.total_requests} (failed: {self.failed_requests}) | "
            f"Tokens: {self.total_input_tokens:,} in + {self.total_output_tokens:,} out | "
            f"Est. cost: ${cost:.2f}"
        )


def call_frontier_model(
    provider: str,
    model: str,
    problem: str,
    temperature: float = 0.7,
    max_tokens: int = 8192,
) -> Tuple[Optional[str], int, int]:
    """
    Call the frontier model API.
    Returns (response_text, input_tokens, output_tokens) or (None, 0, 0) on failure.
    """
    if provider == "openai":
        return _call_openai(model, problem, temperature, max_tokens)
    elif provider == "anthropic":
        return _call_anthropic(model, problem, temperature, max_tokens)
    elif provider == "deepseek":
        return _call_deepseek(model, problem, temperature, max_tokens)
    elif provider == "nvidia":
        return _call_nvidia(model, problem, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def _call_openai(model: str, problem: str, temperature: float, max_tokens: int) -> Tuple[Optional[str], int, int]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {"role": "user", "content": problem},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content
    usage = response.usage
    return text, usage.prompt_tokens, usage.completion_tokens


def _call_anthropic(model: str, problem: str, temperature: float, max_tokens: int) -> Tuple[Optional[str], int, int]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=TEACHER_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": problem},
        ],
        temperature=temperature,
    )
    text = response.content[0].text
    return text, response.usage.input_tokens, response.usage.output_tokens


def _call_deepseek(model: str, problem: str, temperature: float, max_tokens: int) -> Tuple[Optional[str], int, int]:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {"role": "user", "content": problem},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content
    usage = response.usage
    return text, usage.prompt_tokens, usage.completion_tokens


def _call_nvidia(model: str, problem: str, temperature: float, max_tokens: int) -> Tuple[Optional[str], int, int]:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ.get("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1",
    )
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {"role": "user", "content": problem},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content
    usage = response.usage
    return text, usage.prompt_tokens, usage.completion_tokens


# ═══════════════════════════════════════════════════════════════════════════════
# Response Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_response(response_text: str, min_thinking_words: int = 200) -> Tuple[bool, str]:
    """
    Validate that the frontier model's response has proper structure.
    Returns (is_valid, reason).
    """
    if not response_text:
        return False, "Empty response"

    # Check for required blocks
    if "<<THINKING>>" not in response_text:
        return False, "Missing <<THINKING>> block"
    if "<<FILES>>" not in response_text:
        return False, "Missing <<FILES>> block"
    if "<<TEST_COMMAND>>" not in response_text:
        return False, "Missing <<TEST_COMMAND>> block"

    # Extract and validate thinking block
    try:
        thinking_start = response_text.index("<<THINKING>>") + len("<<THINKING>>")
        thinking_end = response_text.index("<<FILES>>")
        thinking_text = response_text[thinking_start:thinking_end].strip()
        
        word_count = len(thinking_text.split())
        if word_count < min_thinking_words:
            return False, f"Thinking block too short ({word_count} words, need {min_thinking_words}+)"
    except ValueError:
        return False, "Could not parse THINKING block boundaries"

    # Extract and validate FILES block
    try:
        files_start = response_text.index("<<FILES>>") + len("<<FILES>>")
        files_end = response_text.index("<<TEST_COMMAND>>")
        files_text = files_text = response_text[files_start:files_end].strip()
        
        # Try to parse as JSON
        files_json = json.loads(files_text)
        if not isinstance(files_json, list) or len(files_json) == 0:
            return False, "FILES block is not a non-empty JSON array"
        
        for f in files_json:
            if "path" not in f or "content" not in f:
                return False, "FILES entries missing 'path' or 'content'"
    except (ValueError, json.JSONDecodeError) as e:
        return False, f"FILES block is not valid JSON: {str(e)[:100]}"

    return True, "OK"


# ═══════════════════════════════════════════════════════════════════════════════
# Checkpoint Management
# ═══════════════════════════════════════════════════════════════════════════════

def load_checkpoint(checkpoint_path: str) -> set:
    """Load the set of already-generated problem hashes."""
    done = set()
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    done.add(line)
    return done


def save_checkpoint(checkpoint_path: str, problem_hash: str):
    """Append a completed problem hash to the checkpoint file."""
    with open(checkpoint_path, "a") as f:
        f.write(problem_hash + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Main Generation Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "deepseek": "deepseek-chat",
    "nvidia": "minimaxai/minimax-m3",
}


def generate_reasoning_dataset(
    provider: str,
    model: Optional[str],
    output_file: str,
    count: int,
    resume: bool,
    temperature: float,
    max_retries: int,
    delay: float,
    min_thinking_words: int,
    seed: int,
):
    """Main generation pipeline."""
    
    # Resolve model
    if model is None:
        model = DEFAULT_MODELS.get(provider, "gpt-4o")
    
    # Check API key
    key_env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "nvidia": "NVIDIA_API_KEY",
    }
    key_env = key_env_map.get(provider, "OPENAI_API_KEY")
    if not os.environ.get(key_env):
        print(f"❌ ERROR: Set your API key: export {key_env}=\"your-key-here\"")
        sys.exit(1)

    # Generate problems
    print(f"🧠 Generating problem bank (seed={seed})...")
    
    # Calculate how many parametric problems per category we need to hit the requested count
    # 15 domains. ~140 fixed problems (killer + multi-lang)
    needed_parametric = max(0, count - 140)
    per_category = max(60, (needed_parametric // 15) + 5) # +5 for buffer
    
    all_problems = generate_all_problems(parametric_per_category=per_category, seed=seed)
    
    if count < len(all_problems):
        all_problems = all_problems[:count]
    
    print(f"📋 Selected {len(all_problems)} problems for distillation")
    print(f"🤖 Provider: {provider} | Model: {model} | Temperature: {temperature}")
    print(f"📁 Output: {output_file}")
    print()

    # Checkpoint setup
    checkpoint_path = output_file + ".checkpoint"
    completed_hashes = set()
    if resume:
        completed_hashes = load_checkpoint(checkpoint_path)
        print(f"♻️  Resuming: {len(completed_hashes)} already completed")

    # Token tracking
    usage = TokenUsage()

    # Stats
    generated = 0
    skipped = 0
    failed = 0

    for i, problem_entry in enumerate(all_problems):
        problem_text = problem_entry["problem"]
        problem_hash = problem_entry["hash"]
        category = problem_entry["category"]

        # Skip if already done
        if problem_hash in completed_hashes:
            skipped += 1
            continue

        # Progress
        progress = f"[{i+1}/{len(all_problems)}]"
        print(f"{progress} [{category}] {problem_text[:80]}...")

        # Retry loop
        success = False
        for attempt in range(max_retries):
            try:
                response_text, in_tokens, out_tokens = call_frontier_model(
                    provider=provider,
                    model=model,
                    problem=problem_text,
                    temperature=temperature,
                )
                usage.add(in_tokens, out_tokens)

                # Validate
                is_valid, reason = validate_response(response_text, min_thinking_words)
                if not is_valid:
                    print(f"   ⚠️  Validation failed (attempt {attempt+1}): {reason}")
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))
                        continue
                    else:
                        print(f"   ❌ Giving up after {max_retries} attempts")
                        usage.add_failure()
                        failed += 1
                        break

                # Format into ChatML JSONL
                jsonl_entry = {
                    "messages": [
                        {"role": "user", "content": problem_text},
                        {"role": "assistant", "content": response_text},
                    ],
                    "metadata": {
                        "category": category,
                        "hash": problem_hash,
                        "provider": provider,
                        "model": model,
                        "input_tokens": in_tokens,
                        "output_tokens": out_tokens,
                    }
                }

                # Write to output
                with open(output_file, "a") as f:
                    f.write(json.dumps(jsonl_entry) + "\n")

                # Save checkpoint
                save_checkpoint(checkpoint_path, problem_hash)
                completed_hashes.add(problem_hash)

                generated += 1
                thinking_words = len(response_text.split("<<FILES>>")[0].split()) if "<<FILES>>" in response_text else 0
                print(f"   ✅ Generated ({thinking_words} thinking words, {out_tokens} tokens)")
                success = True
                break

            except KeyboardInterrupt:
                print(f"\n\n🛑 Interrupted! {generated} examples saved to {output_file}")
                print(f"   Run with --resume to continue from checkpoint")
                print(f"   {usage.summary(provider)}")
                sys.exit(0)

            except Exception as e:
                print(f"   ⚠️  Error (attempt {attempt+1}): {str(e)[:120]}")
                usage.add_failure()
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)
                    print(f"   ⏳ Retrying in {wait_time:.0f}s...")
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ Giving up after {max_retries} attempts")
                    failed += 1

        # Rate limiting between requests
        if success:
            time.sleep(delay)

    # Final report
    print()
    print("=" * 70)
    print(f" GENERATION COMPLETE")
    print("=" * 70)
    print(f"  ✅ Generated: {generated}")
    print(f"  ♻️  Skipped (checkpoint): {skipped}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📊 {usage.summary(provider)}")
    print(f"  📁 Output: {output_file}")
    print()
    
    if generated > 0:
        print(f"  🚀 Next step: Validate with:")
        print(f"     python validate_dataset.py --input {output_file}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Generate reasoning-distilled training data for Nova 1.5B",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with 5 examples using OpenAI
  python generate_reasoning_dataset.py --provider openai --count 5

  # Full generation with DeepSeek (cheapest)
  python generate_reasoning_dataset.py --provider deepseek --count 1000

  # Resume interrupted generation
  python generate_reasoning_dataset.py --provider openai --count 1000 --resume

  # Use a specific model
  python generate_reasoning_dataset.py --provider openai --model gpt-4o-2024-08-06 --count 500
        """,
    )
    
    parser.add_argument(
        "--provider", type=str, required=True,
        choices=["openai", "anthropic", "deepseek", "nvidia"],
        help="API provider to use",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Specific model name (default: provider's best model)",
    )
    parser.add_argument(
        "--output", type=str, default="dataset_nova_v3_cot.jsonl",
        help="Output JSONL file path (default: dataset_nova_v3_cot.jsonl)",
    )
    parser.add_argument(
        "--count", type=int, default=1000,
        help="Number of problems to generate (default: 1000)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from checkpoint (skip already-generated problems)",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.7,
        help="Sampling temperature (default: 0.7)",
    )
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="Max retries per problem on failure (default: 3)",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Delay between API calls in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--min-thinking-words", type=int, default=200,
        help="Minimum words in <<THINKING>> block to accept (default: 200)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for problem generation (default: 42)",
    )

    args = parser.parse_args()

    generate_reasoning_dataset(
        provider=args.provider,
        model=args.model,
        output_file=args.output,
        count=args.count,
        resume=args.resume,
        temperature=args.temperature,
        max_retries=args.max_retries,
        delay=args.delay,
        min_thinking_words=args.min_thinking_words,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
