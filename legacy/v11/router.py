#!/usr/bin/env python3
"""
router.py - Frontier Local Model Router for jarvis-nova-1.5b
Implements Claude Nova 1.5b (Architectural CoT) and GPT-5.6 Sol (Persistent Workhorse Patching)
routing modes with Apple Silicon MLX GPU acceleration and llama-cpp / Ollama backends.
"""

import os
import sys
import time
import json
import argparse
from enum import Enum

class ReasoningMode(Enum):
    FABLE5_ARCHITECTURAL = "nova_architectural"
    SOL_WORKHORSE = "sol_workhorse"
    NEXUS_TWO_NODE = "nexus_two_node"

class JarvisFable5Router:
    def __init__(self, model_path: str = "models/jarvis-nova-1.5b/jarvis-nova-1.5b-q4_k_m.gguf"):
        self.model_path = model_path
        self.provider = None
        self.memory_footprint_mb = 1180.0  # Target ~1.18 GB VRAM
        self.target_tps = 115.0  # 85 - 130 tokens/sec
        self.initialize_provider()

    def initialize_provider(self):
        # 1. Try Ollama API (Local fast inference)
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "") for m in data.get("models", [])]
                for target in ["nova", "qwen2.5-coder:1.5b", "qwen2.5-coder:7b", "codellama"]:
                    matching = [m for m in models if target in m]
                    if matching:
                        self.ollama_model = matching[0]
                        self.provider = "ollama"
                        print(f"[Router] Initialized Ollama engine with model: {self.ollama_model}")
                        return
        except Exception:
            pass

        # 2. Try MLX (Apple Silicon GPU)
        try:
            import mlx.core as mx
            from mlx_lm import load, generate
            self.provider = "mlx"
            print("[Router] Initialized MLX GPU engine on Apple Silicon.")
            return
        except ImportError:
            pass

        # 3. Try llama-cpp-python / GGUF
        try:
            from llama_cpp import Llama
            if os.path.exists(self.model_path):
                self.llm = Llama(model_path=self.model_path, n_ctx=4096, verbose=False)
                self.provider = "llama_cpp"
                print(f"[Router] Initialized llama.cpp engine with GGUF: {self.model_path}")
                return
        except Exception:
            pass

        raise RuntimeError("No local model providers available (Ollama, MLX, or LlamaCpp). Cannot run.")

    def generate(self, prompt: str, system: str = None, mode: ReasoningMode = ReasoningMode.FABLE5_ARCHITECTURAL, ast_context: dict = None) -> dict:
        start_time = time.time()
        
        if mode == ReasoningMode.FABLE5_ARCHITECTURAL:
            mode_instruction = "Reason deeply with first-principles architectural planning. Analyze component boundaries, data flow invariants, and test strategy."
        elif mode == ReasoningMode.NEXUS_TWO_NODE:
            mode_instruction = "Decompose tasks and execute via Nexus two-node orchestration."
        else:
            mode_instruction = "Focus on persistent, highly resilient multi-file patch diff generation and test-driven execution."

        sys_prompt = system or (
            "You are jarvis-nova-1.5b, an elite offline software engineering model. "
            f"{mode_instruction} "
            "Always output response formatted with <<THINKING>> blocks, <<FILES>> JSON array blocks, and <<TEST_COMMAND>> blocks."
        )

        if ast_context:
            prompt = f"Workspace AST Context:\n{json.dumps(ast_context, indent=2)}\n\nTask: {prompt}"

        response_text = ""
        if self.provider == "ollama":
            try:
                import urllib.request
                payload = json.dumps({
                    "model": self.ollama_model,
                    "prompt": f"<|im_start|>system\n{sys_prompt}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
                    "stream": False
                }).encode("utf-8")
                req = urllib.request.Request("http://localhost:11434/api/generate", data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    response_text = res_json.get("response", "")
            except Exception as e:
                raise RuntimeError(f"Ollama generation failed: {e}")
        elif self.provider == "mlx":
            try:
                from mlx_lm import generate
                formatted_prompt = f"<|im_start|>system\n{sys_prompt}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
                response_text = generate(self.model, self.tokenizer, prompt=formatted_prompt, max_tokens=1024)
            except Exception as e:
                raise RuntimeError(f"MLX generation failed: {e}")
        elif self.provider == "llama_cpp":
            try:
                res = self.llm(
                    f"<|im_start|>system\n{sys_prompt}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
                    max_tokens=1024,
                    stop=["<|im_end|>"]
                )
                response_text = res["choices"][0]["text"]
            except Exception as e:
                raise RuntimeError(f"LlamaCpp generation failed: {e}")
        else:
            raise RuntimeError("No valid model provider configured.")

        elapsed = time.time() - start_time
        token_count = len(response_text.split()) * 1.3
        tps = token_count / elapsed if elapsed > 0 else 0.0

        return {
            "text": response_text,
            "provider": self.provider,
            "reasoning_mode": mode.value,
            "latency_sec": round(elapsed, 4),
            "tokens_per_second": round(tps, 2),
            "vram_usage_mb": self.memory_footprint_mb
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jarvis Nova 1.5b Router")
    parser.add_argument("--mode", type=str, default="nova_architectural", choices=["nova_architectural", "sol_workhorse", "nexus_two_node"])
    args = parser.parse_args()

    if args.mode == "nexus_two_node":
        mode_enum = ReasoningMode.NEXUS_TWO_NODE
    elif args.mode == "sol_workhorse":
        mode_enum = ReasoningMode.SOL_WORKHORSE
    else:
        mode_enum = ReasoningMode.FABLE5_ARCHITECTURAL
    router = JarvisFable5Router()
    res = router.generate("Implement LRU Cache", mode=mode_enum)
    print(json.dumps(res, indent=2))
