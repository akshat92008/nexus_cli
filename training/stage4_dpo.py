#!/usr/bin/env python3
"""
Nova v12 Training — Stage 4: Execution-Ranked DPO

Direct Preference Optimisation using execution-ranked preference pairs.
Teaches the model to prefer correct, minimal solutions over plausible
but broken ones.

Data format (each line):
{
    "prompt": "...",
    "chosen": "patch that passed all tests",
    "rejected": "patch that failed tests",
    "chosen_evidence": {"exit_code": 0, "tests_passed": 5, "tests_total": 5},
    "rejected_evidence": {"exit_code": 1, "tests_passed": 2, "tests_total": 5}
}

Usage:
    python stage4_dpo.py --base-model /path/to/stage3_output \
                         --data /path/to/preference_pairs.jsonl \
                         --output-dir /path/to/stage4_output
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        description="Nova v12 Stage 4: DPO Training"
    )
    parser.add_argument("--base-model", type=str, required=True)
    parser.add_argument("--data", type=str, required=True,
                        help="JSONL file with preference pairs")
    parser.add_argument("--output-dir", type=str, required=True)

    parser.add_argument("--learning-rate", type=float, default=5e-7)
    parser.add_argument("--beta", type=float, default=0.1,
                        help="DPO beta parameter (default: 0.1)")
    parser.add_argument("--num-epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--max-seq-length", type=int, default=4096)

    parser.add_argument("--use-lora", action="store_true", default=True)
    parser.add_argument("--lora-rank", type=int, default=32)
    parser.add_argument("--lora-alpha", type=int, default=64)

    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--bf16", action="store_true", default=True)

    args = parser.parse_args()

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("NOVA v12 — STAGE 4: DPO TRAINING")
    print("=" * 70)
    print(f"Base model: {args.base_model}")
    print(f"Data:       {args.data}")
    print(f"Beta:       {args.beta}")
    print(f"LR:         {args.learning_rate}")
    print("=" * 70)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from datasets import load_dataset
        from trl import DPOTrainer, DPOConfig
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install transformers torch datasets trl peft")
        sys.exit(1)

    # Load model and tokenizer
    print("\nLoading model...")
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

    # Load dataset
    print(f"\nLoading preference data from {args.data}...")
    dataset = load_dataset("json", data_files=args.data, split="train")
    print(f"Total pairs: {len(dataset):,}")

    # Split
    split = dataset.train_test_split(test_size=0.05, seed=42)
    train_dataset = split["train"]
    eval_dataset = split["test"]

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

    # DPO config
    dpo_config = DPOConfig(
        output_dir=str(output_path),
        num_train_epochs=args.num_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        beta=args.beta,
        warmup_ratio=0.1,
        lr_scheduler_type="cosine",
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=2,
        bf16=args.bf16,
        gradient_checkpointing=True,
        max_length=args.max_seq_length,
        max_prompt_length=args.max_seq_length // 2,
        report_to="none",
    )

    # Trainer
    trainer = DPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )

    # Train
    print("\nStarting DPO training...")
    train_result = trainer.train()

    # Save
    print("\nSaving model...")
    trainer.save_model()
    tokenizer.save_pretrained(output_path)

    metrics = train_result.metrics
    with open(output_path / "dpo_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n{'='*70}")
    print("STAGE 4 COMPLETE")
    print(f"{'='*70}")
    print(f"Model saved to: {output_path}")
    print(f"Training loss: {metrics.get('train_loss', 'N/A')}")


if __name__ == "__main__":
    main()
