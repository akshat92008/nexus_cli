#!/usr/bin/env python3
"""
train_nova3b_colab.py — Production QLoRA Fine-Tuning for Nova 3B (Amaura)

Designed to run on Google Colab's free T4 GPU. Fine-tunes Qwen2.5-Coder-3B-Instruct
into the Nova 3B "Intern" execution engine using Unsloth's 4-bit QLoRA.

Key Design Decisions:
  - QLoRA (not full fine-tune) — fits in T4's 16GB VRAM
  - r=32, alpha=32 — the scoped v11 retrain configuration
  - All linear layers targeted — maximizes format learning capacity
  - LR 5e-5 with linear decay — conservative learning rate for the scoped retrain
  - System prompt injected into EVERY example — model internalizes the persona
  - 10% eval split — detects overfitting before export
  - Fail closed — no CUDA, training failure, or GGUF failure exits nonzero

Usage (Google Colab):
  # Cell 1: Install
  !pip install -U unsloth datasets

  # Cell 2: Upload your dataset to Colab, then run:
  !python train_nova3b_colab.py --dataset dataset_nova3b_v11.jsonl \
      --expected-dataset-sha256 b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991

  # Cell 3: Download the GGUF from the output directory

Part of the Nova model family by Amaura.
"""

import os
import sys
import json
import argparse
import hashlib
import inspect
import platform
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path


EXPECTED_V11_SHA256 = "b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991"


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    # Model
    "base_model": "Qwen/Qwen2.5-Coder-3B-Instruct",
    "max_seq_length": 2048,
    
    # LoRA
    "lora_rank": 32,
    "lora_alpha": 32,
    "lora_dropout": 0.0,
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    
    # Training
    "epochs": 2,
    "learning_rate": 5e-5,
    "per_device_batch_size": 2,
    "gradient_accumulation_steps": 4,
    "warmup_steps": 10,
    "weight_decay": 0.01,
    "lr_scheduler": "linear",
    "max_grad_norm": 1.0,
    
    # Eval
    "eval_split": 0.10,
    "eval_steps": 50,
    "logging_steps": 5,
    "save_steps": 200,
    
    # Export
    "gguf_quantization": "q4_k_m",
    "output_dir": "nova3b-output",
}


# The system prompt that gets injected into EVERY training example
NOVA_SYSTEM_PROMPT = """You are Nova, an elite coding execution engine developed by Amaura.
You receive specific, narrow coding tasks and execute them with surgical precision.

You MUST respond using this EXACT format — no exceptions:

<<THINKING>>
Brief internal monologue (1-3 sentences). State what you will do.

<<FILES>>
```<language>
# filepath: path/to/file.ext
# action: CREATE | MODIFY

[your code here]
```

<<TEST_COMMAND>>
[exact shell command to verify]"""


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset Processing
# ═══════════════════════════════════════════════════════════════════════════════

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def _load_validated_entries(dataset_path: str) -> list[dict]:
    """Load every non-empty JSONL row; reject the entire dataset on any bad row."""
    if not os.path.isfile(dataset_path):
        raise FileNotFoundError(f"Dataset does not exist: {dataset_path}")

    entries = []
    errors = []
    with open(dataset_path, "r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_num}: invalid JSON: {exc}")
                continue

            if not isinstance(entry, dict):
                errors.append(f"line {line_num}: top-level value is not an object")
                continue

            if "messages" in entry:
                messages = entry["messages"]
                if not isinstance(messages, list):
                    errors.append(f"line {line_num}: messages is not a list")
                    continue
                valid_messages = all(
                    isinstance(msg, dict)
                    and msg.get("role") in {"system", "user", "assistant"}
                    and isinstance(msg.get("content"), str)
                    for msg in messages
                )
                has_user = any(msg.get("role") == "user" and msg.get("content") for msg in messages if isinstance(msg, dict))
                has_assistant = any(msg.get("role") == "assistant" and msg.get("content") for msg in messages if isinstance(msg, dict))
                if not valid_messages or not has_user or not has_assistant:
                    errors.append(f"line {line_num}: invalid or incomplete messages array")
                    continue
            elif "instruction" in entry and "output" in entry:
                if not isinstance(entry["instruction"], str) or not entry["instruction"].strip():
                    errors.append(f"line {line_num}: instruction is empty or not text")
                    continue
                if not isinstance(entry["output"], str) or not entry["output"].strip():
                    errors.append(f"line {line_num}: output is empty or not text")
                    continue
            else:
                errors.append(f"line {line_num}: missing messages or instruction/output fields")
                continue

            entries.append(entry)

    if errors:
        preview = "\n".join(f"  - {error}" for error in errors[:20])
        if len(errors) > 20:
            preview += f"\n  - ... and {len(errors) - 20} more"
        raise ValueError(f"Dataset validation failed with {len(errors)} error(s):\n{preview}")
    if not entries:
        raise ValueError("Dataset contains no valid entries")
    return entries


def process_dataset(dataset_path: str, eval_split: float = 0.10):
    """
    Load and process the dataset into ChatML format with system prompt injection.
    Supports both the v5 format (messages array) and legacy format (instruction/output).
    """
    from datasets import Dataset
    import random
    
    print(f"📂 Loading dataset: {dataset_path}")
    
    entries = _load_validated_entries(dataset_path)
    
    print(f"   Loaded {len(entries)} entries")
    
    # Convert to unified text format with system prompt
    processed = []
    for entry in entries:
        # Handle both formats
        if "messages" in entry:
            messages = entry["messages"]
            user_msg = ""
            assistant_msg = ""
            for msg in messages:
                if msg["role"] == "user":
                    user_msg = msg["content"]
                elif msg["role"] == "assistant":
                    assistant_msg = msg["content"]
        elif "instruction" in entry:
            user_msg = entry["instruction"]
            assistant_msg = entry.get("output", "")
        else:
            raise AssertionError("validated dataset entry has an unsupported schema")
        
        if not user_msg or not assistant_msg:
            raise AssertionError("validated dataset entry lost its user or assistant text")
        
        # Build ChatML text with system prompt
        text = (
            f"<|im_start|>system\n{NOVA_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n{assistant_msg}<|im_end|>"
        )
        
        processed.append({"text": text})
    
    # Shuffle and split
    random.seed(3407)
    random.shuffle(processed)
    
    split_idx = int(len(processed) * (1 - eval_split))
    train_data = processed[:split_idx]
    eval_data = processed[split_idx:]
    
    print(f"   ✅ Train: {len(train_data)} | Eval: {len(eval_data)}")
    
    train_dataset = Dataset.from_list(train_data)
    eval_dataset = Dataset.from_list(eval_data)
    
    return train_dataset, eval_dataset


# ═══════════════════════════════════════════════════════════════════════════════
# Training Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def run_training(
    dataset_path: str,
    output_dir: str = DEFAULT_CONFIG["output_dir"],
    epochs: int = DEFAULT_CONFIG["epochs"],
    rank: int = DEFAULT_CONFIG["lora_rank"],
    alpha: int = DEFAULT_CONFIG["lora_alpha"],
    learning_rate: float = DEFAULT_CONFIG["learning_rate"],
    max_seq_length: int = DEFAULT_CONFIG["max_seq_length"],
    batch_size: int = DEFAULT_CONFIG["per_device_batch_size"],
    grad_accum: int = DEFAULT_CONFIG["gradient_accumulation_steps"],
    eval_split: float = DEFAULT_CONFIG["eval_split"],
    base_model: str = DEFAULT_CONFIG["base_model"],
    export_gguf: bool = True,
    gguf_quant: str = DEFAULT_CONFIG["gguf_quantization"],
    dry_run: bool = False,
    expected_dataset_sha256: str = "",
):
    """Main training pipeline — runs on Colab T4 or any CUDA GPU."""
    
    print("=" * 70)
    print("  🚀 AMAURA — Nova 3B QLoRA Fine-Tuning Pipeline")
    print("=" * 70)
    print()
    print("📋 Configuration:")
    print(f"   Base Model:      {base_model}")
    print(f"   LoRA Rank:       {rank}")
    print(f"   LoRA Alpha:      {alpha}")
    print(f"   Epochs:          {epochs}")
    print(f"   Learning Rate:   {learning_rate}")
    print(f"   Batch Size:      {batch_size} × {grad_accum} = {batch_size * grad_accum} effective")
    print(f"   Max Seq Length:  {max_seq_length}")
    print(f"   Eval Split:      {eval_split}")
    print(f"   Output:          {output_dir}")
    print(f"   GGUF Export:     {export_gguf} ({gguf_quant})")
    print(f"   Started (UTC):   {_utc_now()}")
    print("-" * 70)

    dataset_sha256 = _sha256_file(dataset_path)
    print(f"\n🔐 Dataset SHA-256: {dataset_sha256}")
    if expected_dataset_sha256 and dataset_sha256.lower() != expected_dataset_sha256.lower():
        raise ValueError(
            "Dataset SHA-256 mismatch: "
            f"expected {expected_dataset_sha256.lower()}, got {dataset_sha256.lower()}"
        )
    dataset_summary = _validate_dataset_only(dataset_path, eval_split)
    
    if dry_run:
        print("\n🏗️  DRY RUN COMPLETE — dataset and configuration validated; no training was attempted")
        return

    if os.path.isdir(output_dir) and os.listdir(output_dir):
        raise FileExistsError(
            f"Output directory is not empty: {output_dir}. Use a fresh directory so stale artifacts cannot be mixed into this run."
        )
    
    # ── Step 1: Load model ────────────────────────────────────────────────
    try:
        from unsloth import FastLanguageModel
        import torch
        from trl import SFTConfig, SFTTrainer
    except ImportError as e:
        raise RuntimeError(
            "Required training dependency is unavailable. Install with: "
            "pip install -U unsloth datasets. No output artifact was created."
        ) from e

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required for this real training run. No output artifact was created.")

    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "gpu_count": torch.cuda.device_count(),
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_capability": list(torch.cuda.get_device_capability(0)),
        "unsloth": _package_version("unsloth"),
        "unsloth_zoo": _package_version("unsloth_zoo"),
        "transformers": _package_version("transformers"),
        "trl": _package_version("trl"),
        "datasets": _package_version("datasets"),
    }
    print("\n🧾 Real-run environment:")
    print(json.dumps(environment, indent=2, sort_keys=True))
    
    print(f"\n🔧 [Step 1/5] Loading {base_model} with 4-bit quantization...")
    
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=True,
    )
    
    print(f"   ✅ Model loaded. Parameters: {model.num_parameters():,}")
    
    # ── Step 2: Apply LoRA ────────────────────────────────────────────────
    print(f"\n🔧 [Step 2/5] Applying LoRA adapters (r={rank}, α={alpha})...")
    
    model = FastLanguageModel.get_peft_model(
        model,
        r=rank,
        target_modules=DEFAULT_CONFIG["target_modules"],
        lora_alpha=alpha,
        lora_dropout=DEFAULT_CONFIG["lora_dropout"],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    
    # Count trainable parameters
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"   ✅ LoRA applied. Trainable: {trainable:,} / {total:,} "
          f"({trainable/total*100:.2f}%)")
    
    # ── Step 3: Load dataset ──────────────────────────────────────────────
    print(f"\n🔧 [Step 3/5] Processing dataset...")
    
    train_dataset, eval_dataset = process_dataset(dataset_path, eval_split)
    
    # Compute training steps
    steps_per_epoch = max(1, len(train_dataset) // (batch_size * grad_accum))
    total_steps = steps_per_epoch * epochs
    
    print(f"   Steps per epoch: {steps_per_epoch}")
    print(f"   Total steps:     {total_steps}")
    
    # ── Step 4: Train ─────────────────────────────────────────────────────
    print(f"\n🔧 [Step 4/5] Starting training ({epochs} epochs)...")
    
    sft_kwargs = {
        "output_dir": output_dir,
        "num_train_epochs": epochs,
        "per_device_train_batch_size": batch_size,
        "per_device_eval_batch_size": batch_size,
        "gradient_accumulation_steps": grad_accum,
        "learning_rate": learning_rate,
        "lr_scheduler_type": DEFAULT_CONFIG["lr_scheduler"],
        "warmup_steps": DEFAULT_CONFIG["warmup_steps"],
        "weight_decay": DEFAULT_CONFIG["weight_decay"],
        "max_grad_norm": DEFAULT_CONFIG["max_grad_norm"],
        "fp16": not torch.cuda.is_bf16_supported(),
        "bf16": torch.cuda.is_bf16_supported(),
        "logging_strategy": "steps",
        "logging_steps": DEFAULT_CONFIG["logging_steps"],
        "eval_strategy": "epoch",
        "save_strategy": "epoch",
        "save_total_limit": 2,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_loss",
        "greater_is_better": False,
        "optim": "adamw_8bit",
        "seed": 3407,
        "report_to": "none",
        "dataset_text_field": "text",
        "dataset_num_proc": 2,
        "packing": False,
    }
    sft_parameters = inspect.signature(SFTConfig.__init__).parameters
    if "max_length" in sft_parameters:
        sft_kwargs["max_length"] = max_seq_length
    elif "max_seq_length" in sft_parameters:
        sft_kwargs["max_seq_length"] = max_seq_length
    else:
        raise RuntimeError("Installed TRL SFTConfig exposes neither max_length nor max_seq_length")
    if "eval_strategy" not in sft_parameters and "evaluation_strategy" in sft_parameters:
        sft_kwargs["evaluation_strategy"] = sft_kwargs.pop("eval_strategy")
    training_args = SFTConfig(**sft_kwargs)

    trainer_kwargs = {
        "model": model,
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "args": training_args,
    }
    trainer_parameters = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in trainer_parameters:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_parameters:
        trainer_kwargs["tokenizer"] = tokenizer
    else:
        raise RuntimeError("Installed TRL SFTTrainer accepts neither processing_class nor tokenizer")
    trainer = SFTTrainer(**trainer_kwargs)

    training_started_at = _utc_now()
    print(f"\n   TRAINING_STARTED_AT_UTC={training_started_at}")
    train_result = trainer.train()
    training_finished_at = _utc_now()
    print(f"   TRAINING_FINISHED_AT_UTC={training_finished_at}")
    print(f"   ✅ Training complete. Train loss: {train_result.training_loss:.6f}")
    print("\n   TRAINER_LOG_HISTORY_JSON_BEGIN")
    print(json.dumps(trainer.state.log_history, indent=2, sort_keys=True, default=str))
    print("   TRAINER_LOG_HISTORY_JSON_END")

    best_checkpoint = trainer.state.best_model_checkpoint
    print(f"   BEST_CHECKPOINT={best_checkpoint}")
    
    # Save LoRA adapter
    print(f"\n   💾 Saving LoRA adapter to {output_dir}/")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    # ── Step 5: Export GGUF ───────────────────────────────────────────────
    if export_gguf:
        print(f"\n🔧 [Step 5/5] Exporting to GGUF ({gguf_quant})...")
        model.save_pretrained_gguf(
            output_dir,
            tokenizer=tokenizer,
            quantization_method=gguf_quant,
        )

        # Unsloth versions differ: some write into output_dir, while others
        # create a sibling directory named "<output_dir>_gguf". Search both
        # locations recursively rather than treating the latter as an export
        # failure.
        gguf_roots = [Path(output_dir), Path(f"{output_dir}_gguf")]
        gguf_paths = sorted({
            str(path)
            for root in gguf_roots
            if root.is_dir()
            for path in root.rglob("*.gguf")
        })
        if not gguf_paths:
            raise RuntimeError("GGUF export returned without producing a .gguf file")

        gguf_artifacts = []
        for gguf_path in gguf_paths:
            size_bytes = os.path.getsize(gguf_path)
            with open(gguf_path, "rb") as fh:
                magic = fh.read(4)
            if magic != b"GGUF":
                raise RuntimeError(f"Exported file lacks GGUF magic bytes: {gguf_path} ({magic!r})")
            if size_bytes < 100 * 1024 * 1024:
                raise RuntimeError(f"Exported GGUF is implausibly small: {gguf_path} ({size_bytes} bytes)")
            artifact = {
                "path": os.path.abspath(gguf_path),
                "size_bytes": size_bytes,
                "sha256": _sha256_file(gguf_path),
                "mtime_utc": datetime.fromtimestamp(os.path.getmtime(gguf_path), timezone.utc).isoformat(),
            }
            gguf_artifacts.append(artifact)
            print(f"   ✅ GGUF verified: {json.dumps(artifact, sort_keys=True)}")
    else:
        gguf_artifacts = []

    completed_at = _utc_now()
    evidence = {
        "status": "real_training_and_export_complete" if export_gguf else "real_training_complete_no_gguf_requested",
        "dataset": {
            "path": os.path.abspath(dataset_path),
            "sha256": dataset_sha256,
            **dataset_summary,
        },
        "configuration": {
            "base_model": base_model,
            "epochs": epochs,
            "lora_rank": rank,
            "lora_alpha": alpha,
            "learning_rate": learning_rate,
            "max_seq_length": max_seq_length,
            "per_device_batch_size": batch_size,
            "gradient_accumulation_steps": grad_accum,
            "eval_split": eval_split,
            "gguf_quantization": gguf_quant if export_gguf else None,
            "seed": 3407,
        },
        "environment": environment,
        "timestamps_utc": {
            "training_started": training_started_at,
            "training_finished": training_finished_at,
            "run_completed": completed_at,
        },
        "train_metrics": train_result.metrics,
        "trainer_log_history": trainer.state.log_history,
        "best_checkpoint": best_checkpoint,
        "gguf_artifacts": gguf_artifacts,
    }
    evidence_path = os.path.join(output_dir, "training_evidence.json")
    with open(evidence_path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2, sort_keys=True, default=str)

    print("\nTRAINING_EVIDENCE_JSON_BEGIN")
    print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
    print("TRAINING_EVIDENCE_JSON_END")
    
    print("\n" + "=" * 70)
    print("  ✅ AMAURA — Nova 3B Training Complete!")
    print("=" * 70)
    print(f"\n📁 Output directory: {output_dir}/")
    print(f"📥 Download the .gguf file to your Mac")
    print(f"🧾 Evidence manifest: {evidence_path}")
    print("Do not deploy until the full stdout log, evidence manifest, and GGUF are verified together.")


# ═══════════════════════════════════════════════════════════════════════════════
# Dataset validation
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_dataset_only(dataset_path: str, eval_split: float):
    """Validate dataset format without training and return a compact summary."""
    
    print(f"\n📊 Validating dataset: {dataset_path}")
    
    entries = _load_validated_entries(dataset_path)
    total = len(entries)
    categories = {}
    for entry in entries:
        cat = entry.get("metadata", {}).get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
    
    print(f"   Total entries: {total}")
    print(f"   Valid entries: {total} (100.0%)")
    print(f"\n   Categories:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"     {cat}: {count}")
    
    split_idx = int(total * (1 - eval_split))
    print(f"\n   Train/Eval split: {split_idx} / {total - split_idx}")
    
    if total < 500:
        print("\n   ⚠️  WARNING: Dataset is small. Recommend 3,000+ examples for robust training.")
    return {
        "entry_count": total,
        "train_count": split_idx,
        "eval_count": total - split_idx,
        "categories": categories,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Amaura — Nova 3B QLoRA Fine-Tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Google Colab Quick Start:
  1. !pip install -U unsloth datasets
  2. Upload dataset_nova3b_v11.jsonl
  3. !python train_nova3b_colab.py --dataset dataset_nova3b_v11.jsonl --expected-dataset-sha256 b2cabc6a26f62cd40e0b0f67c0ad7828e7943149a145cbe9140a0a96e1dfe991
  4. Download the .gguf file from nova3b-output/
        """,
    )
    parser.add_argument("--dataset", type=str, required=True,
                        help="Path to training dataset (JSONL)")
    parser.add_argument("--output", type=str, default=DEFAULT_CONFIG["output_dir"],
                        help="Output directory for model files")
    parser.add_argument("--epochs", type=int, default=DEFAULT_CONFIG["epochs"],
                        help="Number of training epochs")
    parser.add_argument("--rank", type=int, default=DEFAULT_CONFIG["lora_rank"],
                        help="LoRA rank")
    parser.add_argument("--alpha", type=int, default=DEFAULT_CONFIG["lora_alpha"],
                        help="LoRA alpha")
    parser.add_argument("--lr", type=float, default=DEFAULT_CONFIG["learning_rate"],
                        help="Learning rate")
    parser.add_argument("--batch-size", type=int,
                        default=DEFAULT_CONFIG["per_device_batch_size"],
                        help="Per-device batch size")
    parser.add_argument("--max-seq-length", type=int,
                        default=DEFAULT_CONFIG["max_seq_length"],
                        help="Maximum sequence length")
    parser.add_argument("--base-model", type=str,
                        default=DEFAULT_CONFIG["base_model"],
                        help="Base model to fine-tune")
    parser.add_argument("--no-gguf", action="store_true",
                        help="Skip GGUF export")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate config and dataset only")
    parser.add_argument("--expected-dataset-sha256", type=str, default="",
                        help="Abort unless the dataset has this exact SHA-256")
    
    args = parser.parse_args()
    
    run_training(
        dataset_path=args.dataset,
        output_dir=args.output,
        epochs=args.epochs,
        rank=args.rank,
        alpha=args.alpha,
        learning_rate=args.lr,
        max_seq_length=args.max_seq_length,
        batch_size=args.batch_size,
        base_model=args.base_model,
        export_gguf=not args.no_gguf,
        dry_run=args.dry_run,
        expected_dataset_sha256=args.expected_dataset_sha256,
    )
