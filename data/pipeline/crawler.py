#!/usr/bin/env python3
"""
Nova v12 Data Pipeline — Code Crawler

Streams code from The Stack v2 (or other HF datasets) with licence
filtering, quality scoring, and token budget tracking.

Designed for streaming — does not download the full multi-TB corpus.

Usage:
    python crawler.py --config configs/phase1_pilot.yaml --output /path/to/output
    python crawler.py --language python --budget 30000000 --output /path/to/output
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALLOWED_LICENCES = {
    "mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause",
    "isc", "unlicense", "cc0-1.0",
}

# Language allocations from Section 7
DEFAULT_LANGUAGE_WEIGHTS = {
    "python": 0.25,
    "javascript": 0.125,
    "typescript": 0.125,
    "java": 0.10,
    "cpp": 0.10,
    "go": 0.075,
    "rust": 0.075,
    "sql": 0.05,
    "bash": 0.05,
    "other": 0.05,
}

# The Stack language directory names
LANGUAGE_DIRS = {
    "python": "data/python",
    "javascript": "data/javascript",
    "typescript": "data/typescript",
    "java": "data/java",
    "cpp": "data/c++",
    "go": "data/go",
    "rust": "data/rust",
    "sql": "data/sql",
    "bash": "data/shell",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CodeRecord:
    """A single code file record with full provenance."""
    repository: str
    commit: str
    path: str
    licence: str
    language: str
    content: str
    content_hash: str
    size_bytes: int
    token_count: int = 0
    quality_score: float = 0.0
    source_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class BudgetTracker:
    """Tracks token budgets per language."""
    budgets: dict[str, int]
    consumed: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        for lang in self.budgets:
            if lang not in self.consumed:
                self.consumed[lang] = 0

    def can_accept(self, language: str, tokens: int) -> bool:
        lang_key = language if language in self.budgets else "other"
        budget = self.budgets.get(lang_key, 0)
        return self.consumed.get(lang_key, 0) + tokens <= budget

    def consume(self, language: str, tokens: int):
        lang_key = language if language in self.budgets else "other"
        self.consumed[lang_key] = self.consumed.get(lang_key, 0) + tokens

    def is_complete(self) -> bool:
        return all(
            self.consumed.get(lang, 0) >= budget
            for lang, budget in self.budgets.items()
        )

    def progress(self) -> dict[str, str]:
        result = {}
        for lang, budget in self.budgets.items():
            consumed = self.consumed.get(lang, 0)
            pct = (consumed / budget * 100) if budget > 0 else 100
            result[lang] = f"{consumed:,}/{budget:,} ({pct:.1f}%)"
        return result

    @property
    def total_consumed(self) -> int:
        return sum(self.consumed.values())

    @property
    def total_budget(self) -> int:
        return sum(self.budgets.values())


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def estimate_token_count(text: str) -> int:
    """Rough token count estimate (4 chars ≈ 1 token for code)."""
    return max(1, len(text) // 4)


def precise_token_count(text: str, tokenizer) -> int:
    """Precise token count using the actual tokenizer."""
    if tokenizer is None:
        return estimate_token_count(text)
    return len(tokenizer.encode(text))


# ---------------------------------------------------------------------------
# Licence filtering
# ---------------------------------------------------------------------------

def is_licence_allowed(licence: str) -> bool:
    """Check if the licence is in the allowlist."""
    if not licence:
        return False
    return licence.lower().strip() in ALLOWED_LICENCES


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------

def compute_hash(content: str) -> str:
    """Compute SHA-256 hash of normalised content."""
    normalised = content.strip().replace("\r\n", "\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Basic quality checks (fast — applied during streaming)
# ---------------------------------------------------------------------------

def passes_basic_quality(content: str, language: str) -> bool:
    """Fast quality checks for streaming filter."""
    # Too short or too long
    if len(content) < 50 or len(content) > 500_000:
        return False

    lines = content.split("\n")

    # Too few lines
    if len(lines) < 3:
        return False

    # Average line too long (likely minified)
    avg_line_len = len(content) / len(lines)
    if avg_line_len > 200:
        return False

    # Too many empty lines (likely generated/padded)
    empty_ratio = sum(1 for l in lines if not l.strip()) / len(lines)
    if empty_ratio > 0.6:
        return False

    # Contains common auto-generated markers
    autogen_markers = [
        "auto-generated", "DO NOT EDIT", "generated by", "machine generated",
        "this file is generated", "autogenerated",
    ]
    first_lines = "\n".join(lines[:10]).lower()
    if any(marker.lower() in first_lines for marker in autogen_markers):
        return False

    return True


# ---------------------------------------------------------------------------
# Streaming from The Stack
# ---------------------------------------------------------------------------

def stream_the_stack(
    language: str,
    split: str = "train",
) -> Iterator[dict]:
    """Stream files from The Stack v2 for a given language."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: `datasets` library required. Install with: pip install datasets")
        sys.exit(1)

    data_dir = LANGUAGE_DIRS.get(language, f"data/{language}")

    print(f"  Streaming {language} from The Stack (dir: {data_dir})...")

    try:
        dataset = load_dataset(
            "bigcode/the-stack",
            data_dir=data_dir,
            split=split,
            streaming=True,
        )

        for example in dataset:
            yield example

    except Exception as e:
        print(f"  Warning: Could not stream {language}: {e}")
        print(f"  Have you accepted The Stack's terms on Hugging Face?")
        return


def stream_local_files(
    directory: str,
    language: str,
) -> Iterator[dict]:
    """Stream from a local directory of code files (fallback)."""
    extensions = {
        "python": [".py"],
        "javascript": [".js", ".mjs", ".cjs"],
        "typescript": [".ts", ".tsx"],
        "java": [".java"],
        "cpp": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
        "go": [".go"],
        "rust": [".rs"],
        "sql": [".sql"],
        "bash": [".sh", ".bash"],
    }

    exts = extensions.get(language, [f".{language}"])
    root = Path(directory)

    for path in root.rglob("*"):
        if path.is_file() and path.suffix in exts:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                yield {
                    "content": content,
                    "repository_name": str(root.name),
                    "path": str(path.relative_to(root)),
                    "license": "unknown",
                    "hexsha": "",
                }
            except Exception:
                continue


# ---------------------------------------------------------------------------
# Main crawl pipeline
# ---------------------------------------------------------------------------

def crawl(
    total_budget: int,
    language_weights: dict[str, float],
    output_dir: str,
    source: str = "the-stack",
    local_dir: Optional[str] = None,
    tokenizer=None,
):
    """Run the crawl pipeline with budget tracking."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Compute per-language budgets
    budgets = {
        lang: int(total_budget * weight)
        for lang, weight in language_weights.items()
    }
    tracker = BudgetTracker(budgets=budgets)

    # Deduplication set
    seen_hashes = set()

    # Stats
    stats = {
        "total_files_seen": 0,
        "rejected_licence": 0,
        "rejected_quality": 0,
        "rejected_duplicate": 0,
        "accepted": 0,
    }

    print("=" * 70)
    print("NOVA v12 DATA CRAWLER")
    print("=" * 70)
    print(f"Total budget: {total_budget:,} tokens")
    print(f"Output: {output_path}")
    print(f"Source: {source}")
    print()

    for language in language_weights:
        if language == "other":
            continue

        if not tracker.can_accept(language, 0):
            continue

        lang_budget = budgets.get(language, 0)
        if lang_budget <= 0:
            continue

        print(f"\n--- {language.upper()} (budget: {lang_budget:,} tokens) ---")

        output_file = output_path / f"{language}.jsonl"

        # Select source
        if source == "local" and local_dir:
            stream = stream_local_files(local_dir, language)
        else:
            stream = stream_the_stack(language)

        with open(output_file, "a") as f:
            for example in stream:
                stats["total_files_seen"] += 1

                content = example.get("content", "")
                licence = example.get("license", example.get("licence", ""))
                repo = example.get("repository_name", "unknown")
                path = example.get("path", "unknown")
                commit = example.get("hexsha", "")

                # Licence filter
                if source != "local" and not is_licence_allowed(licence):
                    stats["rejected_licence"] += 1
                    continue

                # Basic quality filter
                if not passes_basic_quality(content, language):
                    stats["rejected_quality"] += 1
                    continue

                # Deduplication
                content_hash = compute_hash(content)
                if content_hash in seen_hashes:
                    stats["rejected_duplicate"] += 1
                    continue
                seen_hashes.add(content_hash)

                # Token counting
                tokens = precise_token_count(content, tokenizer)

                # Budget check
                if not tracker.can_accept(language, tokens):
                    print(f"  Budget exhausted for {language}")
                    break

                # Create record
                record = CodeRecord(
                    repository=repo,
                    commit=commit,
                    path=path,
                    licence=licence if source != "local" else "local",
                    language=language,
                    content=content,
                    content_hash=content_hash,
                    size_bytes=len(content.encode("utf-8")),
                    token_count=tokens,
                    source_id=f"{repo}/{path}@{commit[:8] if commit else 'local'}",
                )

                # Write
                f.write(record.to_jsonl() + "\n")
                tracker.consume(language, tokens)
                stats["accepted"] += 1

                # Progress
                if stats["accepted"] % 1000 == 0:
                    pct = tracker.total_consumed / tracker.total_budget * 100
                    print(
                        f"  Accepted: {stats['accepted']:,} | "
                        f"Tokens: {tracker.total_consumed:,}/{tracker.total_budget:,} "
                        f"({pct:.1f}%)"
                    )

                # Check total budget
                if tracker.is_complete():
                    break

        if tracker.is_complete():
            break

    # Final report
    print(f"\n{'='*70}")
    print("CRAWL COMPLETE")
    print(f"{'='*70}")
    print(f"Files seen:        {stats['total_files_seen']:,}")
    print(f"Rejected (licence): {stats['rejected_licence']:,}")
    print(f"Rejected (quality): {stats['rejected_quality']:,}")
    print(f"Rejected (dupe):    {stats['rejected_duplicate']:,}")
    print(f"Accepted:           {stats['accepted']:,}")
    print(f"\nToken progress:")
    for lang, prog in tracker.progress().items():
        print(f"  {lang}: {prog}")
    print(f"\nTotal: {tracker.total_consumed:,}/{tracker.total_budget:,}")

    # Save stats
    stats_file = output_path / "crawl_stats.json"
    with open(stats_file, "w") as f:
        json.dump({
            **stats,
            "token_progress": tracker.progress(),
            "total_tokens": tracker.total_consumed,
            "total_budget": tracker.total_budget,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nova v12 Data Crawler")
    parser.add_argument("--budget", type=int, default=50_000_000,
                        help="Total token budget (default: 50M for pilot)")
    parser.add_argument("--output", type=str, required=True,
                        help="Output directory for crawled data")
    parser.add_argument("--language", type=str,
                        help="Crawl only a specific language")
    parser.add_argument("--source", choices=["the-stack", "local"],
                        default="the-stack", help="Data source")
    parser.add_argument("--local-dir", type=str,
                        help="Local directory for source=local")
    parser.add_argument("--config", type=str,
                        help="YAML config file (overrides CLI args)")

    args = parser.parse_args()

    # Load config
    language_weights = DEFAULT_LANGUAGE_WEIGHTS.copy()

    if args.config:
        import yaml
        with open(args.config) as f:
            config = yaml.safe_load(f)
        args.budget = config.get("total_budget", args.budget)
        language_weights = config.get("language_weights", language_weights)

    if args.language:
        # Single language mode
        weight = language_weights.get(args.language, 1.0)
        language_weights = {args.language: weight}

    crawl(
        total_budget=args.budget,
        language_weights=language_weights,
        output_dir=args.output,
        source=args.source,
        local_dir=args.local_dir,
    )


if __name__ == "__main__":
    main()
