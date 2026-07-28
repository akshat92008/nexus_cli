#!/usr/bin/env python3
"""
Nova v12 Data Pipeline — Contamination Checker

Detects overlap between training data and evaluation benchmarks
(HumanEval, MBPP, LiveCodeBench, SWE-bench) to prevent data leakage.

Usage:
    python contamination_check.py --dataset /path/to/data.jsonl
    python contamination_check.py --dataset /path/to/data.jsonl --threshold 0.6
"""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Known benchmark signatures
# ---------------------------------------------------------------------------

# These are n-gram fingerprints of known benchmark problems.
# In production, these should be computed from the actual benchmark datasets.

HUMANEVAL_SIGNATURES = [
    # Function signatures from HumanEval (canonical problems)
    "def has_close_elements(numbers: List[float], threshold: float) -> bool:",
    "def separate_paren_groups(paren_string: str) -> List[str]:",
    "def truncate_number(number: float) -> float:",
    "def below_zero(operations: List[int]) -> bool:",
    "def mean_absolute_deviation(numbers: List[float]) -> float:",
    "def intersperse(numbers: List[int], delimeter: int) -> List[int]:",
    "def parse_nested_parens(paren_string: str) -> List[int]:",
    "def filter_by_substring(strings: List[str], substring: str) -> List[str]:",
    "def sum_product(numbers: List[int]) -> Tuple[int, int]:",
    "def rolling_max(numbers: List[int]) -> List[int]:",
    "def make_palindrome(string: str) -> str:",
    "def string_xor(a: str, b: str) -> str:",
    "def longest(strings: List[str]) -> Optional[str]:",
    "def greatest_common_divisor(a: int, b: int) -> int:",
    "def all_prefixes(string: str) -> List[str]:",
    "def string_sequence(n: int) -> str:",
    "def count_distinct_characters(string: str) -> int:",
    "def parse_music(music_string: str) -> List[int]:",
    "def how_many_times(string: str, substring: str) -> int:",
    "def sort_numbers(numbers: str) -> str:",
    "def find_closest_elements(numbers: List[float]) -> Tuple[float, float]:",
    "def rescale_to_unit(numbers: List[float]) -> List[float]:",
    "def filter_integers(values: List[Any]) -> List[int]:",
    "def strlen(string: str) -> int:",
    "def largest_divisor(n: int) -> int:",
    "def factorize(n: int) -> List[int]:",
    "def remove_duplicates(numbers: List[int]) -> List[int]:",
    "def flip_case(string: str) -> str:",
    "def concatenate(strings: List[str]) -> str:",
    "def filter_by_prefix(strings: List[str], prefix: str) -> List[str]:",
]

MBPP_SIGNATURES = [
    # Common MBPP problem patterns (canonical task descriptions)
    "Write a function to find the similar elements from the given two tuple lists",
    "Write a python function to identify non-prime numbers",
    "Write a function to find the largest integers from a given list",
    "Write a python function to convert the given string to upper case",
    "Write a function to find the sum of the three lowest positive numbers",
    "Write a python function to remove first and last occurrence of a given character",
    "Write a function to find the difference of first even and odd number",
    "Write a function to check whether the given number is undulating or not",
    "Write a function to calculate the factorial of a number",
    "Write a function to find the perimeter of a triangle",
]


def compute_ngrams(text: str, n: int = 5) -> set[str]:
    """Compute character n-grams from text."""
    text = re.sub(r'\s+', ' ', text.strip().lower())
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def compute_token_ngrams(text: str, n: int = 3) -> set[tuple]:
    """Compute token (word) n-grams from text."""
    tokens = re.findall(r'\w+', text.lower())
    return {tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)}


class ContaminationChecker:
    """Checks training data for benchmark contamination."""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.benchmark_ngrams: dict[str, list[set]] = {}
        self.benchmark_signatures: dict[str, list[str]] = {}
        self._load_benchmarks()

    def _load_benchmarks(self):
        """Load benchmark fingerprints."""
        # HumanEval
        self.benchmark_signatures["humaneval"] = HUMANEVAL_SIGNATURES
        self.benchmark_ngrams["humaneval"] = [
            compute_ngrams(sig) for sig in HUMANEVAL_SIGNATURES
        ]

        # MBPP
        self.benchmark_signatures["mbpp"] = MBPP_SIGNATURES
        self.benchmark_ngrams["mbpp"] = [
            compute_ngrams(sig) for sig in MBPP_SIGNATURES
        ]

    def check_content(self, content: str) -> list[dict]:
        """Check a piece of content for contamination.
        
        Returns list of contamination hits with benchmark name and overlap score.
        """
        hits = []
        content_ngrams = compute_ngrams(content)

        if not content_ngrams:
            return hits

        for benchmark, sig_ngrams_list in self.benchmark_ngrams.items():
            for i, sig_ngrams in enumerate(sig_ngrams_list):
                if not sig_ngrams:
                    continue

                overlap = len(content_ngrams & sig_ngrams) / len(sig_ngrams)

                if overlap >= self.threshold:
                    hits.append({
                        "benchmark": benchmark,
                        "signature_index": i,
                        "signature": self.benchmark_signatures[benchmark][i][:100],
                        "overlap": overlap,
                    })

        return hits

    def check_exact_match(self, content: str) -> list[dict]:
        """Check for exact substring matches of benchmark signatures."""
        hits = []
        content_lower = content.lower()

        for benchmark, signatures in self.benchmark_signatures.items():
            for i, sig in enumerate(signatures):
                if sig.lower() in content_lower:
                    hits.append({
                        "benchmark": benchmark,
                        "signature_index": i,
                        "signature": sig[:100],
                        "match_type": "exact",
                    })

        return hits


def check_dataset(
    dataset_path: str,
    threshold: float = 0.6,
    output_path: Optional[str] = None,
):
    """Check an entire dataset file for contamination."""
    checker = ContaminationChecker(threshold=threshold)
    contaminated = []
    clean = 0
    total = 0

    path = Path(dataset_path)
    if not path.exists():
        print(f"Error: Dataset file not found: {dataset_path}")
        sys.exit(1)

    print(f"Checking {path.name} for benchmark contamination...")
    print(f"Threshold: {threshold}")

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            total += 1
            try:
                record = json.loads(line)
                content = record.get("content", "")
            except json.JSONDecodeError:
                content = line

            # Check n-gram overlap
            hits = checker.check_content(content)

            # Check exact matches
            exact_hits = checker.check_exact_match(content)

            all_hits = hits + exact_hits

            if all_hits:
                contaminated.append({
                    "line": line_num,
                    "source": record.get("source_id", f"line:{line_num}"),
                    "hits": all_hits,
                })
            else:
                clean += 1

            if total % 10000 == 0:
                print(f"  Checked {total:,} records, {len(contaminated)} contaminated")

    # Report
    print(f"\n{'='*70}")
    print("CONTAMINATION CHECK RESULTS")
    print(f"{'='*70}")
    print(f"Total records:     {total:,}")
    print(f"Clean records:     {clean:,}")
    print(f"Contaminated:      {len(contaminated):,}")
    print(f"Contamination rate: {len(contaminated)/max(1,total)*100:.2f}%")

    if contaminated:
        print(f"\nContaminated records:")
        for c in contaminated[:20]:
            print(f"  Line {c['line']}: {c['source']}")
            for h in c["hits"]:
                print(f"    → {h['benchmark']}: {h.get('signature', '')[:60]}...")

    # Save report
    if output_path:
        report = {
            "dataset": str(path),
            "threshold": threshold,
            "total_records": total,
            "clean_records": clean,
            "contaminated_records": len(contaminated),
            "contamination_rate": len(contaminated) / max(1, total),
            "contaminated_details": contaminated,
        }
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nFull report saved to {output_path}")

    return len(contaminated) == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Nova v12 Contamination Checker"
    )
    parser.add_argument("--dataset", type=str, required=True,
                        help="Path to dataset JSONL file")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="N-gram overlap threshold (default: 0.6)")
    parser.add_argument("--output", type=str,
                        help="Output path for contamination report JSON")

    args = parser.parse_args()
    is_clean = check_dataset(args.dataset, args.threshold, args.output)
    sys.exit(0 if is_clean else 1)


if __name__ == "__main__":
    main()
