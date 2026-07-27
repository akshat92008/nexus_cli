# Robust 4-Bit QLoRA Fine-Tuning Script for Google Colab (Python 3.12 Compatible)
# Fine-tunes your custom jarvis-nova-1.5b model reliably using HuggingFace PEFT & TRL!

import os
import sys

print("Installing core training dependencies...")
os.system('pip install -q transformers datasets trl peft accelerate bitsandbytes')

import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from peft import LoraConfig, get_peft_model

max_seq_length = 2048
model_name = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

print("1. Loading Model with 4-bit NF4 Quantization...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)

tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=bnb_config,
    device_map="auto"
)

print("2. Applying LoRA Adapters (r=32, alpha=64)...")
peft_config = LoraConfig(
    r=32,
    lora_alpha=64,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)
model = get_peft_model(model, peft_config)

print("3. Loading dataset_nova.jsonl...")
dataset = load_dataset("json", data_files={"train": "dataset_nova.jsonl"}, split="train")

def format_prompts(examples):
    instructions = examples["instruction"]
    outputs = examples["output"]
    texts = []
    for inst, out in zip(instructions, outputs):
        text = f"<|im_start|>user\n{inst}<|im_end|>\n<|im_start|>assistant\n{out}<|im_end|>"
        texts.append(text)
    return {"text": texts}

dataset = dataset.map(format_prompts, batched=True)

print("4. Executing Training Loop...")
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=max_seq_length,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        max_steps=60,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=1,
        output_dir="outputs",
    ),
)
trainer.train()

print("5. Saving Custom Fine-Tuned Model Weights...")
model.save_pretrained("jarvis-nova-1.5b")
tokenizer.save_pretrained("jarvis-nova-1.5b")
print("==========================================================================")
print("SUCCESS! Model training complete! Saved to 'jarvis-nova-1.5b'")
print("==========================================================================")
