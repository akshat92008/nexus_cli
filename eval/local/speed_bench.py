#!/usr/bin/env python3
"""
Nova v12 Evaluation — Local Speed Benchmark

Measures inference performance across quantisation levels and hardware.

Metrics:
    - Tokens per second (generation)
    - Time to first token (TTFT)
    - Peak memory usage
    - Cold start time

Usage:
    python speed_bench.py --model nova-code-4b --backend ollama
    python speed_bench.py --model /path/to/model --backend transformers
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import urllib.request


# ---------------------------------------------------------------------------
# Benchmark prompts (varying complexity)
# ---------------------------------------------------------------------------

SPEED_PROMPTS = [
    {
        "id": "short",
        "prompt": "Write a Python function to check if a number is prime.",
        "expected_tokens": 100,
    },
    {
        "id": "medium",
        "prompt": "Write a Python class implementing an LRU cache with O(1) get and put operations. Include proper error handling and type hints.",
        "expected_tokens": 300,
    },
    {
        "id": "long",
        "prompt": "Write a complete REST API in Python using FastAPI with the following endpoints: POST /users (create user with email validation), GET /users/{id} (get user by ID), PATCH /users/{id} (update user), DELETE /users/{id} (soft delete). Include proper error handling, Pydantic models, and basic tests.",
        "expected_tokens": 800,
    },
    {
        "id": "fim",
        "prompt": "<|fim_prefix|>def binary_search(arr: list[int], target: int) -> int:\n    left, right = 0, len(arr) - 1\n<|fim_suffix|>\n    return -1<|fim_middle|>",
        "expected_tokens": 100,
    },
]


@dataclass
class BenchmarkResult:
    model: str
    backend: str
    prompt_id: str
    tokens_generated: int
    tokens_per_second: float
    time_to_first_token_ms: float
    total_latency_seconds: float
    peak_memory_mb: float
    quantisation: str
    hardware: str
    timestamp: str


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------

def benchmark_ollama(model: str, prompt: str, max_tokens: int = 1024) -> dict:
    """Run a single benchmark against Ollama."""
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": max_tokens,
            "seed": 42,
        },
    }

    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )

    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
    total = time.perf_counter() - start

    eval_count = result.get("eval_count", 0)
    eval_duration = result.get("eval_duration", 0)
    prompt_eval_duration = result.get("prompt_eval_duration", 0)

    tps = eval_count / (eval_duration / 1e9) if eval_duration > 0 else 0
    ttft = prompt_eval_duration / 1e6 if prompt_eval_duration > 0 else 0

    return {
        "tokens": eval_count,
        "tps": tps,
        "ttft_ms": ttft,
        "total_seconds": total,
        "output": result.get("response", ""),
    }


# ---------------------------------------------------------------------------
# Memory measurement
# ---------------------------------------------------------------------------

def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB."""
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024 / 1024  # Convert to MB (macOS reports in bytes)
    except Exception:
        return 0.0


def get_system_info() -> dict:
    """Get system hardware information."""
    import platform
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }

    # Try to get more detail on macOS
    try:
        import subprocess
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True
        )
        ram_bytes = int(result.stdout.strip())
        info["ram_gb"] = ram_bytes / (1024 ** 3)
    except Exception:
        pass

    try:
        import subprocess
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True
        )
        info["cpu"] = result.stdout.strip()
    except Exception:
        pass

    return info


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def run_speed_benchmark(
    model: str,
    backend: str = "ollama",
    quantisation: str = "unknown",
    num_warmup: int = 1,
    num_runs: int = 3,
    output_file: Optional[str] = None,
):
    """Run the speed benchmark suite."""
    hardware_info = get_system_info()
    hardware_str = f"{hardware_info.get('cpu', 'unknown')} / {hardware_info.get('ram_gb', '?'):.0f}GB"

    print("=" * 70)
    print("NOVA v12 SPEED BENCHMARK")
    print("=" * 70)
    print(f"Model:         {model}")
    print(f"Backend:       {backend}")
    print(f"Quantisation:  {quantisation}")
    print(f"Hardware:       {hardware_str}")
    print(f"Warmup runs:   {num_warmup}")
    print(f"Benchmark runs: {num_runs}")
    print("=" * 70)

    results = []

    for prompt_info in SPEED_PROMPTS:
        prompt_id = prompt_info["id"]
        prompt = prompt_info["prompt"]

        print(f"\n--- Prompt: {prompt_id} ---")

        # Warmup
        for i in range(num_warmup):
            print(f"  Warmup {i+1}/{num_warmup}...", end=" ", flush=True)
            try:
                if backend == "ollama":
                    benchmark_ollama(model, prompt)
                print("done")
            except Exception as e:
                print(f"error: {e}")

        # Benchmark runs
        run_results = []
        for i in range(num_runs):
            print(f"  Run {i+1}/{num_runs}...", end=" ", flush=True)
            try:
                mem_before = get_memory_usage_mb()

                if backend == "ollama":
                    result = benchmark_ollama(model, prompt)

                mem_after = get_memory_usage_mb()

                bench_result = BenchmarkResult(
                    model=model,
                    backend=backend,
                    prompt_id=prompt_id,
                    tokens_generated=result["tokens"],
                    tokens_per_second=result["tps"],
                    time_to_first_token_ms=result["ttft_ms"],
                    total_latency_seconds=result["total_seconds"],
                    peak_memory_mb=max(mem_before, mem_after),
                    quantisation=quantisation,
                    hardware=hardware_str,
                    timestamp=datetime.now().isoformat(),
                )
                run_results.append(bench_result)
                results.append(bench_result)

                print(
                    f"{result['tokens']} tok, "
                    f"{result['tps']:.1f} t/s, "
                    f"TTFT: {result['ttft_ms']:.0f}ms"
                )

            except Exception as e:
                print(f"error: {e}")

        # Summary for this prompt
        if run_results:
            avg_tps = sum(r.tokens_per_second for r in run_results) / len(run_results)
            avg_ttft = sum(r.time_to_first_token_ms for r in run_results) / len(run_results)
            print(f"  Average: {avg_tps:.1f} t/s, TTFT: {avg_ttft:.0f}ms")

    # Final report
    print(f"\n{'='*70}")
    print("SPEED BENCHMARK RESULTS")
    print(f"{'='*70}")
    print(f"{'Prompt':<10} {'Tokens':<8} {'t/s':<10} {'TTFT(ms)':<10} {'Latency(s)':<12}")
    print("-" * 50)

    for prompt_info in SPEED_PROMPTS:
        pid = prompt_info["id"]
        prompt_results = [r for r in results if r.prompt_id == pid]
        if prompt_results:
            avg_tok = sum(r.tokens_generated for r in prompt_results) / len(prompt_results)
            avg_tps = sum(r.tokens_per_second for r in prompt_results) / len(prompt_results)
            avg_ttft = sum(r.time_to_first_token_ms for r in prompt_results) / len(prompt_results)
            avg_lat = sum(r.total_latency_seconds for r in prompt_results) / len(prompt_results)
            print(f"{pid:<10} {avg_tok:<8.0f} {avg_tps:<10.1f} {avg_ttft:<10.0f} {avg_lat:<12.2f}")

    # Save results
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for r in results:
                f.write(json.dumps(asdict(r)) + "\n")
        print(f"\nResults saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Nova v12 Speed Benchmark")
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--backend", choices=["ollama", "transformers"],
                        default="ollama")
    parser.add_argument("--quantisation", type=str, default="unknown")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=str)

    args = parser.parse_args()
    run_speed_benchmark(
        model=args.model,
        backend=args.backend,
        quantisation=args.quantisation,
        num_warmup=args.warmup,
        num_runs=args.runs,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
