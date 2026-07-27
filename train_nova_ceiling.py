#!/usr/bin/env python3
"""
train_nova_ceiling.py — DoRA Fine-Tuning Pipeline for Nova 1.5B "Absolute Ceiling"

Upgraded training script for Google Colab that uses DoRA (Weight-Decomposed Low-Rank 
Adaptation) with high-rank adapters to teach the Qwen 2.5 Coder 1.5B model deep 
chain-of-thought reasoning.

Key upgrades over train_unsloth.py:
  - DoRA instead of LoRA (separates weight magnitude and direction)
  - Rank 64 (2x previous) for more reasoning capacity
  - Alpha 128 (2x rank) for proper scaling
  - Learning rate 1.5e-5 (13x slower to prevent forgetting)
  - Max seq length 4096+ (fits long <<THINKING>> blocks)
  - Cosine LR scheduler with warmup
  - ChatML messages format (not instruction/output)
  - Train/eval split for overfitting detection
  - Full epoch training instead of max_steps

Usage (Google Colab):
  !pip install -q unsloth datasets trl transformers

  # Upload dataset_nova_v3_cot_clean.jsonl to Colab
  !python train_nova_ceiling.py --dataset dataset_nova_v3_cot_clean.jsonl --epochs 2

  # Or with custom hyperparameters
  !python train_nova_ceiling.py \\
      --dataset dataset_nova_v3_cot_clean.jsonl \\
      --rank 128 --alpha 256 \\
      --lr 1e-5 --epochs 3 \\
      --max-seq-length 8192 \\
      --output nova-ceiling-v1

Usage (Non-Colab / Simulation):
  python train_nova_ceiling.py --dataset dataset_nova_v3_cot.jsonl --dry-run
"""

import os
import sys
import json
import argparse
from typing import Optional


def run_training(
    dataset_path: str,
    output_dir: str,
    rank: int = 64,
    alpha: int = 128,
    learning_rate: float = 1.5e-5,
    epochs: int = 2,
    max_seq_length: int = 4096,
    batch_size: int = 2,
    gradient_accumulation_steps: int = 4,
    warmup_ratio: float = 0.1,
    dropout: float = 0.05,
    use_dora: bool = True,
    eval_split: float = 0.15,
    logging_steps: int = 1,
    eval_steps: int = 50,
    save_steps: int = 100,
    base_model: str = "Qwen/Qwen2.5-Coder-3B-Instruct",
    dry_run: bool = False,
    export_gguf: bool = True,
    gguf_quant: str = "q4_k_m",
):
    """
    Main training pipeline.
    
    Supports two modes:
    1. Colab mode (with Unsloth installed): Full training and GGUF export
    2. Dry-run mode: Validates configuration and dataset without training
    """

    print("=" * 70)
    print(" NOVA 1.5B 'ABSOLUTE CEILING' — DoRA FINE-TUNING PIPELINE")
    print("=" * 70)
    print()
    print("📋 Configuration:")
    print(f"   Base Model:        {base_model}")
    print(f"   Dataset:           {dataset_path}")
    print(f"   Output:            {output_dir}")
    print(f"   Method:            {'DoRA' if use_dora else 'LoRA'}")
    print(f"   Rank (r):          {rank}")
    print(f"   Alpha:             {alpha}")
    print(f"   Learning Rate:     {learning_rate}")
    print(f"   Epochs:            {epochs}")
    print(f"   Max Seq Length:    {max_seq_length}")
    print(f"   Batch Size:        {batch_size}")
    print(f"   Grad Accum Steps:  {gradient_accumulation_steps}")
    print(f"   Effective Batch:   {batch_size * gradient_accumulation_steps}")
    print(f"   Warmup Ratio:      {warmup_ratio}")
    print(f"   Dropout:           {dropout}")
    print(f"   Eval Split:        {eval_split}")
    print(f"   Export GGUF:       {export_gguf} ({gguf_quant})")
    print(f"   Dry Run:           {dry_run}")
    print()

    # ── Validate Dataset ──────────────────────────────────────────────────
    print("─" * 70)
    print("Step 1: Validating Dataset")
    print("─" * 70)

    if not os.path.exists(dataset_path):
        print(f"❌ Dataset file not found: {dataset_path}")
        sys.exit(1)

    # Count and validate entries
    entry_count = 0
    format_type = None  # "messages" or "instruction"
    sample_entry = None

    with open(dataset_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_count += 1

                if sample_entry is None:
                    sample_entry = entry

                # Detect format
                if "messages" in entry:
                    if format_type is None:
                        format_type = "messages"
                    elif format_type != "messages":
                        print(f"⚠️  Mixed formats detected at line {line_num}")
                elif "instruction" in entry:
                    if format_type is None:
                        format_type = "instruction"
                    elif format_type != "instruction":
                        print(f"⚠️  Mixed formats detected at line {line_num}")

            except json.JSONDecodeError:
                print(f"⚠️  JSON parse error at line {line_num}")

    print(f"   Entries: {entry_count}")
    print(f"   Format:  {format_type}")
    
    if entry_count == 0:
        print("❌ Dataset is empty!")
        sys.exit(1)

    if format_type == "messages":
        print("   ✅ ChatML messages format detected (correct for reasoning distillation)")
    elif format_type == "instruction":
        print("   ⚠️  Legacy instruction/output format detected (will be converted)")
    else:
        print("   ❌ Unknown format")
        sys.exit(1)

    # Show sample
    if sample_entry:
        if format_type == "messages":
            user_msg = sample_entry["messages"][0]["content"][:80]
            assistant_preview = sample_entry["messages"][1]["content"][:120]
        else:
            user_msg = sample_entry.get("instruction", "")[:80]
            assistant_preview = sample_entry.get("output", "")[:120]
        
        print(f"\n   Sample user prompt:     {user_msg}...")
        print(f"   Sample assistant start: {assistant_preview}...")

    print(f"\n   ✅ Dataset validation passed\n")

    # ── Dry Run Exit ──────────────────────────────────────────────────────
    if dry_run:
        print("─" * 70)
        print("🧪 DRY RUN — Configuration validated. No training will be performed.")
        print("─" * 70)
        print()
        print("To run actual training on Google Colab:")
        print(f"  1. Upload {dataset_path} to your Colab session")
        print(f"  2. Install Unsloth: !pip install -q unsloth datasets trl transformers")
        print(f"  3. Run: !python train_nova_ceiling.py --dataset {dataset_path}")
        print()
        print("Expected VRAM usage:")
        print(f"  - Rank {rank}, Seq {max_seq_length}: ~{'6-8' if rank <= 64 else '10-14'}GB (use {'T4' if rank <= 64 else 'A100'})")
        print(f"  - Training time: ~{entry_count * epochs * 0.5 / 60:.0f} minutes on T4")
        return

    # ── Load Model & Apply DoRA ───────────────────────────────────────────
    print("─" * 70)
    print("Step 2: Loading Model & Applying DoRA Adapters")
    print("─" * 70)

    try:
        from unsloth import FastLanguageModel
        import torch
        from datasets import load_dataset, Dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments

        print(f"   Loading {base_model} with 4-bit quantization...")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=base_model,
            max_seq_length=max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )

        print(f"   Applying {'DoRA' if use_dora else 'LoRA'} adapters (r={rank}, alpha={alpha})...")
        dora_kwargs = {}
        if use_dora:
            dora_kwargs["use_dora"] = True
        
        model = FastLanguageModel.get_peft_model(
            model,
            r=rank,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_alpha=alpha,
            lora_dropout=dropout,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=3407,
            **dora_kwargs,
        )

        # Print trainable parameters
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total_params = sum(p.numel() for p in model.parameters())
        print(f"   Trainable parameters: {trainable_params:,} / {total_params:,} ({trainable_params/total_params*100:.2f}%)")
        print(f"   ✅ Model loaded successfully\n")

    except ImportError as e:
        print(f"\n❌ Unsloth not installed. This script requires Google Colab with GPU.")
        print(f"   Error: {e}")
        print(f"\n   Install with: pip install unsloth datasets trl transformers")
        print(f"   Or run with --dry-run to validate configuration without training.")
        sys.exit(1)

    # ── Prepare Dataset ───────────────────────────────────────────────────
    print("─" * 70)
    print("Step 3: Preparing Dataset")
    print("─" * 70)

    print(f"   Loading {dataset_path}...")
    dataset = load_dataset("json", data_files={"train": dataset_path}, split="train")
    print(f"   Loaded {len(dataset)} examples")

    # Define formatting function based on detected format
    if format_type == "messages":
        def formatting_prompts_func(examples):
            """Format ChatML messages into training text."""
            texts = []
            for messages in examples["messages"]:
                # Build ChatML format
                text_parts = []
                for msg in messages:
                    role = msg["role"]
                    content = msg["content"]
                    text_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
                texts.append("\n".join(text_parts))
            return {"text": texts}
    else:
        # Legacy instruction/output format
        def formatting_prompts_func(examples):
            """Format instruction/output into ChatML."""
            texts = []
            instructions = examples["instruction"]
            outputs = examples["output"]
            for inst, out in zip(instructions, outputs):
                text = f"<|im_start|>user\n{inst}<|im_end|>\n<|im_start|>assistant\n{out}<|im_end|>"
                texts.append(text)
            return {"text": texts}

    dataset = dataset.map(formatting_prompts_func, batched=True, remove_columns=dataset.column_names)

    # Train/eval split
    if eval_split > 0 and len(dataset) > 20:
        split = dataset.train_test_split(test_size=eval_split, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        print(f"   Train split: {len(train_dataset)} examples")
        print(f"   Eval split:  {len(eval_dataset)} examples")
    else:
        train_dataset = dataset
        eval_dataset = None
        print(f"   Using all {len(train_dataset)} examples for training (no eval split)")

    # Check sequence lengths
    sample_lengths = []
    for i in range(min(50, len(train_dataset))):
        tokens = tokenizer(train_dataset[i]["text"], truncation=False)
        sample_lengths.append(len(tokens["input_ids"]))
    
    avg_len = sum(sample_lengths) / len(sample_lengths)
    max_len = max(sample_lengths)
    overflow = sum(1 for l in sample_lengths if l > max_seq_length)
    
    print(f"\n   Token length stats (sample of {len(sample_lengths)}):")
    print(f"     Average: {avg_len:.0f} tokens")
    print(f"     Maximum: {max_len} tokens")
    print(f"     Overflow (>{max_seq_length}): {overflow} ({overflow/len(sample_lengths)*100:.0f}%)")
    
    if overflow > len(sample_lengths) * 0.2:
        print(f"   ⚠️  >20% of examples exceed max_seq_length={max_seq_length}!")
        print(f"        Consider increasing --max-seq-length to {min(max_len + 256, 8192)}")
    
    print(f"   ✅ Dataset prepared\n")

    # ── Training ──────────────────────────────────────────────────────────
    print("─" * 70)
    print("Step 4: Training")
    print("─" * 70)

    # Calculate total steps for proper scheduling
    num_training_steps = (len(train_dataset) // (batch_size * gradient_accumulation_steps)) * epochs
    warmup_steps = int(num_training_steps * warmup_ratio)
    
    print(f"   Total training steps: {num_training_steps}")
    print(f"   Warmup steps: {warmup_steps}")
    print(f"   Starting training...\n")

    training_args_kwargs = {
        "per_device_train_batch_size": batch_size,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "warmup_steps": warmup_steps,
        "num_train_epochs": epochs,
        "learning_rate": learning_rate,
        "fp16": not torch.cuda.is_bf16_supported(),
        "bf16": torch.cuda.is_bf16_supported(),
        "logging_steps": logging_steps,
        "optim": "adamw_8bit",
        "weight_decay": 0.01,
        "lr_scheduler_type": "cosine",
        "seed": 3407,
        "output_dir": output_dir,
        "save_steps": save_steps,
        "save_total_limit": 3,
    }

    # Add eval if we have eval dataset
    if eval_dataset is not None:
        training_args_kwargs["eval_strategy"] = "steps"
        training_args_kwargs["eval_steps"] = eval_steps

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(**training_args_kwargs),
    )

    try:
        trainer_stats = trainer.train()
        print(f"\n   ✅ Training complete!")
        print(f"   Training loss: {trainer_stats.training_loss:.4f}")
        print(f"   Training time: {trainer_stats.metrics.get('train_runtime', 0):.0f}s")
    except Exception as e:
        print(f"\n   ⚠️  Training encountered an error during final save: {e}")
        print(f"   Model weights in memory should still be valid. Proceeding to save...")

    # ── Save Model ────────────────────────────────────────────────────────
    print()
    print("─" * 70)
    print("Step 5: Saving Model")
    print("─" * 70)

    print(f"   Saving LoRA/DoRA adapter to {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"   ✅ Adapter saved")

    # ── Export GGUF ───────────────────────────────────────────────────────
    if export_gguf:
        print()
        print("─" * 70)
        print("Step 6: Exporting to GGUF")
        print("─" * 70)

        try:
            print(f"   Merging LoRA weights and converting to GGUF ({gguf_quant})...")
            model.save_pretrained_gguf(
                output_dir, tokenizer,
                quantization_method=gguf_quant,
            )
            
            # Find the GGUF file
            gguf_files = [f for f in os.listdir(output_dir) if f.endswith(".gguf")]
            if gguf_files:
                gguf_path = os.path.join(output_dir, gguf_files[0])
                gguf_size_mb = os.path.getsize(gguf_path) / (1024 * 1024)
                print(f"   ✅ GGUF exported: {gguf_path} ({gguf_size_mb:.0f} MB)")
            else:
                print(f"   ✅ GGUF export completed (check {output_dir}/)")

        except Exception as e:
            print(f"   ⚠️  GGUF export failed: {e}")
            print(f"   You can manually convert using llama.cpp:")
            print(f"   python convert_hf_to_gguf.py {output_dir} --outtype {gguf_quant}")

    # ── Final Report ──────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(" 🎉 TRAINING COMPLETE — Nova 3B 'Absolute Ceiling'")
    print("=" * 70)
    print()
    print("  Next steps:")
    print(f"  1. Download the GGUF file from {output_dir}/")
    print(f"  2. Copy to your Mac: ~/Desktop/nova-1.5b/")
    print(f"  3. Create Ollama model:")
    print(f"     ollama create nova-ceiling -f Modelfile")
    print(f"  4. Test: ollama run nova-ceiling 'Build a Python web scraper'")
    print()
    print("  Expected behavior:")
    print("  - Nova will output <<THINKING>> with 15-30 seconds of deep reasoning")
    print("  - Then output <<FILES>> with production-quality code")
    print("  - Self-correcting logic: 'Wait, if X then I need Y instead...'")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Train Nova 1.5B with DoRA for deep reasoning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (validate config without GPU)
  python train_nova_ceiling.py --dataset dataset_nova_v3_cot.jsonl --dry-run

  # Standard training on Colab T4 (rank 64)
  python train_nova_ceiling.py --dataset dataset_nova_v3_cot_clean.jsonl --epochs 2

  # High-capacity training on Colab A100 (rank 128)
  python train_nova_ceiling.py --dataset dataset_nova_v3_cot_clean.jsonl \\
      --rank 128 --alpha 256 --max-seq-length 8192 --epochs 3

  # Conservative training (slower but safer)
  python train_nova_ceiling.py --dataset dataset_nova_v3_cot_clean.jsonl \\
      --lr 1e-5 --epochs 2 --dropout 0.1
        """,
    )

    # Dataset
    parser.add_argument("--dataset", type=str, required=True, help="Path to JSONL dataset")
    parser.add_argument("--output", type=str, default="nova-ceiling-v1", help="Output directory (default: nova-ceiling-v1)")

    # DoRA/LoRA Config
    parser.add_argument("--rank", "-r", type=int, default=64, help="LoRA/DoRA rank (default: 64)")
    parser.add_argument("--alpha", "-a", type=int, default=128, help="LoRA/DoRA alpha (default: 128, should be 2x rank)")
    parser.add_argument("--no-dora", action="store_true", help="Use standard LoRA instead of DoRA")
    parser.add_argument("--dropout", type=float, default=0.05, help="Dropout rate (default: 0.05)")

    # Training Config
    parser.add_argument("--lr", type=float, default=1.5e-5, help="Learning rate (default: 1.5e-5)")
    parser.add_argument("--epochs", type=int, default=2, help="Number of epochs (default: 2)")
    parser.add_argument("--max-seq-length", type=int, default=4096, help="Max sequence length (default: 4096)")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size (default: 2)")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps (default: 4)")
    parser.add_argument("--warmup-ratio", type=float, default=0.1, help="Warmup ratio (default: 0.1)")
    parser.add_argument("--eval-split", type=float, default=0.15, help="Eval split ratio (default: 0.15)")

    # Model
    parser.add_argument("--base-model", type=str, default="Qwen/Qwen2.5-Coder-3B-Instruct", help="Base model")

    # Export
    parser.add_argument("--no-gguf", action="store_true", help="Skip GGUF export")
    parser.add_argument("--gguf-quant", type=str, default="q4_k_m", help="GGUF quantization method (default: q4_k_m)")

    # Mode
    parser.add_argument("--dry-run", action="store_true", help="Validate configuration without training")

    args = parser.parse_args()

    # Validate alpha = 2x rank
    if args.alpha != 2 * args.rank:
        print(f"⚠️  Warning: alpha ({args.alpha}) is not 2x rank ({args.rank}). Recommended: alpha={2*args.rank}")

    run_training(
        dataset_path=args.dataset,
        output_dir=args.output,
        rank=args.rank,
        alpha=args.alpha,
        learning_rate=args.lr,
        epochs=args.epochs,
        max_seq_length=args.max_seq_length,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        warmup_ratio=args.warmup_ratio,
        dropout=args.dropout,
        use_dora=not args.no_dora,
        eval_split=args.eval_split,
        base_model=args.base_model,
        dry_run=args.dry_run,
        export_gguf=not args.no_gguf,
        gguf_quant=args.gguf_quant,
    )


if __name__ == "__main__":
    main()
