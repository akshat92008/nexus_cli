#!/usr/bin/env python3
"""
ollama_client.py — Ollama HTTP API Client for Nova 3B

Clean wrapper around Ollama's REST API for local model inference.
Supports streaming, performance measurement, and model management.

Part of the Nova model family by Amaura.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional, Generator, List, Dict, Any, Callable


@dataclass
class InferenceMetrics:
    """Performance metrics from a single inference call."""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    time_to_first_token_ms: float = 0.0
    total_time_ms: float = 0.0
    tokens_per_second: float = 0.0

    def summary(self) -> str:
        return (
            f"TPS: {self.tokens_per_second:.1f} | "
            f"TTFT: {self.time_to_first_token_ms:.0f}ms | "
            f"Total: {self.total_time_ms:.0f}ms | "
            f"Tokens: {self.completion_tokens}"
        )


@dataclass
class GenerationResult:
    """Complete result from a generation call."""
    text: str
    metrics: InferenceMetrics
    model: str = ""
    done: bool = True


class OllamaClient:
    """
    HTTP client for the Ollama API.
    
    Usage:
        client = OllamaClient()
        
        # Simple generation
        result = client.generate("nova3b", "Write a hello world function")
        print(result.text)
        print(result.metrics.summary())
        
        # Chat-style generation
        result = client.chat("nova3b", [
            {"role": "system", "content": "You are Nova..."},
            {"role": "user", "content": "Write a fibonacci function"},
        ])
        
        # Streaming
        for chunk in client.generate_stream("nova3b", "Hello"):
            print(chunk, end="", flush=True)
    """

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host.rstrip("/")

    # ──────────────────────────────────────────────────────────────────────────
    # Health & Model Management
    # ──────────────────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Check if Ollama server is accessible."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, ConnectionError, OSError):
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        """List all locally available models."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("models", [])
        except Exception:
            return []

    def has_model(self, model_name: str) -> bool:
        """Check if a specific model is available locally."""
        models = self.list_models()
        return any(m.get("name", "").startswith(model_name) for m in models)

    def model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a model."""
        try:
            payload = json.dumps({"name": model_name}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/show",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def create_model(self, name: str, modelfile_path: str) -> bool:
        """Create a model from a Modelfile."""
        try:
            with open(modelfile_path, "r") as f:
                modelfile_content = f.read()
            
            payload = json.dumps({
                "name": name,
                "modelfile": modelfile_content,
            }).encode("utf-8")
            
            req = urllib.request.Request(
                f"{self.host}/api/create",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                # Stream the response to track progress
                for line in resp:
                    data = json.loads(line.decode("utf-8"))
                    status = data.get("status", "")
                    if status:
                        print(f"  [Ollama] {status}")
            return True
        except Exception as e:
            print(f"  [Ollama] Error creating model: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Generation (Raw Prompt)
    # ──────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.2,
        top_p: float = 0.9,
        num_ctx: int = 4096,
        max_tokens: int = 2048,
    ) -> GenerationResult:
        """Generate a completion (non-streaming)."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        start_time = time.time()
        
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return GenerationResult(
                text=f"[ERROR] Ollama request failed: {e}",
                metrics=InferenceMetrics(),
                model=model,
                done=False,
            )

        total_time = (time.time() - start_time) * 1000
        
        # Extract metrics from Ollama's response
        eval_count = result.get("eval_count", 0)
        eval_duration = result.get("eval_duration", 1)  # nanoseconds
        prompt_eval_duration = result.get("prompt_eval_duration", 0)

        tps = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0
        ttft = prompt_eval_duration / 1e6 if prompt_eval_duration > 0 else 0  # ns to ms

        metrics = InferenceMetrics(
            total_tokens=result.get("prompt_eval_count", 0) + eval_count,
            prompt_tokens=result.get("prompt_eval_count", 0),
            completion_tokens=eval_count,
            time_to_first_token_ms=ttft,
            total_time_ms=total_time,
            tokens_per_second=tps,
        )

        return GenerationResult(
            text=result.get("response", ""),
            metrics=metrics,
            model=model,
            done=result.get("done", True),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Chat (Multi-turn Messages)
    # ──────────────────────────────────────────────────────────────────────────

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        top_p: float = 0.9,
        num_ctx: int = 4096,
        max_tokens: int = 2048,
    ) -> GenerationResult:
        """Chat completion with message history."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }

        start_time = time.time()

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return GenerationResult(
                text=f"[ERROR] Ollama chat failed: {e}",
                metrics=InferenceMetrics(),
                model=model,
                done=False,
            )

        total_time = (time.time() - start_time) * 1000

        eval_count = result.get("eval_count", 0)
        eval_duration = result.get("eval_duration", 1)
        prompt_eval_duration = result.get("prompt_eval_duration", 0)

        tps = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0
        ttft = prompt_eval_duration / 1e6 if prompt_eval_duration > 0 else 0

        metrics = InferenceMetrics(
            total_tokens=result.get("prompt_eval_count", 0) + eval_count,
            prompt_tokens=result.get("prompt_eval_count", 0),
            completion_tokens=eval_count,
            time_to_first_token_ms=ttft,
            total_time_ms=total_time,
            tokens_per_second=tps,
        )

        msg = result.get("message", {})
        return GenerationResult(
            text=msg.get("content", ""),
            metrics=metrics,
            model=model,
            done=result.get("done", True),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Streaming Generation
    # ──────────────────────────────────────────────────────────────────────────

    def generate_stream(
        self,
        model: str,
        prompt: str,
        system: str = "",
        temperature: float = 0.2,
        top_p: float = 0.9,
        num_ctx: int = 4096,
        max_tokens: int = 2048,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> GenerationResult:
        """Stream tokens as they are generated. Returns full result when done."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        start_time = time.time()
        first_token_time = None
        full_text = []
        total_eval_count = 0
        final_data = {}

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                for line in resp:
                    chunk = json.loads(line.decode("utf-8"))
                    token = chunk.get("response", "")
                    
                    if token and first_token_time is None:
                        first_token_time = time.time()
                    
                    if token:
                        full_text.append(token)
                        if on_token:
                            on_token(token)
                    
                    if chunk.get("done", False):
                        final_data = chunk
                        break

        except Exception as e:
            return GenerationResult(
                text=f"[ERROR] Stream failed: {e}",
                metrics=InferenceMetrics(),
                model=model,
                done=False,
            )

        total_time = (time.time() - start_time) * 1000
        ttft = ((first_token_time - start_time) * 1000) if first_token_time else 0

        eval_count = final_data.get("eval_count", len(full_text))
        eval_duration = final_data.get("eval_duration", 1)
        tps = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0

        metrics = InferenceMetrics(
            total_tokens=final_data.get("prompt_eval_count", 0) + eval_count,
            prompt_tokens=final_data.get("prompt_eval_count", 0),
            completion_tokens=eval_count,
            time_to_first_token_ms=ttft,
            total_time_ms=total_time,
            tokens_per_second=tps,
        )

        return GenerationResult(
            text="".join(full_text),
            metrics=metrics,
            model=model,
            done=True,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Nova-Specific Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def nova_generate(
        self,
        prompt: str,
        model: str = "nova3b",
        temperature: float = 0.2,
        stream: bool = False,
        max_tokens: int = 4096,
        num_ctx: int = 8192,
    ) -> GenerationResult:
        """
        Generate using the Nova intern model with the branded system prompt.
        This is the primary interface for the multi-agent pipeline.
        """
        NOVA_SYSTEM = (
            'You are Nova, an elite coding execution engine developed by Amaura.\n'
            'You receive specific, narrow coding tasks and execute them with surgical precision.\n\n'
            'You MUST respond using this EXACT format — no exceptions:\n\n'
            '<<THINKING>>\n'
            'Brief internal monologue (1-3 sentences). State what you will do.\n\n'
            '<<FILES>>\n'
            '```<language>\n'
            '# filepath: path/to/file.ext\n'
            '# action: CREATE | MODIFY\n'
            '[for CREATE: the complete new file, with NO patch markers]\n'
            '[for MODIFY only: <<<<<<< then exact old lines, ======= then replacement, >>>>>>>]\n'
            '```\n\n'
            'Use the exact path named by the task; never add src/ or rename it.\n'
            'CREATE means the target does not exist: emit a complete file directly and never hallucinate old code.\n'
            'MODIFY means the target exists: copy the smallest exact old block from supplied context.\n'
            'Never emit a second separator. Finish every import, entrypoint, block, and closing delimiter.\n'
        )

        if stream:
            return self.generate_stream(
                model=model,
                prompt=prompt,
                system=NOVA_SYSTEM,
                temperature=temperature,
                max_tokens=max_tokens,
                num_ctx=num_ctx,
            )
        else:
            return self.generate(
                model=model,
                prompt=prompt,
                system=NOVA_SYSTEM,
                temperature=temperature,
                max_tokens=max_tokens,
                num_ctx=num_ctx,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Quick Test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    client = OllamaClient()

    if not client.is_running():
        print("❌ Ollama is not running. Start it with: ollama serve")
        exit(1)

    print("✅ Ollama is running")
    print(f"   Models: {[m['name'] for m in client.list_models()]}")

    if client.has_model("nova3b"):
        print("\n🚀 Testing Nova 3B generation...")
        result = client.nova_generate(
            "Write a Python function to check if a number is prime.",
            stream=True,
        )
        print(f"\n\n📊 {result.metrics.summary()}")
    else:
        print("\n⚠️  nova3b model not found. Create it with:")
        print("   ollama create nova3b -f Modelfile.amaura")
