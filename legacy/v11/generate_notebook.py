import json

notebook = {
    "cells": [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# 🚀 Nova 1.5b: Full 100% Capability Training Pipeline (SFT + DPO + GRPO)\n",
                "This notebook executes the entire training pipeline from scratch using an NVIDIA T4 GPU."
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 1. Install Dependencies\n",
                "!pip install \"unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git\"\n",
                "!pip install --no-deps xformers \"trl<0.9.0\" peft accelerate bitsandbytes\n",
                "import torch\n",
                "if torch.cuda.get_device_capability()[0] >= 8:\n",
                "    !pip install --no-deps packaging ninja einops flash-attn xformers trl peft accelerate bitsandbytes"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 2. Run Supervised Fine-Tuning (SFT)\n",
                "!python train_unsloth.py --dataset dataset_nova_v2.jsonl --output_dir models/nova-sft --epochs 1"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 3. Run Direct Preference Optimization (DPO)\n",
                "!python train_dpo.py --model models/nova-sft --sft-data dataset_nova_v2.jsonl --output-dir models/nova-dpo --epochs 1"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 4. Run Execution-Guided GRPO\n",
                "!python train_grpo.py --model models/nova-dpo --sft-data dataset_nova_v2.jsonl --output-dir models/nova-final --epochs 1"
            ]
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 5. Export Final Model to GGUF\n",
                "from unsloth import FastLanguageModel\n",
                "model, tokenizer = FastLanguageModel.from_pretrained(\n",
                "    model_name = \"models/nova-final\",\n",
                "    max_seq_length = 2048,\n",
                "    dtype = None,\n",
                "    load_in_4bit = True,\n",
                ")\n",
                "model.save_pretrained_gguf(\"nova_1.5b_final\", tokenizer, quantization_method = \"q4_k_m\")\n",
                "print(\"✅ Final Model Exported as nova_1.5b_final-unsloth.Q4_K_M.gguf\")"
            ]
        }
    ],
    "metadata": {
        "colab": {
            "provenance": []
        },
        "kernelspec": {
            "display_name": "Python 3",
            "name": "python3"
        },
        "language_info": {
            "name": "python"
        }
    },
    "nbformat": 4,
    "nbformat_minor": 0
}

with open("Nova_Full_Pipeline.ipynb", "w") as f:
    json.dump(notebook, f, indent=2)

print("Notebook generated.")
