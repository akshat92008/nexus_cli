#!/usr/bin/env python3
"""Call a real Ollama model once and print the literal prompt and response."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="nova_codex")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    payload = json.dumps(
        {
            "model": args.model,
            "prompt": args.prompt,
            "stream": False,
            "options": {"temperature": args.temperature, "num_ctx": 4096},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    print(f"MODEL: {args.model}")
    print("RAW PROMPT:")
    print(args.prompt)
    print("\nRAW OUTPUT:")
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"[REQUEST ERROR] {type(exc).__name__}: {exc}")
        print(f"ELAPSED_SECONDS: {time.time() - started:.3f}")
        return 1

    print(result.get("response", ""))
    print("\nOLLAMA METADATA:")
    metadata = {key: value for key, value in result.items() if key != "response"}
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    print(f"ELAPSED_SECONDS: {time.time() - started:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
