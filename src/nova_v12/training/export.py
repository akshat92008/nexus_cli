from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def merge_adapter(base_model: str, adapter: str, output: str, *, trust_remote_code: bool = False) -> None:
    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("install the train extra") from exc
    model = AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=trust_remote_code, device_map="cpu")
    merged = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(target, safe_serialization=True)
    AutoTokenizer.from_pretrained(adapter, trust_remote_code=trust_remote_code).save_pretrained(target)


def run_checked(command: list[str]) -> None:
    executable = shutil.which(command[0]) or (command[0] if Path(command[0]).exists() else None)
    if executable is None:
        raise FileNotFoundError(command[0])
    command = [executable, *command[1:]]
    proc = subprocess.run(command, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--base-model", required=True)
    merge.add_argument("--adapter", required=True)
    merge.add_argument("--output", required=True)
    merge.add_argument("--trust-remote-code", action="store_true")
    gguf = sub.add_parser("gguf")
    gguf.add_argument("--convert-script", required=True)
    gguf.add_argument("--model", required=True)
    gguf.add_argument("--output", required=True)
    gguf.add_argument("--outtype", default="f16")
    quant = sub.add_parser("quantize")
    quant.add_argument("--binary", required=True)
    quant.add_argument("--input", required=True)
    quant.add_argument("--output", required=True)
    quant.add_argument("--type", default="Q4_K_M")
    args = parser.parse_args(argv)
    if args.command == "merge":
        merge_adapter(args.base_model, args.adapter, args.output, trust_remote_code=args.trust_remote_code)
    elif args.command == "gguf":
        run_checked(["python", args.convert_script, args.model, "--outfile", args.output, "--outtype", args.outtype])
    else:
        run_checked([args.binary, args.input, args.output, args.type])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
