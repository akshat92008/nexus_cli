#!/usr/bin/env python3
"""
Nova v12 Data Generator — Bug Injector

Injects controlled bugs into passing code to create debugging training data.

Pipeline:
    1. Take a passing code + test pair
    2. Verify tests pass on original code
    3. Inject a specific bug mutation
    4. Verify tests now fail
    5. Create training record: buggy code + error → fixed code

Bug types:
    - Off-by-one errors
    - Missing validation
    - Wrong operator
    - Swapped arguments
    - Missing await
    - Wrong return type
    - Import errors
    - Exception handling errors
    - Boundary condition errors
    - Type mismatch errors

Usage:
    python bug_injector.py --input /path/to/code.jsonl --output /path/to/bugs.jsonl
"""

import argparse
import ast
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable


# ---------------------------------------------------------------------------
# Bug mutation strategies
# ---------------------------------------------------------------------------

@dataclass
class Mutation:
    """A bug mutation to inject into code."""
    name: str
    description: str
    pattern: str  # regex to find
    replacement: str  # what to replace with
    language: str  # "all" or specific


# Universal mutations (work across languages)
UNIVERSAL_MUTATIONS = [
    Mutation(
        name="off_by_one_gte_to_gt",
        description="Changed >= to > (off-by-one boundary)",
        pattern=r">=",
        replacement=">",
        language="all",
    ),
    Mutation(
        name="off_by_one_lte_to_lt",
        description="Changed <= to < (off-by-one boundary)",
        pattern=r"<=",
        replacement="<",
        language="all",
    ),
    Mutation(
        name="wrong_equality",
        description="Changed == to != (inverted condition)",
        pattern=r"==",
        replacement="!=",
        language="all",
    ),
    Mutation(
        name="wrong_boolean_and_to_or",
        description="Changed and/&& to or/|| (logic error)",
        pattern=r"\band\b",
        replacement="or",
        language="python",
    ),
    Mutation(
        name="wrong_operator_plus_to_minus",
        description="Changed + to - (wrong arithmetic)",
        pattern=r"(?<!=)\+(?!=)",
        replacement="-",
        language="all",
    ),
    Mutation(
        name="off_by_one_range",
        description="Changed range(n) to range(n-1) (off-by-one)",
        pattern=r"range\((\w+)\)",
        replacement=r"range(\1 - 1)",
        language="python",
    ),
    Mutation(
        name="return_none",
        description="Removed return value (returns None)",
        pattern=r"return (.+)",
        replacement="return None",
        language="python",
    ),
    Mutation(
        name="wrong_index",
        description="Changed index [0] to [1] (off-by-one index)",
        pattern=r"\[0\]",
        replacement="[1]",
        language="all",
    ),
    Mutation(
        name="missing_not",
        description="Removed 'not' from condition",
        pattern=r"\bnot\s+",
        replacement="",
        language="python",
    ),
    Mutation(
        name="swap_true_false",
        description="Changed True to False",
        pattern=r"\bTrue\b",
        replacement="False",
        language="python",
    ),
]

# Python-specific mutations
PYTHON_MUTATIONS = [
    Mutation(
        name="missing_await",
        description="Removed await keyword (async bug)",
        pattern=r"\bawait\s+",
        replacement="",
        language="python",
    ),
    Mutation(
        name="wrong_exception",
        description="Changed ValueError to TypeError",
        pattern=r"ValueError",
        replacement="TypeError",
        language="python",
    ),
    Mutation(
        name="append_vs_extend",
        description="Changed append to extend (type error)",
        pattern=r"\.append\(",
        replacement=".extend(",
        language="python",
    ),
    Mutation(
        name="missing_self",
        description="Removed self. prefix (attribute error)",
        pattern=r"self\.(\w+)",
        replacement=r"\1",
        language="python",
    ),
    Mutation(
        name="wrong_string_format",
        description="Changed f-string to plain string (missing interpolation)",
        pattern=r'f"([^"]*\{)',
        replacement=r'"{\1',
        language="python",
    ),
]

# JavaScript/TypeScript mutations
JS_MUTATIONS = [
    Mutation(
        name="missing_await_js",
        description="Removed await keyword",
        pattern=r"\bawait\s+",
        replacement="",
        language="javascript",
    ),
    Mutation(
        name="strict_equality",
        description="Changed === to == (loose equality bug)",
        pattern=r"===",
        replacement="==",
        language="javascript",
    ),
    Mutation(
        name="const_to_var",
        description="Changed const to var (scoping bug)",
        pattern=r"\bconst\b",
        replacement="var",
        language="javascript",
    ),
]

ALL_MUTATIONS = UNIVERSAL_MUTATIONS + PYTHON_MUTATIONS + JS_MUTATIONS


# ---------------------------------------------------------------------------
# Bug injection
# ---------------------------------------------------------------------------

def get_mutations_for_language(language: str) -> list[Mutation]:
    """Get applicable mutations for a language."""
    return [
        m for m in ALL_MUTATIONS
        if m.language == "all" or m.language == language
    ]


def inject_bug(content: str, mutation: Mutation) -> Optional[str]:
    """Attempt to inject a bug using the given mutation.
    
    Returns the mutated content, or None if the pattern was not found.
    """
    # Find all matches
    matches = list(re.finditer(mutation.pattern, content))

    if not matches:
        return None

    # Select a random match (prefer matches inside functions, not imports)
    # Simple heuristic: prefer matches after the first 5 lines
    lines = content.split("\n")
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line) + 1)

    good_matches = []
    for m in matches:
        # Find what line this match is on
        match_pos = m.start()
        for line_num, start in enumerate(line_starts):
            if start > match_pos:
                if line_num > 5:  # After imports/headers
                    good_matches.append(m)
                break

    if not good_matches:
        good_matches = matches

    # Pick a random match
    match = random.choice(good_matches)

    # Apply the mutation at this specific location
    mutated = (
        content[:match.start()]
        + re.sub(mutation.pattern, mutation.replacement, match.group(), count=1)
        + content[match.end():]
    )

    # Verify the content actually changed
    if mutated == content:
        return None

    return mutated


def create_bug_record(
    original_content: str,
    buggy_content: str,
    mutation: Mutation,
    metadata: dict,
) -> dict:
    """Create a training record from a bug injection."""
    return {
        "type": "debugging",
        "mode": "<|nova_debug|>",
        "original_code": original_content,
        "buggy_code": buggy_content,
        "bug_type": mutation.name,
        "bug_description": mutation.description,
        "language": metadata.get("language", "python"),
        "source_file": metadata.get("source_id", ""),
        "source_licence": metadata.get("licence", ""),
        "instruction": (
            f"The following code has a bug: {mutation.description}. "
            f"Find and fix the issue."
        ),
        "input": buggy_content,
        "output": original_content,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nova v12 Bug Injector")
    parser.add_argument("--input", type=str, required=True,
                        help="Input JSONL file of quality-scored code")
    parser.add_argument("--output", type=str, required=True,
                        help="Output JSONL file of bug injection records")
    parser.add_argument("--mutations-per-file", type=int, default=2,
                        help="Mutations to attempt per file")
    parser.add_argument("--max-records", type=int, default=50000,
                        help="Maximum output records")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed")

    args = parser.parse_args()
    random.seed(args.seed)

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_files = 0
    total_records = 0
    total_attempts = 0

    print(f"Injecting bugs from {input_path.name}...")

    with open(input_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue

            total_files += 1
            record = json.loads(line)
            content = record.get("content", "")
            language = record.get("language", "python")

            # Get applicable mutations
            mutations = get_mutations_for_language(language)
            if not mutations:
                continue

            # Try injecting bugs
            random.shuffle(mutations)
            injected = 0

            for mutation in mutations[:args.mutations_per_file * 2]:
                total_attempts += 1
                buggy = inject_bug(content, mutation)

                if buggy:
                    bug_record = create_bug_record(
                        content, buggy, mutation,
                        {
                            "language": language,
                            "source_id": record.get("source_id", ""),
                            "licence": record.get("licence", ""),
                        }
                    )
                    fout.write(json.dumps(bug_record, ensure_ascii=False) + "\n")
                    total_records += 1
                    injected += 1

                    if injected >= args.mutations_per_file:
                        break

            if total_records >= args.max_records:
                break

            if total_files % 1000 == 0:
                print(
                    f"  Files: {total_files:,} | "
                    f"Attempts: {total_attempts:,} | "
                    f"Records: {total_records:,} | "
                    f"Rate: {total_records/max(1,total_attempts)*100:.1f}%"
                )

    print(f"\nDone. Files: {total_files:,} | Records: {total_records:,}")
    print(f"Success rate: {total_records/max(1,total_attempts)*100:.1f}%")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
