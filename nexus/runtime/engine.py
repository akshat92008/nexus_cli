"""
Execution Engine for Nexus.
Handles the core agentic loop, tool dispatching, and state management.
"""

import json
import logging
import time
from typing import Callable, Generator

from nexus.providers.base import Provider
from nexus.runtime.events import (
    BaseEvent,
    ErrorEvent,
    ModelRequestCompleted,
    ModelRequestStarted,
    ModelStreamChunk,
    RunCompleted,
    RunFailed,
    RunStarted,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
    TurnStarted,
)
from nexus.runtime.state_machine import RunState, StateMachine

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """The canonical execution engine for the Nexus agent.

    Manages the state machine and emits events during execution.

    Args:
        provider: Any object that satisfies the Provider protocol.
        max_turns: Maximum agentic turns before giving up.
        model_id: The effective model string to send to the provider API.
                  If omitted, falls back to ``provider.model_id`` or
                  ``provider.id``.
        run_id: Identifier for this run, used in RunStarted events for
                provenance correlation with the run ledger.
    """

    def __init__(
        self,
        provider: Provider,
        max_turns: int = 50,
        model_id: str | None = None,
        run_id: str | None = None,
    ):
        self.provider = provider
        self.max_turns = max_turns
        # Resolve the model ID: explicit > provider.model_id > provider.id
        self.model_id = (
            model_id
            or getattr(provider, "model_id", None)
            or getattr(provider, "id", "unknown")
        )
        self.run_id = run_id or f"run_{int(time.time() * 1000)}"
        self.state_machine = StateMachine()
        self._handlers: list[Callable[[BaseEvent], None]] = []

        self.tool_executor: Callable[[str, dict], tuple[bool, str]] | None = None
        self.before_tool_hook: Callable[[str, dict], None] | None = None
        self.after_tool_hook: Callable[[str, dict, bool, str], None] | None = None

    def add_event_handler(self, handler: Callable[[BaseEvent], None]):
        """Register a callback for runtime events."""
        self._handlers.append(handler)

    def _emit(self, event: BaseEvent):
        """Emit an event to all registered handlers."""
        for handler in self._handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error("Error in event handler: %s", e)

    def run(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Generator[BaseEvent, None, None]:
        """Execute the agentic loop.

        Yields events as they happen, and also calls registered event handlers.
        """
        if not self.state_machine.transition_to(RunState.EXECUTING):
            yield self._create_and_emit(
                ErrorEvent(message="Cannot start run from current state")
            )
            return

        yield self._create_and_emit(
            RunStarted(conversation_id=self.run_id, model=self.model_id)
        )

        iteration = 0
        current_messages = list(messages)

        while iteration < self.max_turns:
            iteration += 1
            yield self._create_and_emit(TurnStarted(turn_number=iteration))

            # Emit Model Request
            yield self._create_and_emit(
                ModelRequestStarted(model=self.model_id, messages=current_messages)
            )

            try:
                stream = self.provider.chat(
                    model_id=self.model_id,
                    messages=current_messages,
                    tools=tools,
                    stream=True,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as e:
                yield self._create_and_emit(ErrorEvent(message=f"Provider error: {e}"))
                self.state_machine.transition_to(RunState.FAILED)
                yield self._create_and_emit(RunFailed(error=str(e)))
                return

            # Process Stream
            full_content, tool_calls = yield from self._process_stream(stream)
            yield self._create_and_emit(ModelRequestCompleted(model=self.model_id))

            # Record assistant message
            assistant_msg: dict = {"role": "assistant"}
            if full_content:
                assistant_msg["content"] = full_content
            if tool_calls:
                # Format for OpenAI schema — arguments MUST be a JSON string
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": (
                                tc["arguments"]
                                if isinstance(tc["arguments"], str)
                                else json.dumps(tc["arguments"])
                            ),
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ]
            current_messages.append(assistant_msg)

            yield self._create_and_emit(
                TurnCompleted(
                    turn_number=iteration,
                    content=full_content,
                    tool_calls=tool_calls,
                )
            )

            if not tool_calls:
                # No more tools to call — clean completion
                break

            # Execute Tools
            for tc in tool_calls:
                tool_name = tc.get("name")
                args = tc.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        pass  # Pass raw string if it's not valid JSON

                safe_args = args if isinstance(args, dict) else {"raw": args}

                yield self._create_and_emit(
                    ToolCallStarted(tool_name=tool_name, arguments=safe_args)
                )

                # Hook isolation: hook exceptions must not crash the execution loop
                if self.before_tool_hook:
                    try:
                        self.before_tool_hook(tool_name, safe_args)
                    except Exception as hook_exc:
                        logger.warning("before_tool_hook raised: %s", hook_exc)

                if self.tool_executor:
                    try:
                        success, result_text = self.tool_executor(tool_name, safe_args)
                    except Exception as e:
                        success, result_text = False, f"Tool executor error: {e}"
                else:
                    success, result_text = False, "No tool executor registered"

                if self.after_tool_hook:
                    try:
                        self.after_tool_hook(tool_name, safe_args, success, result_text)
                    except Exception as hook_exc:
                        logger.warning("after_tool_hook raised: %s", hook_exc)

                yield self._create_and_emit(
                    ToolCallCompleted(
                        tool_name=tool_name,
                        arguments=safe_args,
                        result=result_text,
                        success=success,
                        error=None if success else result_text,
                    )
                )

                # Append tool result
                current_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": tool_name,
                        "content": result_text,
                    }
                )
        else:
            # Max turns exhausted with tool calls still pending — this is a
            # partial/failed outcome, not a clean completion.
            logger.warning(
                "ExecutionEngine: max_turns (%d) exhausted with pending tool calls.",
                self.max_turns,
            )
            self.state_machine.transition_to(RunState.FAILED)
            yield self._create_and_emit(
                RunFailed(error=f"Max turns ({self.max_turns}) exhausted")
            )
            return

        self.state_machine.transition_to(RunState.COMPLETED)

        # Extract the final content from the last assistant message
        final_content = ""
        for msg in reversed(current_messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_content = msg["content"]
                break

        yield self._create_and_emit(RunCompleted(content=final_content))

    def _create_and_emit(self, event: BaseEvent) -> BaseEvent:
        self._emit(event)
        return event

    def _process_stream(self, stream) -> tuple[str, list[dict]]:
        """Process the generator from the provider."""
        full_content = ""
        tool_calls_accum: dict[int, dict] = {}

        for chunk in stream:
            if not hasattr(chunk, "choices") or not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if hasattr(delta, "content") and delta.content:
                full_content += delta.content
                yield self._create_and_emit(ModelStreamChunk(text=delta.content))

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_accum:
                        tool_calls_accum[idx] = {
                            "id": tc.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_accum[idx]["id"] = tc.id
                    if hasattr(tc, "function") and tc.function:
                        if tc.function.name:
                            tool_calls_accum[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_accum[idx]["arguments"] += tc.function.arguments

        tool_calls = []
        for idx in sorted(tool_calls_accum.keys()):
            tc = tool_calls_accum[idx]
            if tc["name"]:
                if not tc.get("id"):
                    tc["id"] = f"call_{idx}_{int(time.time() * 1000)}"
                tool_calls.append(tc)

        return full_content, tool_calls
