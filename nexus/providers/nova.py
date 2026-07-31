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

    # ── Provider protocol ────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return "nova"

    @property
    def name(self) -> str:
        return "Nova Local Pipeline"

    # ── Core chat methods ────────────────────────────────────────────────────

    def chat(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run the Nova pipeline with the last user message as input.

        max_tokens / temperature are accepted for protocol compatibility but
        are not forwarded to the local pipeline (Nova manages its own limits).
        """
        user_input = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                user_input = content if isinstance(content, str) else str(content)
                break

        result = self._backend.run(user_input)

        if stream:
            # Wrap in a minimal streaming-compatible generator so the engine
            # does not need to branch on provider type.
            def _stream():
                class DummyChunk:
                    class _Choice:
                        class _Delta:
                            tool_calls = None

                            def __init__(self, content: str):
                                self.content = content

                        def __init__(self, content: str):
                            self.delta = self._Delta(content)

                    def __init__(self, content: str):
                        self.choices = [self._Choice(content)]

                yield DummyChunk(result.output)

            return _stream()

        return result

    def chat_sync(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Blocking Nova pipeline call (same as non-streaming chat)."""
        return self.chat(
            model_id,
            messages,
            tools=tools,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def count_tokens(self, text: str) -> int:
        return len(text) // 4  # Fallback estimate
