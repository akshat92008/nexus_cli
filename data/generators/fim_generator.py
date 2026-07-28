#!/usr/bin/env python3
"""
Nova v12 Data Generator — Fill-in-the-Middle (FIM) Samples

Generates FIM training examples from source code files by masking
random spans within functions, methods, or logical blocks.

Format:
    <|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>{middle}

Usage:
    python fim_generator.py --input /path/to/code.jsonl --output /path/to/fim.jsonl
"""

import argparse
import ast
import json
import random
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# FIM tokens
# ---------------------------------------------------------------------------

FIM_PREFIX = "<|fim_prefix|>"
FIM_SUFFIX = "<|fim_suffix|>"
FIM_MIDDLE = "<|fim_middle|>"


# ---------------------------------------------------------------------------
# Span extraction strategies
# ---------------------------------------------------------------------------

def find_python_spans(content: str) -> list[tuple[int, int]]:
    """Find maskable spans in Python code (function/method bodies)."""
    spans = []
    try:
        tree = ast.parse(content)
        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Get the body range (skip the def line)
                if node.body:
                    start_line = node.body[0].lineno - 1
                    end_line = node.body[-1].end_lineno
                    if end_line and end_line > start_line:
                        start_char = sum(len(lines[i]) + 1 for i in range(start_line))
                        end_char = sum(len(lines[i]) + 1 for i in range(end_line))
                        if 10 < end_char - start_char < 2000:
                            spans.append((start_char, end_char))

    except SyntaxError:
        pass

    return spans


def find_generic_spans(content: str) -> list[tuple[int, int]]:
    """Find maskable spans using brace-based heuristics."""
    spans = []

    # Find function-like blocks: { ... }
    brace_depth = 0
    block_start = -1

    for i, char in enumerate(content):
        if char == "{":
            if brace_depth == 0:
                block_start = i + 1
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth == 0 and block_start > 0:
                block_end = i
                span_len = block_end - block_start
                if 10 < span_len < 2000:
                    spans.append((block_start, block_end))

    return spans


def find_line_spans(content: str, min_lines: int = 3, max_lines: int = 20) -> list[tuple[int, int]]:
    """Fallback: find spans by selecting random line ranges."""
    lines = content.split("\n")
    spans = []

    if len(lines) < min_lines * 2:
        return spans

    for _ in range(10):  # Try 10 random spans
        span_len = random.randint(min_lines, min(max_lines, len(lines) // 3))
        start_line = random.randint(1, len(lines) - span_len - 1)

        start_char = sum(len(lines[i]) + 1 for i in range(start_line))
        end_char = sum(len(lines[i]) + 1 for i in range(start_line + span_len))

        if 20 < end_char - start_char < 2000:
            spans.append((start_char, end_char))

    return spans


# ---------------------------------------------------------------------------
# FIM sample generation
# ---------------------------------------------------------------------------

def generate_fim_sample(content: str, language: str) -> Optional[dict]:
    """Generate a single FIM training sample from a code file."""
    # Find spans
    if language == "python":
        spans = find_python_spans(content)
    elif language in ("javascript", "typescript", "java", "cpp", "go", "rust"):
        spans = find_generic_spans(content)
    else:
        spans = []

    # Fallback to line-based spans
    if not spans:
        spans = find_line_spans(content)

    if not spans:
        return None

    # Select a random span
    start, end = random.choice(spans)

    prefix = content[:start]
    middle = content[start:end]
    suffix = content[end:]

    # Validate
    if not middle.strip():
        return None

    return {
        "prefix": prefix,
        "middle": middle,
        "suffix": suffix,
        "language": language,
        "formatted": f"{FIM_PREFIX}{prefix}{FIM_SUFFIX}{suffix}{FIM_MIDDLE}{middle}",
    }


def generate_multiple_fim_samples(
    content: str,
    language: str,
    num_samples: int = 3,
) -> list[dict]:
    """Generate multiple FIM samples from a single file."""
    samples = []

    for _ in range(num_samples * 2):  # Try more to account for failures
        sample = generate_fim_sample(content, language)
        if sample and sample not in samples:
            samples.append(sample)
        if len(samples) >= num_samples:
            break

    return samples


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nova v12 FIM Generator")
    parser.add_argument("--input", type=str, required=True,
                        help="Input JSONL file of code records")
    parser.add_argument("--output", type=str, required=True,
                        help="Output JSONL file of FIM samples")
    parser.add_argument("--samples-per-file", type=int, default=2,
                        help="FIM samples to generate per file (default: 2)")
    parser.add_argument("--max-samples", type=int, default=100000,
                        help="Maximum total FIM samples")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed")

    args = parser.parse_args()
    random.seed(args.seed)

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_samples = 0

    print(f"Generating FIM samples from {input_path.name}...")

    with open(input_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue

            total_files += 1
            record = json.loads(line)
            content = record.get("content", "")
            language = record.get("language", "python")

            samples = generate_multiple_fim_samples(
                content, language, args.samples_per_file
            )

            for sample in samples:
                sample["source_file"] = record.get("source_id", "")
                sample["source_licence"] = record.get("licence", "")
                fout.write(json.dumps(sample, ensure_ascii=False) + "\n")
                total_samples += 1

            if total_samples >= args.max_samples:
                break

            if total_files % 1000 == 0:
                print(f"  Files: {total_files:,} | FIM samples: {total_samples:,}")

    print(f"\nDone. Files: {total_files:,} | FIM samples: {total_samples:,}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
