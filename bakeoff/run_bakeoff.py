#!/usr/bin/env python3
"""
Nova v12 Foundation Bake-Off Runner

Evaluates candidate base models on standardised prompts across all
scoring dimensions. All candidates run on identical hardware with
identical parameters.

Usage:
    python run_bakeoff.py --all-candidates
    python run_bakeoff.py --candidate nanbeige4.2-3b-base
    python run_bakeoff.py --candidate phi-4-mini --category code_generation
"""

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BAKEOFF_DIR = Path(__file__).parent
PROMPTS_DIR = BAKEOFF_DIR / "prompts"
RESULTS_DIR = BAKEOFF_DIR / "results"
CANDIDATES_FILE = BAKEOFF_DIR / "candidates.yaml"

CATEGORIES = [
    "code_generation",
    "debugging",
    "repository_editing",
    "tool_use",
    "fim",
    "instruction_following",
]

DEFAULT_PARAMS = {
    "temperature": 0.0,
    "max_tokens": 2048,
    "top_p": 1.0,
    "seed": 42,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    """Result from a single prompt evaluation."""
    candidate_id: str
    category: str
    prompt_id: str
    prompt_text: str
    raw_output: str
    latency_seconds: float
    tokens_generated: int
    tokens_per_second: float
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CandidateConfig:
    """Configuration for a bake-off candidate."""
    id: str
    name: str
    hf_id: str
    params: str
    licence: str
    context_length: int
    architecture: str
    status: str


# ---------------------------------------------------------------------------
# Model loading backends
# ---------------------------------------------------------------------------

class OllamaBackend:
    """Run inference via Ollama REST API."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    def generate(self, prompt: str, params: dict) -> dict:
        """Generate a response and return output + metrics."""
        import urllib.request

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": params.get("temperature", 0.0),
                "num_predict": params.get("max_tokens", 2048),
                "top_p": params.get("top_p", 1.0),
                "seed": params.get("seed", 42),
            },
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
        elapsed = time.perf_counter() - start

        output = result.get("response", "")
        eval_count = result.get("eval_count", len(output.split()))
        eval_duration_ns = result.get("eval_duration", elapsed * 1e9)
        tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns > 0 else 0

        return {
            "output": output,
            "latency": elapsed,
            "tokens": eval_count,
            "tps": tps,
        }

    def is_available(self) -> bool:
        """Check if the model is available in Ollama."""
        import urllib.request
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                models = [m["name"] for m in data.get("models", [])]
                return any(self.model_name in m for m in models)
        except Exception:
            return False


class TransformersBackend:
    """Run inference via Hugging Face Transformers."""

    def __init__(self, model_id: str, trust_remote_code: bool = False):
        self.model_id = model_id
        self.trust_remote_code = trust_remote_code
        self.model = None
        self.tokenizer = None

    def _load(self):
        if self.model is not None:
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch
        except ImportError:
            raise RuntimeError(
                "transformers and torch are required. "
                "Install with: pip install transformers torch"
            )

        print(f"  Loading {self.model_id} via Transformers...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            trust_remote_code=self.trust_remote_code,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=self.trust_remote_code,
        )
        print(f"  Loaded {self.model_id}")

    def generate(self, prompt: str, params: dict) -> dict:
        import torch

        self._load()

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        input_len = inputs["input_ids"].shape[1]

        start = time.perf_counter()
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=params.get("max_tokens", 2048),
                temperature=max(params.get("temperature", 0.0), 1e-7),
                top_p=params.get("top_p", 1.0),
                do_sample=params.get("temperature", 0.0) > 0,
            )
        elapsed = time.perf_counter() - start

        new_tokens = outputs[0][input_len:]
        output = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        num_tokens = len(new_tokens)
        tps = num_tokens / elapsed if elapsed > 0 else 0

        return {
            "output": output,
            "latency": elapsed,
            "tokens": num_tokens,
            "tps": tps,
        }

    def is_available(self) -> bool:
        try:
            from transformers import AutoConfig
            AutoConfig.from_pretrained(
                self.model_id,
                trust_remote_code=self.trust_remote_code,
            )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts(category: str) -> list[dict]:
    """Load prompts for a given category."""
    prompt_file = PROMPTS_DIR / f"{category}.jsonl"
    if not prompt_file.exists():
        print(f"  Warning: No prompts found for category '{category}'")
        return []

    prompts = []
    with open(prompt_file) as f:
        for line in f:
            line = line.strip()
            if line:
                prompts.append(json.loads(line))
    return prompts


def format_prompt_for_eval(prompt_data: dict, category: str) -> str:
    """Format a prompt for evaluation based on its category."""
    if category == "fim":
        # FIM prompts have prefix/suffix structure
        prefix = prompt_data.get("prefix", "")
        suffix = prompt_data.get("suffix", "")
        return f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"

    elif category == "code_generation":
        return prompt_data["prompt"]

    elif category == "debugging":
        return prompt_data["prompt"]

    elif category == "tool_use":
        return prompt_data["prompt"]

    elif category == "repository_editing":
        return prompt_data["prompt"]

    elif category == "instruction_following":
        return prompt_data["prompt"]

    return prompt_data.get("prompt", str(prompt_data))


# ---------------------------------------------------------------------------
# Candidate loading
# ---------------------------------------------------------------------------

def load_candidates() -> list[CandidateConfig]:
    """Load candidate configurations from YAML."""
    with open(CANDIDATES_FILE) as f:
        data = yaml.safe_load(f)

    candidates = []
    for c in data.get("candidates", []):
        candidates.append(CandidateConfig(
            id=c["id"],
            name=c["name"],
            hf_id=c["hf_id"],
            params=c["params"],
            licence=c["licence"],
            context_length=c["context_length"],
            architecture=c["architecture"],
            status=c.get("status", "candidate"),
        ))
    return candidates


def get_backend(candidate: CandidateConfig) -> OllamaBackend | TransformersBackend:
    """Select the appropriate backend for a candidate."""
    # Try Ollama first (faster, already quantised)
    ollama_name = candidate.id.replace(".", "-")
    ollama = OllamaBackend(ollama_name)
    if ollama.is_available():
        print(f"  Using Ollama backend for {candidate.name}")
        return ollama

    # Fall back to Transformers
    trust_remote = "custom" in candidate.architecture.lower()
    print(f"  Using Transformers backend for {candidate.name}")
    return TransformersBackend(candidate.hf_id, trust_remote_code=trust_remote)


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def evaluate_candidate(
    candidate: CandidateConfig,
    categories: list[str],
    params: dict,
) -> list[EvalResult]:
    """Run all prompts for a candidate across specified categories."""
    results = []
    backend = get_backend(candidate)

    for category in categories:
        prompts = load_prompts(category)
        print(f"\n  Category: {category} ({len(prompts)} prompts)")

        for i, prompt_data in enumerate(prompts):
            prompt_id = prompt_data.get("id", f"{category}_{i:03d}")
            prompt_text = format_prompt_for_eval(prompt_data, category)

            print(f"    [{i+1}/{len(prompts)}] {prompt_id}...", end=" ", flush=True)

            try:
                result = backend.generate(prompt_text, params)
                eval_result = EvalResult(
                    candidate_id=candidate.id,
                    category=category,
                    prompt_id=prompt_id,
                    prompt_text=prompt_text[:500],  # Truncate for storage
                    raw_output=result["output"],
                    latency_seconds=result["latency"],
                    tokens_generated=result["tokens"],
                    tokens_per_second=result["tps"],
                )
                print(f"✓ ({result['tokens']} tok, {result['tps']:.1f} t/s)")

            except Exception as e:
                eval_result = EvalResult(
                    candidate_id=candidate.id,
                    category=category,
                    prompt_id=prompt_id,
                    prompt_text=prompt_text[:500],
                    raw_output="",
                    latency_seconds=0,
                    tokens_generated=0,
                    tokens_per_second=0,
                    error=str(e),
                )
                print(f"✗ ({e})")

            results.append(eval_result)

    return results


def save_results(candidate_id: str, results: list[EvalResult]):
    """Save results to a JSONL file per candidate."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RESULTS_DIR / f"{candidate_id}.jsonl"

    with open(output_file, "w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")

    print(f"\n  Results saved to {output_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Nova v12 Foundation Bake-Off Runner"
    )
    parser.add_argument(
        "--all-candidates",
        action="store_true",
        help="Evaluate all candidates",
    )
    parser.add_argument(
        "--candidate",
        type=str,
        help="Evaluate a specific candidate by ID",
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=CATEGORIES,
        help="Evaluate only a specific category",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Generation temperature (default: 0.0)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Maximum tokens to generate (default: 2048)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be evaluated without running",
    )

    args = parser.parse_args()

    # Load candidates
    candidates = load_candidates()

    # Filter candidates
    if args.candidate:
        candidates = [c for c in candidates if c.id == args.candidate]
        if not candidates:
            print(f"Error: Candidate '{args.candidate}' not found")
            sys.exit(1)
    elif not args.all_candidates:
        # Default: evaluate only lead candidate and control
        candidates = [
            c for c in candidates
            if c.status in ("lead_candidate", "control", "strong_candidate")
        ]

    # Select categories
    categories = [args.category] if args.category else CATEGORIES

    # Build params
    params = {
        **DEFAULT_PARAMS,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }

    # Summary
    print("=" * 70)
    print("NOVA v12 FOUNDATION BAKE-OFF")
    print("=" * 70)
    print(f"Candidates:  {', '.join(c.name for c in candidates)}")
    print(f"Categories:  {', '.join(categories)}")
    print(f"Temperature: {params['temperature']}")
    print(f"Max tokens:  {params['max_tokens']}")
    print(f"Timestamp:   {datetime.now().isoformat()}")
    print("=" * 70)

    if args.dry_run:
        for c in candidates:
            print(f"\n{c.name} ({c.id})")
            print(f"  HF: {c.hf_id}")
            print(f"  Params: {c.params}")
            print(f"  Licence: {c.licence}")
            for cat in categories:
                prompts = load_prompts(cat)
                print(f"  {cat}: {len(prompts)} prompts")
        return

    # Run evaluations
    all_results = {}
    for candidate in candidates:
        print(f"\n{'='*70}")
        print(f"Evaluating: {candidate.name}")
        print(f"  HF ID: {candidate.hf_id}")
        print(f"  Params: {candidate.params}")
        print(f"  Licence: {candidate.licence}")
        print(f"  Context: {candidate.context_length}")
        print(f"{'='*70}")

        try:
            results = evaluate_candidate(candidate, categories, params)
            save_results(candidate.id, results)
            all_results[candidate.id] = results
        except Exception as e:
            print(f"\n  FAILED: {e}")
            traceback.print_exc()

    # Print summary
    print(f"\n{'='*70}")
    print("BAKE-OFF SUMMARY")
    print(f"{'='*70}")
    for cid, results in all_results.items():
        total = len(results)
        errors = sum(1 for r in results if r.error)
        avg_tps = (
            sum(r.tokens_per_second for r in results if not r.error)
            / max(1, total - errors)
        )
        print(f"  {cid}: {total} prompts, {errors} errors, {avg_tps:.1f} avg t/s")

    print(f"\nResults directory: {RESULTS_DIR}")
    print("Run score_bakeoff.py to compute weighted scores.")


if __name__ == "__main__":
    main()
