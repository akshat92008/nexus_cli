#!/usr/bin/env python3
"""
Nova v12 Tokenizer Setup — Add Special Mode Tokens

Adds Nova-specific control tokens to the foundation model's tokenizer.
These tokens route the model into different operating modes.

Usage:
    python add_special_tokens.py --model Nanbeige/Nanbeige4.2-3B --output /path/to/tokenizer
    python add_special_tokens.py --model Qwen/Qwen2.5-Coder-3B-Instruct --output /path/to/tokenizer
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Nova v12 special tokens
# ---------------------------------------------------------------------------

NOVA_MODE_TOKENS = [
    # Operating mode tokens
    "<|nova_chat|>",
    "<|nova_code|>",
    "<|nova_fim|>",
    "<|nova_edit|>",
    "<|nova_agent|>",
    "<|nova_debug|>",
    "<|nova_review|>",
    "<|nova_explain|>",
    "<|nova_refactor|>",

    # FIM tokens (if not already in base tokenizer)
    "<|fim_prefix|>",
    "<|fim_middle|>",
    "<|fim_suffix|>",

    # Agent tool-call tokens
    "<|tool_call|>",
    "<|tool_result|>",
    "<|tool_error|>",

    # Structured output tokens
    "<|patch_start|>",
    "<|patch_end|>",
    "<|file_start|>",
    "<|file_end|>",
    "<|diff_start|>",
    "<|diff_end|>",

    # Task management tokens
    "<|task_start|>",
    "<|task_end|>",
    "<|step|>",
    "<|observation|>",
    "<|thinking|>",
]


def add_special_tokens(
    model_id: str,
    output_dir: str,
    trust_remote_code: bool = False,
    dry_run: bool = False,
):
    """Add Nova special tokens to a model's tokenizer."""
    try:
        from transformers import AutoTokenizer
    except ImportError:
        print("ERROR: transformers required. Install with: pip install transformers")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Loading tokenizer from {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        trust_remote_code=trust_remote_code,
    )

    original_vocab_size = len(tokenizer)
    print(f"Original vocabulary size: {original_vocab_size:,}")

    # Check which tokens are already present
    existing = set()
    new_tokens = []

    for token in NOVA_MODE_TOKENS:
        token_ids = tokenizer.encode(token, add_special_tokens=False)
        # If the token encodes to multiple IDs, it's not a single token
        decoded = tokenizer.decode(token_ids)
        if decoded.strip() == token.strip():
            existing.add(token)
            print(f"  Already exists: {token}")
        else:
            new_tokens.append(token)

    if not new_tokens:
        print("\nAll tokens already present in tokenizer.")
        return

    print(f"\nAdding {len(new_tokens)} new tokens:")
    for token in new_tokens:
        print(f"  + {token}")

    if dry_run:
        print("\nDry run — no changes saved.")
        return

    # Add tokens
    num_added = tokenizer.add_special_tokens({
        "additional_special_tokens": new_tokens,
    })

    new_vocab_size = len(tokenizer)
    print(f"\nTokens added: {num_added}")
    print(f"New vocabulary size: {new_vocab_size:,}")
    print(f"Vocab growth: {new_vocab_size - original_vocab_size}")

    # Save tokenizer
    tokenizer.save_pretrained(output_path)
    print(f"\nTokenizer saved to {output_path}")

    # Save token mapping for reference
    token_map = {}
    for token in NOVA_MODE_TOKENS:
        token_id = tokenizer.convert_tokens_to_ids(token)
        token_map[token] = token_id

    map_file = output_path / "nova_token_mapping.json"
    with open(map_file, "w") as f:
        json.dump(token_map, f, indent=2)
    print(f"Token mapping saved to {map_file}")

    # Verification
    print("\nVerification:")
    for token in NOVA_MODE_TOKENS[:5]:
        token_id = tokenizer.convert_tokens_to_ids(token)
        roundtrip = tokenizer.decode([token_id])
        status = "✓" if roundtrip.strip() == token.strip() else "✗"
        print(f"  {status} {token} → ID {token_id} → '{roundtrip.strip()}'")
    if len(NOVA_MODE_TOKENS) > 5:
        print(f"  ... and {len(NOVA_MODE_TOKENS) - 5} more")

    # Important note about model embedding resize
    print("\n" + "=" * 60)
    print("IMPORTANT: After adding tokens, you must resize the model's")
    print("embedding layer before training:")
    print()
    print("  model.resize_token_embeddings(len(tokenizer))")
    print()
    print("The new token embeddings will be randomly initialised.")
    print("They will learn their representations during training.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Add Nova v12 special tokens to a model tokenizer"
    )
    parser.add_argument("--model", type=str, required=True,
                        help="HuggingFace model ID or local path")
    parser.add_argument("--output", type=str, required=True,
                        help="Output directory for modified tokenizer")
    parser.add_argument("--trust-remote-code", action="store_true",
                        help="Allow trust_remote_code for custom models")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without saving")

    args = parser.parse_args()

    add_special_tokens(
        model_id=args.model,
        output_dir=args.output,
        trust_remote_code=args.trust_remote_code,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
