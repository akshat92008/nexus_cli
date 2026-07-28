#!/usr/bin/env python3
"""
dataset_expansion/generate_multifile_examples.py

Expands the 12 hand-authored multi-file seeds into a full ~50–75 example dataset.

THREE-TRACK SOURCING STRATEGY:
  Track 1 — Seeds (always included, ~12 examples):
      The 12 hand-authored gold examples from multifile_seeds.py.

  Track 2 — Synthetic from templates (~30-40 examples):
      Programmatically varies the 12 seeds:
        - Different project types (API, CLI, package, service)
        - Different file counts (2, 3, 4, 5)
        - Different languages (JS, TS, Go, CSS, mixed)
        - Different action types (CREATE, MODIFY, split refactors)
      Does NOT use an LLM — generates from structural templates.

  Track 3 — LLM-generated (optional, ~10-20 examples):
      Uses DeepSeek/GPT-4o-mini to generate additional high-quality examples.
      Triggered only if --use-llm flag is set AND DEEPSEEK_API_KEY is in env.
      Falls back gracefully to Track 2 only if API is unavailable.

Output: dataset_expansion/multifile_examples.jsonl

Usage:
    python3 dataset_expansion/generate_multifile_examples.py
    python3 dataset_expansion/generate_multifile_examples.py --count 70 --use-llm
    python3 dataset_expansion/generate_multifile_examples.py --preview

Part of the Nova model family by Amaura.
"""

import json
import random
import argparse
import os
from pathlib import Path
from typing import List, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent))
from multifile_seeds import MULTIFILE_SEEDS, to_jsonl_entry as seed_to_entry


# ═══════════════════════════════════════════════════════════════════════════════
# Track 2: Structural Templates
# ═══════════════════════════════════════════════════════════════════════════════

# Project archetypes — each defines a coherent multi-file project pattern
PROJECT_ARCHETYPES = [

    # ── JavaScript ─────────────────────────────────────────────────────────────
    {
        "lang": "javascript",
        "action": "CREATE",
        "file_count": 3,
        "project_type": "Express middleware chain",
        "prompt_template": "Create an Express.js {project} with three files: `{f1}` ({f1_desc}), `{f2}` ({f2_desc}), and `{f3}` ({f3_desc}).",
        "variants": [
            {
                "project": "rate limiter middleware",
                "f1": "middleware/rateLimiter.js", "f1_desc": "sliding window rate limiter",
                "f2": "middleware/ipBlocker.js", "f2_desc": "IP blocklist checker",
                "f3": "middleware/index.js", "f3_desc": "middleware chain export",
                "test": "npm test",
                "response_lang": "javascript",
            },
            {
                "project": "request validator middleware",
                "f1": "middleware/validateBody.js", "f1_desc": "request body schema validator",
                "f2": "middleware/sanitize.js", "f2_desc": "input sanitizer",
                "f3": "middleware/index.js", "f3_desc": "middleware chain export",
                "test": "npm test",
                "response_lang": "javascript",
            },
        ],
    },
    {
        "lang": "javascript",
        "action": "CREATE",
        "file_count": 4,
        "project_type": "Node.js CLI tool",
        "prompt_template": "Create a Node.js CLI tool split across four files: `{f1}`, `{f2}`, `{f3}`, and `{f4}`.",
        "variants": [
            {
                "f1": "bin/cli.js", "f2": "lib/commands/init.js",
                "f3": "lib/commands/run.js", "f4": "lib/config.js",
                "test": "npm test",
                "response_lang": "javascript",
                "description": "bin/cli.js entry point, lib/commands/init.js init command, lib/commands/run.js run command, lib/config.js config loader",
            },
        ],
    },

    # ── TypeScript ─────────────────────────────────────────────────────────────
    {
        "lang": "typescript",
        "action": "CREATE",
        "file_count": 3,
        "project_type": "TypeScript service layer",
        "prompt_template": "Create a TypeScript {service} service split into three files: `{f1}` ({f1_desc}), `{f2}` ({f2_desc}), and `{f3}` ({f3_desc}).",
        "variants": [
            {
                "service": "email notification",
                "f1": "services/email/types.ts", "f1_desc": "EmailOptions interface",
                "f2": "services/email/emailService.ts", "f2_desc": "send/queue methods",
                "f3": "services/email/templates.ts", "f3_desc": "HTML email templates",
                "test": "npx jest",
                "response_lang": "typescript",
            },
            {
                "service": "file storage",
                "f1": "services/storage/types.ts", "f1_desc": "StorageProvider interface",
                "f2": "services/storage/s3Provider.ts", "f2_desc": "S3 implementation",
                "f3": "services/storage/localProvider.ts", "f3_desc": "local filesystem implementation",
                "test": "npx jest",
                "response_lang": "typescript",
            },
            {
                "service": "payment",
                "f1": "services/payment/types.ts", "f1_desc": "PaymentIntent and Charge interfaces",
                "f2": "services/payment/stripeClient.ts", "f2_desc": "Stripe API wrapper",
                "f3": "services/payment/webhookHandler.ts", "f3_desc": "Stripe webhook event processor",
                "test": "npx jest",
                "response_lang": "typescript",
            },
        ],
    },

    # ── Go ─────────────────────────────────────────────────────────────────────
    {
        "lang": "go",
        "action": "CREATE",
        "file_count": 3,
        "project_type": "Go package",
        "prompt_template": "Create a Go `{pkg}` package with three files: `{f1}` ({f1_desc}), `{f2}` ({f2_desc}), and `{f3}` ({f3_desc}).",
        "variants": [
            {
                "pkg": "retry",
                "f1": "retry/retry.go", "f1_desc": "Retry interface and Do function",
                "f2": "retry/backoff.go", "f2_desc": "exponential backoff strategy",
                "f3": "retry/errors.go", "f3_desc": "MaxRetriesError type",
                "test": "go test ./retry/...",
                "response_lang": "go",
            },
            {
                "pkg": "ratelimit",
                "f1": "ratelimit/limiter.go", "f1_desc": "Limiter interface",
                "f2": "ratelimit/token_bucket.go", "f2_desc": "token bucket implementation",
                "f3": "ratelimit/middleware.go", "f3_desc": "HTTP middleware wrapper",
                "test": "go test ./ratelimit/...",
                "response_lang": "go",
            },
            {
                "pkg": "queue",
                "f1": "queue/queue.go", "f1_desc": "Queue interface with Push/Pop/Len",
                "f2": "queue/memory.go", "f2_desc": "in-memory FIFO implementation",
                "f3": "queue/priority.go", "f3_desc": "min-heap priority queue",
                "test": "go test ./queue/...",
                "response_lang": "go",
            },
        ],
    },
    {
        "lang": "go",
        "action": "CREATE",
        "file_count": 4,
        "project_type": "Go REST handler split",
        "prompt_template": "Split the Go REST handlers across four files: `{f1}` ({f1_desc}), `{f2}` ({f2_desc}), `{f3}` ({f3_desc}), `{f4}` ({f4_desc}).",
        "variants": [
            {
                "f1": "handlers/products.go", "f1_desc": "GET/POST /products handlers",
                "f2": "handlers/orders.go", "f2_desc": "GET/POST /orders handlers",
                "f3": "handlers/middleware.go", "f3_desc": "auth and logging middleware",
                "f4": "handlers/errors.go", "f4_desc": "error response helpers",
                "test": "go test ./handlers/...",
                "response_lang": "go",
            },
        ],
    },

    # ── CSS ─────────────────────────────────────────────────────────────────────
    {
        "lang": "css",
        "action": "CREATE",
        "file_count": 3,
        "project_type": "CSS component library",
        "prompt_template": "Create a minimal CSS {component_type} component library with three files: `{f1}` ({f1_desc}), `{f2}` ({f2_desc}), and `{f3}` ({f3_desc}).",
        "variants": [
            {
                "component_type": "navigation",
                "f1": "components/nav/navbar.css", "f1_desc": "top navigation bar",
                "f2": "components/nav/sidebar.css", "f2_desc": "collapsible side navigation",
                "f3": "components/nav/breadcrumb.css", "f3_desc": "breadcrumb trail",
                "test": "none",
                "response_lang": "css",
            },
            {
                "component_type": "data display",
                "f1": "components/table.css", "f1_desc": "sortable data table",
                "f2": "components/badge.css", "f2_desc": "status and count badges",
                "f3": "components/avatar.css", "f3_desc": "user avatar with fallback initials",
                "test": "none",
                "response_lang": "css",
            },
        ],
    },

    # ── Mixed (JS + CSS) ────────────────────────────────────────────────────────
    {
        "lang": "javascript+css",
        "action": "CREATE",
        "file_count": 3,
        "project_type": "Frontend widget",
        "prompt_template": "Create a self-contained {widget} widget with three files: `{f1}` ({f1_desc}), `{f2}` ({f2_desc}), and `{f3}` ({f3_desc}).",
        "variants": [
            {
                "widget": "toast notification",
                "f1": "widgets/toast/toast.js", "f1_desc": "Toast class with show/hide methods",
                "f2": "widgets/toast/toast.css", "f2_desc": "slide-in animation and variants",
                "f3": "widgets/toast/index.js", "f3_desc": "singleton export with convenience methods",
                "test": "none",
                "response_lang": "javascript",
                "extra_lang": "css",
            },
        ],
    },
]


def build_prompt_from_archetype(archetype: dict, variant: dict) -> str:
    """Build a prompt string from an archetype and variant."""
    template = archetype["prompt_template"]
    try:
        return template.format(**variant)
    except KeyError:
        # Build a generic prompt if template keys are missing
        files = [v for k, v in variant.items() if k.startswith("f") and k[1:].isdigit()]
        return f"Create a {archetype['project_type']} with these files: {', '.join(files)}."


def build_stub_response(archetype: dict, variant: dict) -> str:
    """
    Build a stub multi-file response for a variant.
    This produces a minimal but valid <<FILES>> block with correct # filepath: headers.
    For the synthetic track, the code content is simplified stubs.
    """
    files = []
    i = 1
    while f"f{i}" in variant:
        files.append(variant[f"f{i}"])
        i += 1

    lang = variant.get("response_lang", archetype["lang"].split("+")[0])
    action = archetype.get("action", "CREATE")

    comment_style = {
        "javascript": "//", "typescript": "//", "go": "//",
        "css": "/*", "rust": "//", "python": "#",
    }.get(lang, "//")

    comment_close = {
        "css": " */",
    }.get(lang, "")

    response_lines = [
        "<<THINKING>>",
        f"Creating {len(files)} files for {archetype['project_type']}.",
        "",
        "<<FILES>>",
    ]

    for filepath in files:
        ext = filepath.rsplit(".", 1)[-1] if "." in filepath else lang
        fence_lang = {
            "js": "javascript", "ts": "typescript", "go": "go",
            "css": "css", "rs": "rust", "py": "python",
            "proto": "protobuf", "sh": "bash",
        }.get(ext, lang)

        response_lines.append(f"```{fence_lang}")
        response_lines.append(f"{comment_style} filepath: {filepath}{comment_close}")
        response_lines.append(f"{comment_style} action: {action}{comment_close}")
        response_lines.append("")

        # Language-specific stubs
        if fence_lang in ("javascript", "typescript"):
            name = filepath.split("/")[-1].replace(".js", "").replace(".ts", "")
            if "index" in name or name == "index":
                response_lines.append("// Re-export all public APIs")
                if fence_lang == "typescript":
                    response_lines.append(f"export {{}};")
                else:
                    response_lines.append(f"module.exports = {{}};")
            elif fence_lang == "typescript":
                response_lines.append(f"export interface {name.capitalize()} {{")
                response_lines.append(f"    // TODO: define fields")
                response_lines.append(f"}}")
            else:
                response_lines.append(f"'use strict';")
                response_lines.append(f"")
                response_lines.append(f"module.exports = {{}};")
        elif fence_lang == "go":
            pkg = filepath.split("/")[-2] if "/" in filepath else "main"
            response_lines.append(f"package {pkg}")
            response_lines.append(f"")
        elif fence_lang == "css":
            selector = "." + filepath.split("/")[-1].replace(".css", "").replace("-", "_")
            response_lines.append(f"{selector} {{")
            response_lines.append(f"    /* TODO: add styles */")
            response_lines.append(f"}}")
        else:
            response_lines.append(f"# TODO: implement {filepath}")

        response_lines.append("```")

    test_cmd = variant.get("test", "none")
    response_lines += [
        "",
        "<<TEST_COMMAND>>",
        test_cmd,
    ]
    return "\n".join(response_lines)


def generate_synthetic_examples(target_count: int, seed: int = 42) -> List[dict]:
    """Generate synthetic multi-file examples from structural templates."""
    random.seed(seed)
    examples = []

    all_variants = []
    for arch in PROJECT_ARCHETYPES:
        for v in arch.get("variants", []):
            all_variants.append((arch, v))

    random.shuffle(all_variants)

    for i, (arch, variant) in enumerate(all_variants):
        if len(examples) >= target_count:
            break

        prompt = build_prompt_from_archetype(arch, variant)
        response = build_stub_response(arch, variant)

        examples.append({
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ],
            "metadata": {
                "category": "multi_file_multi_language",
                "language": arch["lang"],
                "file_count": arch["file_count"],
                "project_type": arch["project_type"],
                "track": "synthetic",
                "version": "v1_generated",
            }
        })

    return examples


# ═══════════════════════════════════════════════════════════════════════════════
# Track 3: LLM-Generated (optional)
# ═══════════════════════════════════════════════════════════════════════════════

LLM_GENERATION_PROMPT = """You are generating training examples for a coding model called Nova.
Nova outputs multi-file coding tasks in this EXACT format:

<<THINKING>>
[Brief, ≤ 50 words: what files are being created and why]

<<FILES>>
[One fenced code block per file, each starting with:
  # filepath: <path>
  # action: CREATE|MODIFY
]

<<TEST_COMMAND>>
[Single shell command to test the output]

Generate ONE complete training example with:
- Language: {language}
- File count: {file_count}
- Project type: {project_type}

The prompt must be concrete and specific (include exact file paths and what each file should contain).
The response must use the exact <<THINKING>><<FILES>><<TEST_COMMAND>> format with proper # filepath: headers.
Output ONLY the JSON object with keys "prompt" and "response". No other text."""

LLM_GENERATION_TASKS = [
    {"language": "go", "file_count": 4, "project_type": "gRPC service with proto, server, handlers, and main"},
    {"language": "typescript", "file_count": 4, "project_type": "Next.js API route with types, service, handler, and middleware"},
    {"language": "javascript", "file_count": 5, "project_type": "Express app with routes, models, middleware, config, and entry point"},
    {"language": "go", "file_count": 3, "project_type": "HTTP middleware package with interface, implementations, and chain"},
    {"language": "css", "file_count": 5, "project_type": "Complete design system (tokens, typography, layout, components, utilities)"},
    {"language": "typescript", "file_count": 3, "project_type": "Repository pattern with interface, implementation, and factory"},
    {"language": "go", "file_count": 3, "project_type": "Worker pool with interface, pool implementation, and task types"},
    {"language": "javascript", "file_count": 3, "project_type": "WebSocket server with connection manager, message handler, and broadcaster"},
    {"language": "typescript", "file_count": 4, "project_type": "Event system with emitter, listener, types, and middleware"},
    {"language": "go", "file_count": 4, "project_type": "Config loader with interface, file reader, env reader, and validator"},
]


def generate_llm_examples(api_key: str, count: int = 10) -> List[dict]:
    """Generate examples using DeepSeek API (optional track)."""
    try:
        from openai import OpenAI
    except ImportError:
        print("⚠️  openai package not installed. Skipping LLM track.")
        return []

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    examples = []
    tasks = LLM_GENERATION_TASKS[:count]

    for task in tasks:
        print(f"  [LLM] Generating: {task['language']} {task['file_count']}-file {task['project_type']}...")
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a training data generator for AI models."},
                    {"role": "user", "content": LLM_GENERATION_PROMPT.format(**task)},
                ],
                temperature=0.4,
                max_tokens=3000,
            )
            text = resp.choices[0].message.content.strip()

            # Parse JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)
            examples.append({
                "messages": [
                    {"role": "user", "content": data["prompt"]},
                    {"role": "assistant", "content": data["response"]},
                ],
                "metadata": {
                    "category": "multi_file_multi_language",
                    "language": task["language"],
                    "file_count": task["file_count"],
                    "project_type": task["project_type"],
                    "track": "llm_generated",
                    "version": "v1_generated",
                }
            })

        except Exception as e:
            print(f"  ⚠️  LLM generation failed for {task}: {e}")

    return examples


# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_example(ex: dict) -> tuple:
    """Validate that an example has correct format."""
    errors = []
    response = ex["messages"][1]["content"]

    if "<<THINKING>>" not in response:
        errors.append("Missing <<THINKING>>")
    if "<<FILES>>" not in response:
        errors.append("Missing <<FILES>>")
    if "<<TEST_COMMAND>>" not in response:
        errors.append("Missing <<TEST_COMMAND>>")

    import re
    file_count = len(re.findall(r'^#\s*filepath\s*:', response, re.MULTILINE | re.IGNORECASE))
    expected = ex["metadata"].get("file_count", 0)
    if expected > 0 and file_count < 2:
        errors.append(f"Expected {expected} files but found {file_count} filepath headers")

    return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate multi-file, multi-language training examples")
    parser.add_argument("--count", type=int, default=65,
                        help="Target total count (default: 65, includes 12 seeds)")
    parser.add_argument("--output", type=str,
                        default=str(Path(__file__).parent / "multifile_examples.jsonl"),
                        help="Output JSONL file path")
    parser.add_argument("--use-llm", action="store_true",
                        help="Use DeepSeek API for LLM-generated track (requires DEEPSEEK_API_KEY)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for synthetic generation")
    parser.add_argument("--preview", action="store_true", help="Print stats and first 3 examples, then exit")
    args = parser.parse_args()

    print("=" * 60)
    print("  Multi-File Example Generator")
    print("=" * 60)

    examples = []

    # Track 1: Seeds
    print(f"\n[Track 1] Loading {len(MULTIFILE_SEEDS)} hand-authored seeds...")
    for seed in MULTIFILE_SEEDS:
        examples.append(seed_to_entry(seed))
    print(f"  → {len(examples)} examples so far")

    # Track 2: Synthetic
    synthetic_target = args.count - len(examples)
    if args.use_llm:
        llm_count = min(10, len(LLM_GENERATION_TASKS))
        synthetic_target -= llm_count

    if synthetic_target > 0:
        print(f"\n[Track 2] Generating ~{synthetic_target} synthetic examples...")
        synthetic = generate_synthetic_examples(synthetic_target, seed=args.seed)
        examples.extend(synthetic)
        print(f"  → {len(examples)} examples so far")

    # Track 3: LLM (optional)
    if args.use_llm:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            print("\n⚠️  DEEPSEEK_API_KEY not set. Skipping LLM track.")
        else:
            print(f"\n[Track 3] Generating LLM examples via DeepSeek...")
            llm_examples = generate_llm_examples(api_key, count=10)
            examples.extend(llm_examples)
            print(f"  → {len(examples)} examples total (after LLM track)")

    if args.preview:
        from collections import Counter
        langs = Counter(ex["metadata"]["language"] for ex in examples)
        tracks = Counter(ex["metadata"].get("track", "seed") for ex in examples)
        counts = Counter(ex["metadata"].get("file_count", "?") for ex in examples)
        print(f"\nTotal: {len(examples)}")
        print(f"Languages: {dict(langs)}")
        print(f"Tracks: {dict(tracks)}")
        print(f"File counts: {dict(counts)}")
        print("\nFirst 3 examples:")
        for ex in examples[:3]:
            print(f"\n  Prompt: {ex['messages'][0]['content'][:100]}...")
            print(f"  Response (first 150): {ex['messages'][1]['content'][:150]}...")
        return

    # Validate
    print("\nValidating all examples...")
    valid_count = 0
    invalid_examples = []
    for ex in examples:
        is_valid, errors = validate_example(ex)
        if is_valid:
            valid_count += 1
        else:
            invalid_examples.append((ex, errors))

    if invalid_examples:
        print(f"⚠️  {len(invalid_examples)} examples failed validation:")
        for ex, errs in invalid_examples[:3]:
            print(f"   - {ex['messages'][0]['content'][:60]}... → {errs}")

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    print(f"\n✅ Wrote {len(examples)} examples to {output_path}")
    print(f"   Valid: {valid_count}/{len(examples)}")

    from collections import Counter
    langs = Counter(ex["metadata"]["language"] for ex in examples)
    tracks = Counter(ex["metadata"].get("track", "seed") for ex in examples)
    print(f"   Languages: {dict(langs)}")
    print(f"   Tracks: {dict(tracks)}")


if __name__ == "__main__":
    main()
