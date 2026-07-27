#!/usr/bin/env python3
"""
audit_noncoding.py — Non-Coding Training Data Audit (Priority 2)

Analyzes the training dataset to determine whether <<RESPONSE>> examples
are sufficient in count and diversity to teach the model when to use the
explanation format vs the code format.

Outputs a structured report with:
  - Distribution of <<FILES>> vs <<RESPONSE>> vs <<CLARIFICATION>> examples
  - Verbatim list of all <<RESPONSE>> user prompts
  - Phrasing diversity analysis
  - Recommendation on whether a targeted retrain is needed
"""

import json
import re
import sys
from collections import Counter

DATASET_PATH = "/Users/ashishsingh/Desktop/nova-1.5b/dataset_nova3b_v8.jsonl"

# Phrasing patterns that should be represented in <<RESPONSE>> examples
EXPECTED_PHRASINGS = {
    "Explain": re.compile(r"^Explain\b", re.IGNORECASE),
    "What is/are": re.compile(r"^What\s+(?:is|are)\b", re.IGNORECASE),
    "Summarize": re.compile(r"^Summarize\b", re.IGNORECASE),
    "How does X work": re.compile(r"^How\s+(?:does|do)\b", re.IGNORECASE),
    "Differences between": re.compile(r"(?:difference|differences|compare)\s+(?:between|of)\b", re.IGNORECASE),
    "List/Describe": re.compile(r"^(?:List|Describe)\b", re.IGNORECASE),
    "Give me/overview": re.compile(r"(?:Give\s+me|overview|brief)\b", re.IGNORECASE),
    "Define": re.compile(r"^Define\b", re.IGNORECASE),
    "When should/Why": re.compile(r"^(?:When\s+should|Why)\b", re.IGNORECASE),
    "Tell me about": re.compile(r"^Tell\s+me\s+(?:about|how)", re.IGNORECASE),
}


def load_dataset(path):
    """Load JSONL dataset and return list of (user_prompt, assistant_response) tuples."""
    examples = []
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                msgs = d.get("messages", [])
                user_msg = ""
                asst_msg = ""
                for m in msgs:
                    if m.get("role") == "user":
                        user_msg = m.get("content", "")
                    elif m.get("role") == "assistant":
                        asst_msg = m.get("content", "")
                examples.append((user_msg, asst_msg))
            except json.JSONDecodeError:
                print(f"  ⚠️  Skipping malformed JSON at line {line_num}")
    return examples


def classify_example(asst_response):
    """Classify an assistant response by its output format."""
    if "<<RESPONSE>>" in asst_response:
        return "RESPONSE"
    if "<<CLARIFICATION>>" in asst_response:
        return "CLARIFICATION"
    if "<<FILES>>" in asst_response:
        return "FILES"
    return "UNKNOWN"


def analyze_phrasing(prompts):
    """Check which phrasing patterns are covered by the given prompts."""
    covered = {}
    uncovered = []
    for name, pattern in EXPECTED_PHRASINGS.items():
        matches = [p for p in prompts if pattern.search(p)]
        if matches:
            covered[name] = matches
        else:
            uncovered.append(name)
    return covered, uncovered


def main():
    print("═" * 70)
    print("  Non-Coding Training Data Audit")
    print("═" * 70)

    examples = load_dataset(DATASET_PATH)
    total = len(examples)
    print(f"\n  Dataset: {DATASET_PATH}")
    print(f"  Total examples: {total}")

    # ── Distribution ─────────────────────────────────────────────────────
    categories = Counter()
    response_prompts = []
    files_prompts = []
    clarification_prompts = []

    for user_msg, asst_msg in examples:
        cat = classify_example(asst_msg)
        categories[cat] += 1
        if cat == "RESPONSE":
            response_prompts.append(user_msg)
        elif cat == "FILES":
            files_prompts.append(user_msg)
        elif cat == "CLARIFICATION":
            clarification_prompts.append(user_msg)

    print("\n  ── Output Format Distribution ──")
    for cat in ["FILES", "CLARIFICATION", "RESPONSE", "UNKNOWN"]:
        count = categories.get(cat, 0)
        pct = (count / total * 100) if total > 0 else 0
        bar = "█" * int(pct / 2) + "░" * (50 - int(pct / 2))
        print(f"  {cat:15s} {count:5d} ({pct:5.1f}%)  {bar}")

    ratio = categories.get("FILES", 0) / max(categories.get("RESPONSE", 0), 1)
    print(f"\n  FILES:RESPONSE ratio = {ratio:.0f}:1")

    # ── All <<RESPONSE>> prompts ─────────────────────────────────────────
    print(f"\n  ── All <<RESPONSE>> Training Prompts ({len(response_prompts)}) ──")
    for i, p in enumerate(response_prompts, 1):
        print(f"  {i:2d}. {p[:100]}")

    # ── Phrasing diversity analysis ──────────────────────────────────────
    print(f"\n  ── Phrasing Diversity Analysis ──")
    covered, uncovered = analyze_phrasing(response_prompts)

    print(f"  Covered phrasings ({len(covered)}/{len(EXPECTED_PHRASINGS)}):")
    for name, matches in covered.items():
        print(f"    ✅ {name} ({len(matches)} example(s))")

    if uncovered:
        print(f"\n  MISSING phrasings ({len(uncovered)}):")
        for name in uncovered:
            print(f"    ❌ {name}")

    # ── Recommendation ───────────────────────────────────────────────────
    response_pct = categories.get("RESPONSE", 0) / total * 100 if total > 0 else 0
    coverage_pct = len(covered) / len(EXPECTED_PHRASINGS) * 100

    print(f"\n  ── Recommendation ──")
    print(f"  <<RESPONSE>> percentage: {response_pct:.1f}% (target: ≥ 5%)")
    print(f"  Phrasing coverage: {coverage_pct:.0f}% ({len(covered)}/{len(EXPECTED_PHRASINGS)} patterns)")

    needs_retrain = False
    reasons = []

    if response_pct < 5.0:
        needs_retrain = True
        target_count = int(total * 0.05)
        deficit = target_count - categories.get("RESPONSE", 0)
        reasons.append(
            f"<<RESPONSE>> examples are {response_pct:.1f}% of dataset (need ≥ 5%). "
            f"Add ~{deficit} more non-coding examples."
        )

    if len(uncovered) > 2:
        needs_retrain = True
        reasons.append(
            f"Missing {len(uncovered)} phrasing patterns: {uncovered}. "
            f"Add examples for each missing pattern."
        )

    if needs_retrain:
        print(f"\n  ⚠️  RETRAIN RECOMMENDED")
        for r in reasons:
            print(f"     • {r}")

        # Generate suggested prompts for missing phrasings
        SUGGESTED_PROMPTS = {
            "Summarize": [
                "Summarize how OAuth 2.0 works in simple terms.",
                "Summarize the key features of GraphQL.",
                "Summarize the purpose of Kubernetes in one paragraph.",
            ],
            "How does X work": [
                "How does DNS resolution work?",
                "How does garbage collection work in Java?",
                "How does HTTPS encryption work?",
            ],
            "Differences between": [
                "What are the differences between SQL and NoSQL databases?",
                "Compare REST and gRPC.",
                "What's the difference between a process and a thread?",
            ],
            "Define": [
                "Define the term 'eventual consistency'.",
                "Define what a load balancer does.",
                "Define the concept of 'sharding' in databases.",
            ],
            "When should/Why": [
                "When should you use a message queue like RabbitMQ?",
                "Why is immutability important in functional programming?",
                "When should you use WebSockets instead of HTTP polling?",
            ],
            "Tell me about": [
                "Tell me about the observer design pattern.",
                "Tell me how rate limiting works in APIs.",
                "Tell me about the differences between OAuth and SAML.",
            ],
        }

        if uncovered:
            print(f"\n  ── Suggested New Training Prompts ──")
            for pattern_name in uncovered:
                if pattern_name in SUGGESTED_PROMPTS:
                    print(f"\n  Pattern: {pattern_name}")
                    for sp in SUGGESTED_PROMPTS[pattern_name]:
                        print(f"    + {sp}")
    else:
        print(f"\n  ✅ No retrain needed — coverage is adequate.")

    print("\n" + "═" * 70)
    return 0 if not needs_retrain else 1


if __name__ == "__main__":
    sys.exit(main())
