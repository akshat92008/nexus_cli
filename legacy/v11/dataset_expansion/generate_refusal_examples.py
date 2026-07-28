#!/usr/bin/env python3
"""
dataset_expansion/generate_refusal_examples.py

Expands the 10 hand-authored seed refusal examples into a full ~50–75 example dataset.

Strategy:
  - Varies domain (backend, ml, infra, mobile, security, data, web3, architecture)
  - Varies vagueness pattern (missing stack, missing scale, missing scope, missing files)
  - Varies prompt tone (formal, messy/casual, urgent, JIRA-style)
  - Generates responses deterministically from a template — no LLM needed for this pass

Output: dataset_expansion/refusal_examples.jsonl

Usage:
    python3 dataset_expansion/generate_refusal_examples.py
    python3 dataset_expansion/generate_refusal_examples.py --count 75 --output custom_path.jsonl

Part of the Nova model family by Amaura.
"""

import json
import random
import argparse
from pathlib import Path
from typing import List, Dict, Tuple

# Import seeds for quality reference
import sys, os
sys.path.insert(0, str(Path(__file__).parent))
from refusal_seeds import REFUSAL_SEEDS, to_jsonl_entry as seed_to_entry


# ═══════════════════════════════════════════════════════════════════════════════
# Domain Templates
# ═══════════════════════════════════════════════════════════════════════════════

DOMAINS = {
    "backend": {
        "vague_prompts": [
            "Build a REST API for {app_type}.",
            "Create a backend for {app_type}.",
            "Implement a server for {app_type}.",
            "We need a backend service for {app_type}, make it production-ready.",
            "yo can you set up the backend for {app_type}? needs to be fast",
            "URGENT: need backend for {app_type} by tomorrow, make it scalable",
            "Hey nova, build out our {app_type} backend please",
            "JIRA-1234: Backend implementation for {app_type}. Make it secure.",
        ],
        "app_types": [
            "a task management app", "an e-commerce platform",
            "a social media platform", "a ride-sharing app",
            "a food delivery service", "a booking system",
            "a fintech application", "a healthcare portal",
            "a real-time analytics dashboard", "a SaaS product",
        ],
        "missing_items": ["stack", "endpoints", "auth method", "database"],
        "questions": [
            ("What language/framework?", "(Python/FastAPI, Node/Express, Go/Gin, Ruby/Rails?)"),
            ("Which endpoints?", "(e.g., POST /auth/login, GET /users/{id}, POST /orders?)"),
            ("Authentication?", "(JWT, OAuth2, session cookies, API key?)"),
            ("Which files to create?", "(e.g., src/api.py, routes/orders.js, handlers/user.go?)"),
        ],
    },
    "ml": {
        "vague_prompts": [
            "Create an ML model that predicts {ml_target}.",
            "Build a machine learning pipeline for {ml_target}.",
            "Implement an AI system to predict {ml_target}.",
            "We need an ML solution for {ml_target} — make it accurate.",
            "train a model to predict {ml_target} as fast as possible",
            "URGENT: need ML pipeline for {ml_target}. 99% accuracy required.",
        ],
        "app_types": [
            "customer churn", "sales forecasting",
            "fraud detection", "demand prediction",
            "user lifetime value", "click-through rate",
            "anomaly detection", "document classification",
        ],
        "missing_items": ["data format", "model type", "evaluation metric", "output file"],
        "questions": [
            ("What is the input data?", "(CSV schema? pandas DataFrame? columns?)"),
            ("Which model type?", "(logistic regression, XGBoost, neural network, LSTM?)"),
            ("What evaluation metric?", "(AUC-ROC, F1, precision@recall, RMSE?)"),
            ("What file to create?", "(src/model.py, notebooks/train.ipynb, pipeline/train.py?)"),
        ],
    },
    "infra": {
        "vague_prompts": [
            "Set up monitoring for our {infra_type}.",
            "Add observability to our {infra_type}.",
            "Implement logging and tracing for {infra_type}.",
            "Make our {infra_type} production-ready with proper monitoring.",
            "yo we need monitoring for {infra_type} asap",
        ],
        "app_types": [
            "microservices", "API gateway", "data pipeline",
            "Kubernetes cluster", "serverless functions",
            "message queue system", "batch processing job",
        ],
        "missing_items": ["stack", "metrics", "storage backend", "instrumentation language"],
        "questions": [
            ("What observability stack?", "(Prometheus+Grafana, Datadog, OpenTelemetry, CloudWatch?)"),
            ("Which metrics to collect?", "(latency p99, error rate, throughput, custom business metrics?)"),
            ("What language to instrument?", "(Python, Go, Node.js?)"),
            ("Which file to create/modify?", "(src/metrics.py, middleware/tracing.go, observability/setup.js?)"),
        ],
    },
    "security": {
        "vague_prompts": [
            "Make our {security_target} more secure.",
            "Add security to our {security_target}.",
            "Harden the {security_target} for production.",
            "Implement security best practices for {security_target}.",
            "URGENT: our {security_target} is vulnerable, fix it",
        ],
        "app_types": [
            "authentication system", "API endpoints",
            "user data storage", "file upload system",
            "admin panel", "payment processing", "session management",
        ],
        "missing_items": ["threat model", "specific vulnerability", "language", "files to modify"],
        "questions": [
            ("What threat are you addressing?", "(SQL injection, XSS, CSRF, auth bypass, data leak?)"),
            ("What language?", "(Python, Node.js, Go, PHP?)"),
            ("Which specific files?", "(src/auth.py, routes/api.js, middleware/auth.go?)"),
            ("What's the current implementation?", "(share the existing code or describe it)"),
        ],
    },
    "mobile": {
        "vague_prompts": [
            "Build a mobile app for {mobile_target}.",
            "Create the app for {mobile_target}.",
            "Implement a mobile solution for {mobile_target}.",
            "We need a mobile app for {mobile_target} with a great UX.",
        ],
        "app_types": [
            "fitness tracking", "expense tracking",
            "recipe management", "habit building",
            "language learning", "meditation",
            "task management", "event planning",
        ],
        "missing_items": ["platform", "framework", "specific screen", "backend"],
        "questions": [
            ("iOS, Android, or cross-platform?", "(Swift/UIKit, Kotlin, React Native, Flutter?)"),
            ("Which specific screen/component?", "(login screen, dashboard, settings, onboarding?)"),
            ("Which file to create?", "(LoginViewController.swift, screens/HomeScreen.tsx, lib/main.dart?)"),
            ("Is there an existing backend?", "(or do you need API calls implemented too?)"),
        ],
    },
    "data": {
        "vague_prompts": [
            "Build a data pipeline for {data_target}.",
            "Create an ETL process for {data_target}.",
            "Process and transform {data_target} data.",
            "We need data processing for {data_target}.",
        ],
        "app_types": [
            "user events", "product catalog",
            "financial transactions", "sensor readings",
            "log files", "social media posts",
            "e-commerce orders", "healthcare records",
        ],
        "missing_items": ["source format", "destination", "transformation logic", "schedule"],
        "questions": [
            ("What is the source format?", "(CSV, JSON, Parquet, database table, API endpoint?)"),
            ("Where does data go?", "(PostgreSQL, BigQuery, S3, Elasticsearch, Kafka topic?)"),
            ("What transformations are needed?", "(filtering, aggregation, normalization, joins?)"),
            ("Which file to create?", "(pipeline/etl.py, dags/transform.py, jobs/process.go?)"),
        ],
    },
}

TONE_PREFIXES = {
    "formal": "",
    "messy": "hey nova, ",
    "urgent": "URGENT: ",
    "jira": "JIRA-{ticket}: ",
    "casual": "yo can you ",
}

TICKET_NUMBERS = [f"{random.randint(100, 9999)}" for _ in range(200)]


# ═══════════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════════

def build_clarification_response(missing_items: List[str], questions: List[Tuple[str, str]]) -> str:
    """Build a structured <<CLARIFICATION>> response."""
    missing_str = ", ".join(missing_items[:3])

    lines = [
        f"<<THINKING>>",
        f"Task is underspecified. Missing: {missing_str}.",
        "",
        f"<<CLARIFICATION>>",
        f"I need more information before writing code:",
    ]
    for i, (q, hint) in enumerate(questions, 1):
        lines.append(f"{i}. {q} {hint}")

    lines += [
        "",
        "<<FILES>>",
        "(none — clarification required)",
        "",
        "<<TEST_COMMAND>>",
        "none",
    ]
    return "\n".join(lines)


def generate_refusal_examples(count: int = 65, seed: int = 42) -> List[dict]:
    """Generate a dataset of refusal/clarification examples."""
    random.seed(seed)

    examples = []

    # Start with the 10 human-authored seeds (always included)
    for s in REFUSAL_SEEDS:
        examples.append(seed_to_entry(s))

    remaining = count - len(REFUSAL_SEEDS)
    domain_names = list(DOMAINS.keys())

    for _ in range(remaining):
        domain_name = random.choice(domain_names)
        domain = DOMAINS[domain_name]

        # Select vague prompt template and app type
        prompt_template = random.choice(domain["vague_prompts"])
        app_type = random.choice(domain["app_types"])

        # Apply tone
        tone = random.choice(list(TONE_PREFIXES.keys()))
        prefix = TONE_PREFIXES[tone]
        if tone == "jira":
            prefix = prefix.format(ticket=random.choice(TICKET_NUMBERS))

        # Build prompt
        raw_prompt = prompt_template.format(
            app_type=app_type,
            ml_target=app_type,
            infra_type=app_type,
            security_target=app_type,
            mobile_target=app_type,
            data_target=app_type,
        )

        # Add tone prefix (avoid double-capitalizing)
        if tone in ("messy", "jira", "casual"):
            prompt = prefix + raw_prompt.lower()[0] + raw_prompt[1:]
        elif tone == "urgent":
            prompt = prefix + raw_prompt
        else:
            prompt = raw_prompt

        # Build response
        missing = random.sample(domain["missing_items"], min(3, len(domain["missing_items"])))
        q_count = min(4, len(domain["questions"]))
        questions = random.sample(domain["questions"], q_count)
        response = build_clarification_response(missing, questions)

        examples.append({
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ],
            "metadata": {
                "category": "refusal_clarification",
                "domain": domain_name,
                "tone": tone,
                "missing_info": missing,
                "version": "v1_generated",
            }
        })

    return examples


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate refusal/clarification training examples")
    parser.add_argument("--count", type=int, default=65,
                        help="Total examples to generate (default: 65, includes 10 seeds)")
    parser.add_argument("--output", type=str,
                        default=str(Path(__file__).parent / "refusal_examples.jsonl"),
                        help="Output JSONL file path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--preview", action="store_true", help="Print first 5 examples and exit")
    args = parser.parse_args()

    print(f"Generating {args.count} refusal/clarification examples...")
    examples = generate_refusal_examples(count=args.count, seed=args.seed)

    if args.preview:
        print(f"\nPreview of first 5 examples:")
        for ex in examples[:5]:
            print(f"\nPrompt: {ex['messages'][0]['content']}")
            print(f"Response (first 200): {ex['messages'][1]['content'][:200]}...")
        print(f"\nTotal: {len(examples)}")
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"✅ Wrote {len(examples)} examples to {output_path}")

    # Stats
    from collections import Counter
    domains = Counter(ex["metadata"]["domain"] for ex in examples)
    tones = Counter(ex["metadata"].get("tone", "seed") for ex in examples)
    print(f"\nDomain distribution: {dict(domains)}")
    print(f"Tone distribution: {dict(tones)}")

    # Quick format validation
    print("\nRunning format check on all examples...")
    format_errors = 0
    for ex in examples:
        response = ex["messages"][1]["content"]
        has_thinking = "<<THINKING>>" in response
        has_clarification = "<<CLARIFICATION>>" in response
        has_files = "<<FILES>>" in response
        has_test = "<<TEST_COMMAND>>" in response
        if not all([has_thinking, has_clarification, has_files, has_test]):
            format_errors += 1
    if format_errors == 0:
        print("✅ All examples pass format check.")
    else:
        print(f"⚠️  {format_errors} examples have format errors.")


if __name__ == "__main__":
    main()
