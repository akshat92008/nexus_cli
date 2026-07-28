#!/usr/bin/env python3
"""
Nova v12 Foundation Bake-Off Scorer

Reads raw evaluation results and computes weighted scores per candidate
using the Section 4 bake-off criteria.

Usage:
    python score_bakeoff.py --report
    python score_bakeoff.py --report --output results/bakeoff_report.md
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BAKEOFF_DIR = Path(__file__).parent
RESULTS_DIR = BAKEOFF_DIR / "results"
CANDIDATES_FILE = BAKEOFF_DIR / "candidates.yaml"

# Scoring weights from Section 4 of the blueprint
SCORING_WEIGHTS = {
    "code_correctness": 0.25,
    "debugging_repair": 0.15,
    "repository_tasks": 0.15,
    "tool_use": 0.10,
    "fim_completion": 0.10,
    "instruction_following": 0.10,
    "quantised_performance": 0.05,
    "speed_memory": 0.05,
    "licence_ecosystem": 0.05,
}

# Map evaluation categories to scoring dimensions
CATEGORY_TO_DIMENSION = {
    "code_generation": "code_correctness",
    "debugging": "debugging_repair",
    "repository_editing": "repository_tasks",
    "tool_use": "tool_use",
    "fim": "fim_completion",
    "instruction_following": "instruction_following",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CandidateScore:
    """Aggregated score for a candidate."""
    candidate_id: str
    candidate_name: str
    dimension_scores: dict[str, float]
    weighted_total: float
    avg_tokens_per_second: float
    avg_latency: float
    total_prompts: int
    total_errors: int


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def score_code_generation(result: dict) -> float:
    """Score a code generation result (0.0 to 1.0)."""
    output = result.get("raw_output", "")
    if result.get("error"):
        return 0.0

    score = 0.0

    # Has code block
    if "```" in output or "def " in output or "function " in output:
        score += 0.3

    # Reasonable length (not empty, not absurdly short)
    if 50 < len(output) < 10000:
        score += 0.2

    # Contains expected patterns based on language
    prompt = result.get("prompt_text", "")
    if "python" in prompt.lower() and ("def " in output or "class " in output):
        score += 0.2
    elif "javascript" in prompt.lower() and ("function" in output or "=>" in output or "const " in output):
        score += 0.2
    elif "typescript" in prompt.lower() and ("function" in output or "interface" in output or ": " in output):
        score += 0.2
    elif any(lang in prompt.lower() for lang in ["java", "go", "rust", "cpp", "sql", "bash"]):
        if len(output) > 50:
            score += 0.2

    # No obvious hallucination markers
    hallucination_markers = [
        "I cannot", "I'm sorry", "I don't", "As an AI",
        "I'm unable", "please provide",
    ]
    if not any(marker.lower() in output.lower() for marker in hallucination_markers):
        score += 0.15

    # Syntactic validity check (basic — does it look like code?)
    code_patterns = [
        r"def \w+", r"class \w+", r"function\s+\w+", r"func\s+\w+",
        r"fn\s+\w+", r"public\s+\w+", r"import\s+", r"from\s+\w+\s+import",
        r"const\s+\w+", r"let\s+\w+", r"var\s+\w+", r"SELECT\s+",
    ]
    if any(re.search(pat, output) for pat in code_patterns):
        score += 0.15

    return min(score, 1.0)


def score_debugging(result: dict) -> float:
    """Score a debugging result."""
    output = result.get("raw_output", "")
    if result.get("error"):
        return 0.0

    score = 0.0

    # Identifies the bug type or root cause
    bug_keywords = [
        "bug", "issue", "problem", "fix", "error", "cause",
        "because", "reason", "root cause", "the issue is",
    ]
    if any(kw in output.lower() for kw in bug_keywords):
        score += 0.3

    # Provides a fix/patch
    if "```" in output and any(w in output.lower() for w in ["fix", "correct", "change", "replace"]):
        score += 0.3

    # Explains the fix
    if len(output) > 100:
        score += 0.2

    # Doesn't just rewrite everything
    if len(output) < 5000:
        score += 0.2

    return min(score, 1.0)


def score_fim(result: dict) -> float:
    """Score a fill-in-the-middle result."""
    output = result.get("raw_output", "")
    if result.get("error"):
        return 0.0

    score = 0.0

    # Produced some output
    if len(output.strip()) > 0:
        score += 0.3

    # Reasonable length (FIM should be concise)
    if 5 < len(output) < 2000:
        score += 0.3

    # Looks like code, not explanation
    if not output.strip().startswith(("Here", "The", "This", "I ")):
        score += 0.2

    # No markdown wrapping (FIM should be raw code)
    if "```" not in output:
        score += 0.2

    return min(score, 1.0)


def score_tool_use(result: dict) -> float:
    """Score a tool-use result."""
    output = result.get("raw_output", "")
    if result.get("error"):
        return 0.0

    score = 0.0

    # Contains JSON tool call structure
    if '"tool"' in output or '"function"' in output or '"name"' in output:
        score += 0.3

    # Contains valid JSON
    try:
        # Try to find and parse JSON blocks
        json_pattern = r'\{[^{}]*\}'
        matches = re.findall(json_pattern, output)
        if any(json.loads(m) for m in matches):
            score += 0.3
    except (json.JSONDecodeError, ValueError):
        pass

    # References expected tools
    expected_tools = ["read_file", "list_files", "search_code", "apply_patch", "run_tests"]
    if any(tool in output for tool in expected_tools):
        score += 0.2

    # Multi-step workflow
    if output.count('"tool"') >= 2 or output.count("Step") >= 2:
        score += 0.2

    return min(score, 1.0)


def score_repository_editing(result: dict) -> float:
    """Score a repository editing result."""
    output = result.get("raw_output", "")
    if result.get("error"):
        return 0.0

    score = 0.0

    # Contains code changes
    if "```" in output:
        score += 0.25

    # References specific files
    file_patterns = [r'\w+\.\w{1,4}', r'src/', r'tests/', r'test_']
    if any(re.search(pat, output) for pat in file_patterns):
        score += 0.25

    # Preserves existing code (mentions preservation/keeping)
    if any(w in output.lower() for w in ["existing", "preserve", "keep", "unchanged", "modify"]):
        score += 0.25

    # Reasonable length
    if 100 < len(output) < 10000:
        score += 0.25

    return min(score, 1.0)


def score_instruction_following(result: dict) -> float:
    """Score an instruction-following result."""
    output = result.get("raw_output", "")
    if result.get("error"):
        return 0.0

    score = 0.0

    # Produced output
    if len(output.strip()) > 10:
        score += 0.3

    # Followed format constraints (heuristic)
    prompt = result.get("prompt_text", "")
    if "JSON" in prompt and ("{" in output and "}" in output):
        score += 0.4
    elif "function" in prompt.lower() and ("def " in output or "function " in output):
        score += 0.4
    else:
        score += 0.2

    # Reasonable length
    if len(output) < 5000:
        score += 0.3

    return min(score, 1.0)


SCORING_FUNCTIONS = {
    "code_generation": score_code_generation,
    "debugging": score_debugging,
    "fim": score_fim,
    "tool_use": score_tool_use,
    "repository_editing": score_repository_editing,
    "instruction_following": score_instruction_following,
}


# ---------------------------------------------------------------------------
# Licence and ecosystem scoring
# ---------------------------------------------------------------------------

def score_licence_ecosystem(candidate_data: dict) -> float:
    """Score a candidate's licence and ecosystem compatibility."""
    score = 0.0
    licence = candidate_data.get("licence", "").lower()

    # Licence scoring
    permissive = ["mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc"]
    if any(lic in licence for lic in permissive):
        score += 0.5

    # Architecture scoring (standard = better ecosystem)
    arch = candidate_data.get("architecture", "").lower()
    if "standard" in arch or "dense transformer" in arch:
        score += 0.3
    elif "custom" in arch:
        score += 0.1  # Penalty for custom architectures

    # trust_remote_code penalty
    if "trust_remote_code" in arch:
        score -= 0.1

    # Base score for being an available candidate
    score += 0.2

    return max(0.0, min(score, 1.0))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def load_results(candidate_id: str) -> list[dict]:
    """Load results for a candidate."""
    results_file = RESULTS_DIR / f"{candidate_id}.jsonl"
    if not results_file.exists():
        return []

    results = []
    with open(results_file) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def compute_candidate_score(
    candidate_id: str,
    candidate_data: dict,
    results: list[dict],
) -> CandidateScore:
    """Compute the weighted composite score for a candidate."""
    # Group results by category
    by_category = defaultdict(list)
    for r in results:
        by_category[r["category"]].append(r)

    # Score each dimension
    dimension_scores = {}

    for category, scorer in SCORING_FUNCTIONS.items():
        cat_results = by_category.get(category, [])
        if cat_results:
            scores = [scorer(r) for r in cat_results]
            dimension = CATEGORY_TO_DIMENSION.get(category, category)
            dimension_scores[dimension] = sum(scores) / len(scores)
        else:
            dimension = CATEGORY_TO_DIMENSION.get(category, category)
            dimension_scores[dimension] = 0.0

    # Add licence/ecosystem score
    dimension_scores["licence_ecosystem"] = score_licence_ecosystem(candidate_data)

    # Speed/memory score (normalised TPS)
    valid_results = [r for r in results if not r.get("error")]
    if valid_results:
        avg_tps = sum(r["tokens_per_second"] for r in valid_results) / len(valid_results)
        # Normalise: 30+ t/s = 1.0, 0 t/s = 0.0
        dimension_scores["speed_memory"] = min(avg_tps / 30.0, 1.0)
    else:
        avg_tps = 0.0
        dimension_scores["speed_memory"] = 0.0

    # Quantised performance (placeholder — same as code_correctness for now)
    dimension_scores["quantised_performance"] = dimension_scores.get(
        "code_correctness", 0.0
    )

    # Compute weighted total
    weighted_total = sum(
        dimension_scores.get(dim, 0.0) * weight
        for dim, weight in SCORING_WEIGHTS.items()
    )

    # Aggregate metrics
    avg_latency = (
        sum(r["latency_seconds"] for r in valid_results) / len(valid_results)
        if valid_results else 0.0
    )

    return CandidateScore(
        candidate_id=candidate_id,
        candidate_name=candidate_data.get("name", candidate_id),
        dimension_scores=dimension_scores,
        weighted_total=weighted_total,
        avg_tokens_per_second=avg_tps,
        avg_latency=avg_latency,
        total_prompts=len(results),
        total_errors=len(results) - len(valid_results),
    )


def generate_report(scores: list[CandidateScore], output_path: Optional[Path] = None):
    """Generate a markdown report."""
    # Sort by weighted total (descending)
    scores.sort(key=lambda s: s.weighted_total, reverse=True)

    lines = [
        "# Nova v12 Foundation Bake-Off Report",
        "",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "---",
        "",
        "## Ranking",
        "",
        "| Rank | Candidate | Weighted Score | Avg t/s | Errors |",
        "|---:|---|---:|---:|---:|",
    ]

    for i, s in enumerate(scores, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "")
        lines.append(
            f"| {i} {medal} | **{s.candidate_name}** | "
            f"{s.weighted_total:.3f} | {s.avg_tokens_per_second:.1f} | "
            f"{s.total_errors}/{s.total_prompts} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Dimension Breakdown",
        "",
    ])

    # Dimension header
    dimensions = list(SCORING_WEIGHTS.keys())
    header = "| Dimension | Weight |"
    separator = "|---|---:|"
    for s in scores:
        header += f" {s.candidate_name} |"
        separator += "---:|"
    lines.extend([header, separator])

    for dim in dimensions:
        weight = SCORING_WEIGHTS[dim]
        row = f"| {dim.replace('_', ' ').title()} | {weight:.0%} |"
        for s in scores:
            val = s.dimension_scores.get(dim, 0.0)
            row += f" {val:.3f} |"
        lines.append(row)

    # Weighted total row
    row = "| **WEIGHTED TOTAL** | **100%** |"
    for s in scores:
        row += f" **{s.weighted_total:.3f}** |"
    lines.append(row)

    lines.extend([
        "",
        "---",
        "",
        "## Performance Metrics",
        "",
        "| Candidate | Avg Latency (s) | Avg Tokens/s | Total Prompts | Errors |",
        "|---|---:|---:|---:|---:|",
    ])

    for s in scores:
        lines.append(
            f"| {s.candidate_name} | {s.avg_latency:.2f} | "
            f"{s.avg_tokens_per_second:.1f} | {s.total_prompts} | {s.total_errors} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Recommendation",
        "",
    ])

    if scores:
        winner = scores[0]
        lines.append(f"**Winner: {winner.candidate_name}** (score: {winner.weighted_total:.3f})")
        lines.append("")
        lines.append("This candidate should proceed as the foundation for Nova Code 4B.")

        if len(scores) > 1:
            runner_up = scores[1]
            gap = winner.weighted_total - runner_up.weighted_total
            if gap < 0.05:
                lines.append("")
                lines.append(
                    f"> ⚠️ **Close result.** The gap between {winner.candidate_name} and "
                    f"{runner_up.candidate_name} is only {gap:.3f}. "
                    f"Consider additional evaluation before committing."
                )

    lines.extend([
        "",
        "---",
        "",
        "## Scoring Methodology",
        "",
        "Weights follow Section 4 of the Nova v12 blueprint:",
        "",
    ])
    for dim, weight in SCORING_WEIGHTS.items():
        lines.append(f"- **{dim.replace('_', ' ').title()}**: {weight:.0%}")

    lines.extend([
        "",
        "Scores are normalised to [0, 1] per dimension.",
        "Weighted total is the sum of (dimension_score × weight).",
        "",
        "---",
        "",
        "*Amaura Labs — Building verifiable intelligence.*",
    ])

    report = "\n".join(lines)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)
        print(f"Report saved to {output_path}")
    else:
        print(report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Nova v12 Foundation Bake-Off Scorer"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate a full bake-off report",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for the report (default: stdout)",
    )

    args = parser.parse_args()

    if not args.report:
        parser.print_help()
        return

    # Load candidates
    with open(CANDIDATES_FILE) as f:
        candidates_data = yaml.safe_load(f)

    candidate_lookup = {
        c["id"]: c for c in candidates_data.get("candidates", [])
    }

    # Find all result files
    if not RESULTS_DIR.exists():
        print("No results found. Run run_bakeoff.py first.")
        sys.exit(1)

    result_files = list(RESULTS_DIR.glob("*.jsonl"))
    if not result_files:
        print("No result files found. Run run_bakeoff.py first.")
        sys.exit(1)

    # Compute scores
    scores = []
    for rf in result_files:
        candidate_id = rf.stem
        results = load_results(candidate_id)
        candidate_data = candidate_lookup.get(candidate_id, {"name": candidate_id})
        score = compute_candidate_score(candidate_id, candidate_data, results)
        scores.append(score)

    # Generate report
    output_path = Path(args.output) if args.output else None
    generate_report(scores, output_path)


if __name__ == "__main__":
    main()
