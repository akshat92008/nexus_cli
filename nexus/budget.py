"""Hard per-run limits for hosted model usage."""

from __future__ import annotations

import json
import math
import threading
from dataclasses import asdict, dataclass
from typing import Any


class BudgetExceeded(RuntimeError):
    """Raised before a hosted call that would violate a configured limit."""


@dataclass
class BudgetLimits:
    """Optional hard ceilings. ``None`` means the dimension is unlimited."""

    max_hosted_calls: int | None = None
    max_prompt_tokens: int | None = None
    max_completion_tokens: int | None = None
    max_cost_usd: float | None = None
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None

    def validate(self) -> None:
        for name in ("max_hosted_calls", "max_prompt_tokens", "max_completion_tokens"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in ("max_cost_usd", "input_price_per_million", "output_price_per_million"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.max_cost_usd is not None and (
            self.input_price_per_million is None or self.output_price_per_million is None
        ):
            raise ValueError(
                "A currency ceiling requires explicit input and output prices per million tokens."
            )


@dataclass
class BudgetUsage:
    hosted_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0


class BudgetController:
    """Authorize model calls and account for actual token usage."""

    def __init__(self, limits: BudgetLimits | None = None):
        self.limits = limits or BudgetLimits()
        self.limits.validate()
        self.usage = BudgetUsage()
        self._lock = threading.Lock()

    def before_hosted_call(
        self,
        messages: list[dict[str, Any]] | None = None,
        requested_max_tokens: int = 16384,
    ) -> int:
        """Reserve a call and return the maximum completion tokens allowed.

        The UTF-8 byte length of the serialized messages is used as a
        conservative pre-call upper bound for prompt tokens. Provider-reported
        usage replaces estimates in the persisted accounting after the call.
        """
        with self._lock:
            limit = self.limits.max_hosted_calls
            if limit is not None and self.usage.hosted_calls >= limit:
                raise BudgetExceeded(
                    f"Hosted-call budget exhausted ({self.usage.hosted_calls}/{limit})."
                )
            self._check_token_and_cost_limits()

            prompt_upper_bound = len(
                json.dumps(
                    messages or [],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            )
            prompt_limit = self.limits.max_prompt_tokens
            if (
                prompt_limit is not None
                and self.usage.prompt_tokens + prompt_upper_bound > prompt_limit
            ):
                raise BudgetExceeded(
                    "Prompt-token budget would be exceeded before the hosted call "
                    f"({self.usage.prompt_tokens}+≤{prompt_upper_bound}/{prompt_limit})."
                )

            allowed_tokens = max(0, int(requested_max_tokens))
            completion_limit = self.limits.max_completion_tokens
            if completion_limit is not None:
                allowed_tokens = min(
                    allowed_tokens,
                    completion_limit - self.usage.completion_tokens,
                )

            cost_limit = self.limits.max_cost_usd
            if cost_limit is not None:
                projected_input_cost = (
                    self.usage.estimated_cost_usd
                    + prompt_upper_bound * float(self.limits.input_price_per_million) / 1_000_000
                )
                remaining_cost = cost_limit - projected_input_cost
                if remaining_cost <= 0:
                    raise BudgetExceeded(
                        "Currency budget cannot cover the next prompt's conservative "
                        f"upper bound (${projected_input_cost:.6f}/${cost_limit:.6f})."
                    )
                output_price = float(self.limits.output_price_per_million)
                if output_price > 0:
                    affordable_output = math.floor(remaining_cost * 1_000_000 / output_price)
                    allowed_tokens = min(allowed_tokens, affordable_output)

            if allowed_tokens <= 0:
                raise BudgetExceeded("Completion-token or currency budget is exhausted.")
            self.usage.hosted_calls += 1
            return allowed_tokens

    def reset(self) -> None:
        """Start a fresh accounting window for the next Nexus run."""
        with self._lock:
            self.usage = BudgetUsage()

    def record_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """Add provider-reported usage and enforce the hard post-call ceiling."""
        with self._lock:
            self.usage.prompt_tokens += max(0, int(prompt_tokens or 0))
            self.usage.completion_tokens += max(0, int(completion_tokens or 0))
            self.usage.estimated_cost_usd = self._estimate_cost()
            self._check_token_and_cost_limits()

    def snapshot(self) -> dict[str, Any]:
        return {
            "limits": asdict(self.limits),
            "usage": asdict(self.usage),
        }

    def _estimate_cost(self) -> float:
        if (
            self.limits.input_price_per_million is None
            or self.limits.output_price_per_million is None
        ):
            return 0.0
        return (
            self.usage.prompt_tokens * self.limits.input_price_per_million
            + self.usage.completion_tokens * self.limits.output_price_per_million
        ) / 1_000_000

    def _check_token_and_cost_limits(self) -> None:
        checks = (
            (
                "prompt-token",
                self.usage.prompt_tokens,
                self.limits.max_prompt_tokens,
            ),
            (
                "completion-token",
                self.usage.completion_tokens,
                self.limits.max_completion_tokens,
            ),
        )
        for label, used, limit in checks:
            if limit is not None and used > limit:
                raise BudgetExceeded(f"{label} budget exceeded ({used}/{limit}).")
        cost_limit = self.limits.max_cost_usd
        if cost_limit is not None and self.usage.estimated_cost_usd > cost_limit:
            raise BudgetExceeded(
                "Currency budget exceeded "
                f"(${self.usage.estimated_cost_usd:.6f}/${cost_limit:.6f})."
            )


class BudgetedClient:
    """Transparent proxy that enforces call limits across all Nexus nodes."""

    def __init__(self, client: Any, controller: BudgetController):
        self._wrapped_client = client
        self._budget_controller = controller

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped_client, name)

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        args, kwargs = self._apply_budget(args, kwargs)
        response = self._wrapped_client.chat(*args, **kwargs)
        if not kwargs.get("stream", True):
            self._record_response_usage(response)
        return response

    def chat_sync(self, *args: Any, **kwargs: Any) -> Any:
        args, kwargs = self._apply_budget(args, kwargs)
        response = self._wrapped_client.chat_sync(*args, **kwargs)
        self._record_response_usage(response)
        return response

    def _record_response_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self._budget_controller.record_usage(
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def _apply_budget(
        self,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        mutable_args = list(args)
        mutable_kwargs = dict(kwargs)
        messages = mutable_kwargs.get("messages")
        if messages is None and len(mutable_args) > 1:
            messages = mutable_args[1]
        requested = mutable_kwargs.get("max_tokens")
        if requested is None and len(mutable_args) > 4:
            requested = mutable_args[4]
        allowed = self._budget_controller.before_hosted_call(
            messages if isinstance(messages, list) else [],
            int(requested if requested is not None else 16384),
        )
        if len(mutable_args) > 4:
            mutable_args[4] = allowed
        else:
            mutable_kwargs["max_tokens"] = allowed
        return tuple(mutable_args), mutable_kwargs
