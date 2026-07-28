from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nova_v12.data.validators import validate_sft_record
from nova_v12.training.common import (
    apply_lora,
    dtype_from_config,
    ensure_atomic_tokens,
    load_config,
    load_records,
    save_run_metadata,
    set_seed,
)


MODE_TOKEN = {
    "code": "<|nova_code|>",
    "edit": "<|nova_edit|>",
    "debug": "<|nova_debug|>",
    "agent": "<|nova_agent|>",
}


def _encode_record(record: dict[str, Any], tokenizer: Any, max_length: int) -> dict[str, list[int]]:
    report = validate_sft_record(record)
    if not report.valid:
        raise ValueError(f"invalid SFT record {record.get('id')}: {report.errors}")
    messages = list(record["messages"])
    assistant = str(messages[-1]["content"])
    prefix_messages = messages[:-1]
    mode_token = MODE_TOKEN.get(str(record.get("mode")), "")
    if prefix_messages:
        prefix_messages[0] = dict(prefix_messages[0])
        prefix_messages[0]["content"] = mode_token + "\n" + str(prefix_messages[0]["content"])
    if getattr(tokenizer, "chat_template", None):
        prefix = tokenizer.apply_chat_template(prefix_messages, tokenize=False, add_generation_prompt=True)
        full = prefix + assistant + (tokenizer.eos_token or "")
    else:
        prefix = "\n".join(f"{item['role']}: {item['content']}" for item in prefix_messages) + "\nassistant: "
        full = prefix + assistant + (tokenizer.eos_token or "")
    full_ids = tokenizer.encode(full, add_special_tokens=True, truncation=True, max_length=max_length)
    prefix_ids = tokenizer.encode(prefix, add_special_tokens=True, truncation=True, max_length=max_length)
    prefix_length = min(len(prefix_ids), len(full_ids))
    labels = [-100] * prefix_length + full_ids[prefix_length:]
    return {"input_ids": full_ids, "attention_mask": [1] * len(full_ids), "labels": labels}


class CausalCollator:
    def __init__(self, pad_token_id: int) -> None:
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, Any]:
        import torch

        length = max(len(item["input_ids"]) for item in features)
        output = {"input_ids": [], "attention_mask": [], "labels": []}
        for item in features:
            padding = length - len(item["input_ids"])
            output["input_ids"].append(item["input_ids"] + [self.pad_token_id] * padding)
            output["attention_mask"].append(item["attention_mask"] + [0] * padding)
            output["labels"].append(item["labels"] + [-100] * padding)
        return {key: torch.tensor(value, dtype=torch.long) for key, value in output.items()}


def train(config_path: str | Path) -> None:
    try:
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
    except ImportError as exc:
        raise RuntimeError("install the train extra") from exc
    config = load_config(config_path)
    seed = int(config.get("seed", 42))
    set_seed(seed)
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
    added = ensure_atomic_tokens(tokenizer, model)
    model = apply_lora(model, config, train_embeddings=bool(added))
    max_length = int(config.get("max_length", 8192))
    train_records = load_records(config.get("train_files", []))
    validation_records = load_records(config.get("validation_files", []))
    train_encoded = [_encode_record(item, tokenizer, max_length) for item in train_records]
    validation_encoded = [_encode_record(item, tokenizer, max_length) for item in validation_records]
    train_dataset = Dataset.from_list(train_encoded)
    eval_dataset = Dataset.from_list(validation_encoded)
    arguments = TrainingArguments(
        output_dir=str(config["output_dir"]),
        learning_rate=float(config.get("learning_rate", 5e-5)),
        num_train_epochs=float(config.get("num_train_epochs", 2)),
        per_device_train_batch_size=int(config.get("per_device_train_batch_size", 1)),
        per_device_eval_batch_size=int(config.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(config.get("gradient_accumulation_steps", 16)),
        logging_steps=int(config.get("logging_steps", 10)),
        save_steps=int(config.get("save_steps", 250)),
        eval_strategy="steps" if validation_encoded else "no",
        eval_steps=int(config.get("eval_steps", config.get("save_steps", 250))),
        warmup_ratio=float(config.get("warmup_ratio", 0.03)),
        bf16=bool(config.get("bf16", False)),
        fp16=bool(config.get("fp16", False)),
        report_to=config.get("report_to", "none"),
        seed=seed,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=arguments,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset if validation_encoded else None,
        data_collator=CausalCollator(tokenizer.pad_token_id),
    )
    trainer.train(resume_from_checkpoint=config.get("resume_from_checkpoint"))
    trainer.save_model(str(config["output_dir"]))
    tokenizer.save_pretrained(str(config["output_dir"]))
    save_run_metadata(config["output_dir"], config, {"added_tokens": added, "train_records": len(train_records), "validation_records": len(validation_records)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    train(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
