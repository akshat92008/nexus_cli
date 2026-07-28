from __future__ import annotations

import argparse
from pathlib import Path

from nova_v12.data.validators import validate_dpo_record
from nova_v12.training.common import dtype_from_config, load_config, load_records, save_run_metadata, set_seed


def train(config_path: str | Path) -> None:
    try:
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import DPOConfig, DPOTrainer
    except ImportError as exc:
        raise RuntimeError("install the train extra") from exc
    config = load_config(config_path)
    seed = int(config.get("seed", 42))
    set_seed(seed)
    train_records = load_records(config.get("train_files", []))
    validation_records = load_records(config.get("validation_files", []))
    for record in train_records + validation_records:
        report = validate_dpo_record(record)
        if not report.valid:
            raise ValueError(f"invalid DPO record {record.get('id')}: {report.errors}")
    dataset_fields = ("prompt", "chosen", "rejected")
    train_dataset = Dataset.from_list([{field: item[field] for field in dataset_fields} for item in train_records])
    eval_dataset = Dataset.from_list([{field: item[field] for field in dataset_fields} for item in validation_records])
    base_model = str(config["base_model"])
    tokenizer = AutoTokenizer.from_pretrained(base_model, revision=config.get("revision"), trust_remote_code=bool(config.get("trust_remote_code", False)))
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        revision=config.get("revision"),
        trust_remote_code=bool(config.get("trust_remote_code", False)),
        torch_dtype=dtype_from_config(config),
        device_map="auto" if config.get("device_map", "auto") == "auto" else None,
    )
    arguments = DPOConfig(
        output_dir=str(config["output_dir"]),
        learning_rate=float(config.get("learning_rate", 5e-6)),
        num_train_epochs=float(config.get("num_train_epochs", 1)),
        per_device_train_batch_size=int(config.get("per_device_train_batch_size", 1)),
        per_device_eval_batch_size=int(config.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(config.get("gradient_accumulation_steps", 16)),
        beta=float(config.get("beta", 0.1)),
        max_length=int(config.get("max_length", 8192)),
        max_prompt_length=int(config.get("max_prompt_length", 4096)),
        bf16=bool(config.get("bf16", False)),
        fp16=bool(config.get("fp16", False)),
        report_to=config.get("report_to", "none"),
        eval_strategy="steps" if validation_records else "no",
        save_steps=int(config.get("save_steps", 250)),
        logging_steps=int(config.get("logging_steps", 10)),
        seed=seed,
    )
    trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=arguments,
        processing_class=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset if validation_records else None,
    )
    trainer.train(resume_from_checkpoint=config.get("resume_from_checkpoint"))
    trainer.save_model(str(config["output_dir"]))
    tokenizer.save_pretrained(str(config["output_dir"]))
    save_run_metadata(config["output_dir"], config, {"train_records": len(train_records), "validation_records": len(validation_records)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    train(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
