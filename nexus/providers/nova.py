"""
Nova local model provider adapter.
"""

from typing import Any

from nexus.nova_backend import NovaPipelineBackend
from nexus.providers.base import Provider


class NovaProvider(Provider):
    """Adapter for the local Nova 3B pipeline backend."""

    def __init__(self, model_name: str, working_dir: str):
        self.model_name = model_name
        self.working_dir = working_dir
        self._backend = NovaPipelineBackend(
            model=model_name,
            working_dir=working_dir,
        )

    @property
    def id(self) -> str:
        return "nova"

    @property
    def name(self) -> str:
        return "Nova Local Pipeline"

    def chat(self, model_id: str, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> Any:
        # Nova pipeline currently takes the raw user input and processes it through 
        # its own local guardrails and context gathering.
        # We extract the last user message to feed into the pipeline.
        user_input = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_input = msg["content"]
                break
        
        # Return a simulated stream/response format that the engine can process
        result = self._backend.run(user_input)
        
        if stream:
            # Fake stream for compatibility
            def _stream():
                class DummyChunk:
                    class Choice:
                        class Delta:
                            def __init__(self, content):
                                self.content = content
                        def __init__(self, content):
                            self.delta = self.Delta(content)
                    def __init__(self, content):
                        self.choices = [self.Choice(content)]
                yield DummyChunk(result.output)
            return _stream()
            
        return result

    def count_tokens(self, text: str) -> int:
        return len(text) // 4  # Fallback estimate
