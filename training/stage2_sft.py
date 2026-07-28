#!/usr/bin/env python3
"""
Nova v12 Training — Stage 2: Multi-Mode Supervised Fine-Tuning

Trains the model on all Nova operating modes using execution-verified
examples with mode-specific control tokens.

Modes:
    <|nova_code|>      Code generation (30%)
    <|nova_fim|>       FIM completion (20%)
    <|nova_edit|>      Code editing (15%)
    <|nova_debug|>     Debugging (15%)
    <|nova_agent|>     Agentic tool use (10%)
    <|nova_review|>    Code review (5%)
    <|nova_explain|>   Explanation (5%)

Usage:
    python stage2_sft.py --base-model /path/to/stage1_output \
                         --data-dir /path/to/sft_data \
                         --output-dir /path/to/stage2_output
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime


# System prompt for Nova Code
NOVA_SYSTEM_PROMPT = (
    "You are Nova Code, an AI coding assistant by Amaura Labs. "
    "You help developers write, debug, edit, and understand code. "
    "You are precise, minimal, and honest about your limitations. "
    "You produce working code and explain your reasoning clearly."
)


def format_sft_example(example: dict, tokenizer) -> dict:
    """Format a training example into a chat template."""
    mode = example.get("mode", "<|nova_code|>")
    instruction = example.get("instruction", "")
    input_text = example.get("input", "")
    output_text = example.get("output", "")

    # Build messages
    messages = [
        {"role": "system", "content": NOVA_SYSTEM_PROMPT},
    ]

    # User message
    user_content = f"{mode}\n{instruction}"
    if input_text:
        user_content += f"\n\n{input_text}"
    messages.append({"role": "user", "content": user_content})

    # Assistant message
    messages.append({"role": "assistant", "content": output_text})

    # Apply chat template
    try:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    except Exception:
        # Fallback for tokenizers without chat template
        text = (
            f"<|im_start|>system\n{NOVA_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user_content}<|im_end|>\n"
            f"<|im_start|>assistant\n{output_text}<|im_end|>"
        )

    return {"text": text}


def main():
    parser = argparse.ArgumentParser(
        description="Nova v12 Stage 2: Multi-Mode SFT"
    )
    parser.add_argument("--base-model", type=str, required=True,
                        help="Path to Stage 1 output or foundation model")
    parser.add_argument("--data-dir", type=str, required=True,
                        help="Directory containing SFT JSONL data")
    parser.add_argument("--output-dir", type=str, required=True,
                        help="Output directory for trained model")

    # Training hyperparameters
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--num-epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--max-seq-length", type=int, default=4096)

    # LoRA
    parser.add_argument("--use-lora", action="store_true", default=True)
    parser.add_argument("--lora-rank", type=int, default=64)
    parser.add_argument("--lora-alpha", type=int, default=128)

    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--bf16", action="store_true", default=True)

    args = parser.parse_args()

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("NOVA v12 — STAGE 2: MULTI-MODE SFT")
    print("=" * 70)
    print(f"Base model: {args.base_model}")
    print(f"Data:       {args.data_dir}")
    print(f"Output:     {args.output_dir}")
    print(f"LR:         {args.learning_rate}")
    print(f"Epochs:     {args.num_epochs}")
    print(f"LoRA:       r={args.lora_rank}, α={args.lora_alpha}")
    print("=" * 70)

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
        )
        from datasets import load_dataset
        from trl import SFTTrainer, SFTConfig
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install transformers torch datasets trl peft")
        sys.exit(1)

    # Load tokenizer and model
    print("\nLoading tokenizer and model...")
    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model,
        trust_remote_code=args.trust_remote_code,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16 if args.bf16 else torch.float16,
        trust_remote_code=args.trust_remote_code,
        device_map="auto",
    )

    # Load and format dataset
    print(f"\nLoading SFT data from {args.data_dir}...")
    data_path = Path(args.data_dir)
    data_files = list(data_path.glob("*.jsonl"))

    dataset = load_dataset(
        "json",
        data_files=[str(f) for f in data_files],
        split="train",
    )

    print(f"Total examples: {len(dataset):,}")

    # Format examples
    def format_fn(examples):
        texts = []
        for i in range(len(examples["instruction"])):
            example = {
                key: examples[key][i]
                for key in examples.keys()
            }
            formatted = format_sft_example(example, tokenizer)
            texts.append(formatted["text"])
        return {"text": texts}

    formatted_dataset = dataset.map(
        format_fn,
        batched=True,
        remove_columns=dataset.column_names,
    )

    # Split
    split = formatted_dataset.train_test_split(test_size=0.1, seed=42)
    train_dataset = split["train"]
    eval_dataset = split["test"]

    print(f"Train: {len(train_dataset):,} | Eval: {len(eval_dataset):,}")

    # LoRA config
    peft_config = None
    if args.use_lora:
        from peft import LoraConfig, TaskType
        peft_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_rank,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            bias="none",
        )

    # Training config
    sft_config = SFTConfig(
        output_dir=str(output_path),
        num_train_epochs=args.num_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=25,
        eval_strategy="steps",
        eval_steps=250,
        save_strategy="steps",
        save_steps=500,
        save_total_limit=3,
        bf16=args.bf16,
        gradient_checkpointing=True,
        max_seq_length=args.max_seq_length,
        packing=True,
        dataset_text_field="text",
        report_to="none",
    )

    # Trainer
    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        peft_config=peft_config,
    )

    # Train
    print("\nStarting SFT training...")
    train_result = trainer.train()

    # Save
    print("\nSaving model...")
    trainer.save_model()
    tokenizer.save_pretrained(output_path)

    # Metrics
    metrics = train_result.metrics
    with open(output_path / "sft_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n{'='*70}")
    print("STAGE 2 COMPLETE")
    print(f"{'='*70}")
    print(f"Model saved to: {output_path}")
    print(f"Training loss: {metrics.get('train_loss', 'N/A')}")
    print(f"\nNext: Run evaluation suite")


if __name__ == "__main__":
    main()
