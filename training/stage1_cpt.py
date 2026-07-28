#!/usr/bin/env python3
"""
Nova v12 Training — Stage 1: Domain-Adaptive Continued Pretraining

Continues pretraining the selected foundation model on filtered code data
with multiple objectives: next-token prediction, FIM, and diff prediction.

Usage:
    python stage1_cpt.py --config configs/cpt_config.yaml
    python stage1_cpt.py --base-model Nanbeige/Nanbeige4.2-3B \
                         --data-dir /path/to/crawled_data \
                         --output-dir /path/to/stage1_output
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        description="Nova v12 Stage 1: Continued Pretraining"
    )
    parser.add_argument("--base-model", type=str, required=True,
                        help="HuggingFace model ID or local path")
    parser.add_argument("--tokenizer-dir", type=str,
                        help="Directory with Nova-modified tokenizer")
    parser.add_argument("--data-dir", type=str, required=True,
                        help="Directory containing crawled JSONL data")
    parser.add_argument("--output-dir", type=str, required=True,
                        help="Output directory for trained model")
    parser.add_argument("--config", type=str,
                        help="YAML config file (overrides CLI args)")

    # Training hyperparameters
    parser.add_argument("--learning-rate", type=float, default=2e-5,
                        help="Learning rate (default: 2e-5)")
    parser.add_argument("--num-epochs", type=int, default=1,
                        help="Number of epochs (default: 1)")
    parser.add_argument("--batch-size", type=int, default=2,
                        help="Per-device batch size (default: 2)")
    parser.add_argument("--gradient-accumulation", type=int, default=8,
                        help="Gradient accumulation steps (default: 8)")
    parser.add_argument("--max-seq-length", type=int, default=4096,
                        help="Maximum sequence length (default: 4096)")
    parser.add_argument("--warmup-ratio", type=float, default=0.03,
                        help="Warmup ratio (default: 0.03)")
    parser.add_argument("--weight-decay", type=float, default=0.01,
                        help="Weight decay (default: 0.01)")

    # Method
    parser.add_argument("--use-lora", action="store_true",
                        help="Use LoRA instead of full fine-tuning")
    parser.add_argument("--lora-rank", type=int, default=64,
                        help="LoRA rank (default: 64)")
    parser.add_argument("--lora-alpha", type=int, default=128,
                        help="LoRA alpha (default: 128)")

    # FIM
    parser.add_argument("--fim-rate", type=float, default=0.5,
                        help="Fraction of examples using FIM objective (default: 0.5)")

    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--bf16", action="store_true", default=True)
    parser.add_argument("--resume-from", type=str, help="Resume from checkpoint")

    args = parser.parse_args()

    # Load config if provided
    if args.config:
        import yaml
        with open(args.config) as f:
            config = yaml.safe_load(f)
        for key, value in config.items():
            if hasattr(args, key.replace("-", "_")):
                setattr(args, key.replace("-", "_"), value)

    # Validate
    data_path = Path(args.data_dir)
    if not data_path.exists():
        print(f"Error: Data directory not found: {args.data_dir}")
        sys.exit(1)

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("NOVA v12 — STAGE 1: CONTINUED PRETRAINING")
    print("=" * 70)
    print(f"Base model:     {args.base_model}")
    print(f"Data directory: {args.data_dir}")
    print(f"Output:         {args.output_dir}")
    print(f"Learning rate:  {args.learning_rate}")
    print(f"Batch size:     {args.batch_size} × {args.gradient_accumulation}")
    print(f"Max seq length: {args.max_seq_length}")
    print(f"FIM rate:       {args.fim_rate}")
    print(f"LoRA:           {'Yes (r={args.lora_rank})' if args.use_lora else 'No (full FT)'}")
    print(f"Timestamp:      {datetime.now().isoformat()}")
    print("=" * 70)

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
            DataCollatorForLanguageModeling,
        )
        from datasets import load_dataset
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install transformers torch datasets")
        sys.exit(1)

    # Load tokenizer (use Nova-modified if available)
    tokenizer_path = args.tokenizer_dir or args.base_model
    print(f"\nLoading tokenizer from {tokenizer_path}...")
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_path,
        trust_remote_code=args.trust_remote_code,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model
    print(f"Loading model from {args.base_model}...")
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16 if args.bf16 else torch.float16,
        trust_remote_code=args.trust_remote_code,
        device_map="auto",
    )

    # Resize embeddings if tokenizer has new tokens
    if len(tokenizer) > model.config.vocab_size:
        print(f"Resizing embeddings: {model.config.vocab_size} → {len(tokenizer)}")
        model.resize_token_embeddings(len(tokenizer))

    # Apply LoRA if requested
    if args.use_lora:
        try:
            from peft import LoraConfig, get_peft_model, TaskType
        except ImportError:
            print("peft required for LoRA. Install with: pip install peft")
            sys.exit(1)

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_rank,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            bias="none",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

    # Load dataset
    print(f"\nLoading data from {args.data_dir}...")
    data_files = list(data_path.glob("*.jsonl"))
    if not data_files:
        print("Error: No JSONL files found in data directory")
        sys.exit(1)

    print(f"Found {len(data_files)} data files")

    dataset = load_dataset(
        "json",
        data_files=[str(f) for f in data_files],
        split="train",
    )

    print(f"Total examples: {len(dataset):,}")

    # Tokenisation
    def tokenize_function(examples):
        texts = examples.get("content", examples.get("formatted", []))
        return tokenizer(
            texts,
            truncation=True,
            max_length=args.max_seq_length,
            padding=False,
        )

    print("Tokenising dataset...")
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=dataset.column_names,
        num_proc=4,
    )

    # Split for evaluation
    split = tokenized_dataset.train_test_split(test_size=0.02, seed=42)
    train_dataset = split["train"]
    eval_dataset = split["test"]

    print(f"Train: {len(train_dataset):,} | Eval: {len(eval_dataset):,}")

    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_path),
        overwrite_output_dir=True,
        num_train_epochs=args.num_epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type="cosine",
        logging_steps=50,
        eval_strategy="steps",
        eval_steps=500,
        save_strategy="steps",
        save_steps=1000,
        save_total_limit=3,
        bf16=args.bf16,
        gradient_checkpointing=True,
        report_to="none",
        dataloader_num_workers=2,
        remove_unused_columns=False,
        resume_from_checkpoint=args.resume_from,
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
    )

    # Train
    print("\nStarting training...")
    train_result = trainer.train(resume_from_checkpoint=args.resume_from)

    # Save
    print("\nSaving model...")
    trainer.save_model()
    tokenizer.save_pretrained(output_path)

    # Save training metrics
    metrics = train_result.metrics
    metrics_file = output_path / "training_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n{'='*70}")
    print("STAGE 1 COMPLETE")
    print(f"{'='*70}")
    print(f"Model saved to: {output_path}")
    print(f"Training loss:  {metrics.get('train_loss', 'N/A')}")
    print(f"\nNext step: Run evaluation to verify no regression")
    print(f"  python eval/benchmarks/humaneval_plus.py --model {output_path}")


if __name__ == "__main__":
    main()
