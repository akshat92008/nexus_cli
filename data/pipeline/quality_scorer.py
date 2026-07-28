#!/usr/bin/env python3
"""
Nova v12 Data Pipeline — Quality Scorer

Scores code files on multiple quality dimensions to determine inclusion
in the training corpus. Higher score = higher quality.

Scoring dimensions:
1. AST parse success (syntactic validity)
2. Comment-to-code ratio
3. Identifier quality (meaningful names)
4. Complexity (not too simple, not too complex)
5. Auto-generated detection
6. Test presence
7. Documentation quality

Usage:
    python quality_scorer.py --input /path/to/data.jsonl --output /path/to/scored.jsonl
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Language-specific AST parsers
# ---------------------------------------------------------------------------

def parse_python(content: str) -> bool:
    """Check if Python code parses successfully."""
    try:
        ast.parse(content)
        return True
    except SyntaxError:
        return False


def parse_generic(content: str, language: str) -> bool:
    """Basic syntactic checks for non-Python languages."""
    # Check balanced braces/brackets
    if language in ("javascript", "typescript", "java", "cpp", "go", "rust"):
        opens = content.count("{") + content.count("(") + content.count("[")
        closes = content.count("}") + content.count(")") + content.count("]")
        if abs(opens - closes) > 2:
            return False

    # Check for common syntax patterns
    if language in ("javascript", "typescript"):
        if not re.search(r'(function|const|let|var|class|import|export|=>)', content):
            return False

    elif language == "java":
        if not re.search(r'(class|interface|enum|import|package)', content):
            return False

    elif language == "go":
        if not re.search(r'(package|func|import|type|struct)', content):
            return False

    elif language == "rust":
        if not re.search(r'(fn|use|mod|struct|enum|impl|trait|pub)', content):
            return False

    return True


def check_ast(content: str, language: str) -> float:
    """Score AST parse success. Returns 0.0 or 1.0."""
    if language == "python":
        return 1.0 if parse_python(content) else 0.0
    return 1.0 if parse_generic(content, language) else 0.0


# ---------------------------------------------------------------------------
# Comment-to-code ratio
# ---------------------------------------------------------------------------

def compute_comment_ratio(content: str, language: str) -> float:
    """Compute comment-to-code ratio. Ideal range: 0.05–0.40."""
    lines = content.split("\n")
    total = len(lines)
    if total == 0:
        return 0.0

    comment_lines = 0
    in_block_comment = False

    for line in lines:
        stripped = line.strip()

        if language == "python":
            if stripped.startswith("#"):
                comment_lines += 1
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                in_block_comment = not in_block_comment
                comment_lines += 1
            elif in_block_comment:
                comment_lines += 1

        elif language in ("javascript", "typescript", "java", "cpp", "go", "rust"):
            if stripped.startswith("//"):
                comment_lines += 1
            elif "/*" in stripped:
                in_block_comment = True
                comment_lines += 1
            elif "*/" in stripped:
                in_block_comment = False
                comment_lines += 1
            elif in_block_comment:
                comment_lines += 1

        elif language == "sql":
            if stripped.startswith("--"):
                comment_lines += 1

        elif language == "bash":
            if stripped.startswith("#") and not stripped.startswith("#!"):
                comment_lines += 1

    ratio = comment_lines / total
    return ratio


def score_comment_ratio(ratio: float) -> float:
    """Score the comment ratio. Ideal: 0.05–0.30."""
    if ratio < 0.01:
        return 0.3  # No comments at all
    elif 0.01 <= ratio < 0.05:
        return 0.6
    elif 0.05 <= ratio <= 0.30:
        return 1.0  # Ideal range
    elif 0.30 < ratio <= 0.50:
        return 0.7  # Somewhat over-commented
    else:
        return 0.3  # Excessive comments (likely docs, not code)


# ---------------------------------------------------------------------------
# Identifier quality
# ---------------------------------------------------------------------------

def score_identifier_quality(content: str) -> float:
    """Score identifier naming quality. Penalises single-char and cryptic names."""
    # Extract identifiers
    identifiers = re.findall(r'\b([a-zA-Z_]\w*)\b', content)

    if not identifiers:
        return 0.5

    # Filter out keywords and common tokens
    keywords = {
        "if", "else", "for", "while", "return", "def", "class", "import",
        "from", "in", "not", "and", "or", "is", "None", "True", "False",
        "function", "const", "let", "var", "new", "this", "self",
        "public", "private", "static", "void", "int", "str", "bool",
        "try", "except", "catch", "finally", "throw", "raise",
    }

    user_identifiers = [
        ident for ident in identifiers
        if ident not in keywords and len(ident) > 0
    ]

    if not user_identifiers:
        return 0.5

    # Score: proportion of meaningful (>2 char) identifiers
    meaningful = sum(1 for i in user_identifiers if len(i) > 2)
    ratio = meaningful / len(user_identifiers)

    return min(1.0, ratio + 0.2)  # Slight boost — single-char loop vars are OK


# ---------------------------------------------------------------------------
# Complexity scoring
# ---------------------------------------------------------------------------

def score_complexity(content: str) -> float:
    """Score code complexity. Penalises trivially simple and overly complex code."""
    lines = [l for l in content.split("\n") if l.strip()]
    num_lines = len(lines)

    if num_lines < 5:
        return 0.3  # Trivially short
    elif num_lines < 10:
        return 0.6  # Short but might be useful
    elif 10 <= num_lines <= 500:
        return 1.0  # Good range
    elif 500 < num_lines <= 2000:
        return 0.8  # Long but acceptable
    else:
        return 0.5  # Very long — might be generated or data

    return 0.5


# ---------------------------------------------------------------------------
# Auto-generated detection
# ---------------------------------------------------------------------------

def is_auto_generated(content: str) -> bool:
    """Detect auto-generated code."""
    markers = [
        "auto-generated", "do not edit", "generated by",
        "machine generated", "this file is generated",
        "autogenerated", "code generated", "automatically generated",
        "generated from", "generated with",
        # Common tool signatures
        "protobuf", "swagger-codegen", "openapi-generator",
        "grpc-generated", "thrift-generated",
    ]

    # Check first 20 lines
    first_lines = "\n".join(content.split("\n")[:20]).lower()
    return any(marker in first_lines for marker in markers)


# ---------------------------------------------------------------------------
# Test presence
# ---------------------------------------------------------------------------

def has_tests(content: str, language: str, path: str = "") -> float:
    """Score whether the code contains or is accompanied by tests."""
    score = 0.0

    # Is this a test file?
    if any(marker in path.lower() for marker in ["test_", "_test.", "test.", "spec."]):
        score += 0.5

    # Contains test patterns
    if language == "python":
        if re.search(r'(def test_|class Test|unittest|pytest|assert\s)', content):
            score += 0.5
    elif language in ("javascript", "typescript"):
        if re.search(r'(describe\(|it\(|test\(|expect\(|jest|mocha|vitest)', content):
            score += 0.5
    elif language == "java":
        if re.search(r'(@Test|junit|assertThat|assertEquals)', content):
            score += 0.5
    elif language == "go":
        if re.search(r'(func Test|testing\.T|t\.Run|t\.Error)', content):
            score += 0.5
    elif language == "rust":
        if re.search(r'(#\[test\]|#\[cfg\(test\)\]|assert_eq!|assert!)', content):
            score += 0.5

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------

def score_file(
    content: str,
    language: str,
    path: str = "",
) -> dict:
    """Compute composite quality score for a code file.
    
    Returns a dict with individual dimension scores and the composite score.
    """
    scores = {}

    # 1. AST parse (weight: 0.25)
    scores["ast_parse"] = check_ast(content, language)

    # 2. Comment ratio (weight: 0.15)
    ratio = compute_comment_ratio(content, language)
    scores["comment_ratio"] = score_comment_ratio(ratio)
    scores["raw_comment_ratio"] = ratio

    # 3. Identifier quality (weight: 0.15)
    scores["identifier_quality"] = score_identifier_quality(content)

    # 4. Complexity (weight: 0.15)
    scores["complexity"] = score_complexity(content)

    # 5. Not auto-generated (weight: 0.15)
    scores["not_generated"] = 0.0 if is_auto_generated(content) else 1.0

    # 6. Test presence (weight: 0.10)
    scores["test_presence"] = has_tests(content, language, path)

    # 7. Documentation (weight: 0.05)
    has_docstring = bool(re.search(r'("""|\'\'\'|/\*\*|\* @param|///)', content))
    scores["documentation"] = 1.0 if has_docstring else 0.3

    # Composite score
    weights = {
        "ast_parse": 0.25,
        "comment_ratio": 0.15,
        "identifier_quality": 0.15,
        "complexity": 0.15,
        "not_generated": 0.15,
        "test_presence": 0.10,
        "documentation": 0.05,
    }

    composite = sum(
        scores.get(dim, 0) * weight
        for dim, weight in weights.items()
    )
    scores["composite"] = composite

    return scores


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Nova v12 Quality Scorer")
    parser.add_argument("--input", type=str, required=True,
                        help="Input JSONL file")
    parser.add_argument("--output", type=str, required=True,
                        help="Output JSONL file with quality scores")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="Minimum composite score to keep (default: 0.70)")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    kept = 0
    rejected = 0

    print(f"Scoring {input_path.name} (threshold: {args.threshold})...")

    with open(input_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue

            total += 1
            record = json.loads(line)

            content = record.get("content", "")
            language = record.get("language", "python")
            path = record.get("path", "")

            scores = score_file(content, language, path)
            record["quality_scores"] = scores
            record["quality_score"] = scores["composite"]

            if scores["composite"] >= args.threshold:
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1
            else:
                rejected += 1

            if total % 5000 == 0:
                print(f"  Processed: {total:,} | Kept: {kept:,} | Rejected: {rejected:,}")

    print(f"\nDone. Total: {total:,} | Kept: {kept:,} | Rejected: {rejected:,}")
    print(f"Keep rate: {kept/max(1,total)*100:.1f}%")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
