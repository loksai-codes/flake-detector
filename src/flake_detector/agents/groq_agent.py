"""Groq OpenAI-compatible agent adapter for flake-detector.

Supports multi-turn tool calling, rate limiting (--max-rpm), exponential backoff
on 429 and 5xx errors with Retry-After support, and secret sanitization.
Conforms to PRD Section 10 and Milestone 04.
"""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

from dotenv import load_dotenv

from flake_detector.agents.tools import TOOL_DEFINITIONS, execute_tool
from flake_detector.models import AgentOutput, Task


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 30.0,
    retry_after: float | None = None,
    jitter: bool = False,
    rng: random.Random | None = None,
) -> float:
    """Calculate the backoff delay for retry attempts.

    Pure function with no sleeping to enable comprehensive unit testing.

    Args:
        attempt: 1-indexed attempt number (1, 2, 3...).
        base_delay: Initial retry delay in seconds.
        factor: Exponential multiplier.
        max_delay: Maximum delay cap in seconds.
        retry_after: Optional Retry-After header value from HTTP 429 response.
        jitter: Whether to add random jitter.
        rng: Optional seeded Random instance for deterministic jitter in tests.

    Returns:
        Delay in seconds.
    """
    exponent = max(0, attempt - 1)
    delay = min(max_delay, base_delay * (factor ** exponent))

    if jitter:
        r = rng if rng is not None else random
        delay = delay + r.uniform(0.0, 0.5 * delay)

    if retry_after is not None and retry_after > delay:
        delay = retry_after

    return delay


class RateLimiter:
    """Thread-safe rate limiter implementing requests per minute throttling."""

    def __init__(self, max_rpm: int = 20) -> None:
        self.max_rpm = max(1, max_rpm)
        self.min_interval = 60.0 / self.max_rpm
        self._lock = threading.Lock()
        self._last_call: float = 0.0

    def acquire(self) -> None:
        """Block until the minimum request interval has elapsed."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            wait_time = self.min_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_call = time.monotonic()


class GroqAgent:
    """Tool-calling agent interacting with Groq via OpenAI SDK."""

    name: str = "groq"
    model: str
    config: dict[str, Any]

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_rpm: int = 20,
        temperature: float = 0.7,
        client: Any | None = None,
    ) -> None:
        # Load environment variables from .env
        load_dotenv()

        resolved_key = api_key or os.getenv("GROQ_API_KEY")
        if not resolved_key and client is None:
            raise ValueError(
                "GROQ_API_KEY is not set. Please copy .env.example to .env "
                "and set your Groq API key."
            )

        resolved_model = model or os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile"
        self.model = resolved_model
        self.temperature = temperature
        self.max_steps = 6
        self.rate_limiter = RateLimiter(max_rpm=max_rpm)

        # Config must NEVER contain the secret API key
        self.config = {
            "model": self.model,
            "temperature": self.temperature,
            "max_rpm": max_rpm,
            "max_steps": self.max_steps,
        }

        if client is not None:
            self.client = client
        else:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=resolved_key,
                base_url="https://api.groq.com/openai/v1",
            )

    def run(self, task: Task, seed: int) -> AgentOutput:
        """Run the tool-calling agent loop up to 6 steps."""
        start_time = time.perf_counter()
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": task.prompt}
        ]

        tokens_in = 0
        tokens_out = 0
        steps = 0

        while steps < self.max_steps:
            self.rate_limiter.acquire()

            response = self._call_with_retry(messages, seed)
            if isinstance(response, AgentOutput):
                # Error encountered during API call
                response.latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                response.tokens_in = tokens_in
                response.tokens_out = tokens_out
                response.steps = max(1, steps)
                return response

            if hasattr(response, "usage") and response.usage:
                tokens_in += getattr(response.usage, "prompt_tokens", 0)
                tokens_out += getattr(response.usage, "completion_tokens", 0)

            steps += 1
            choice = response.choices[0]
            message = choice.message

            # Check if model requested tool execution
            if hasattr(message, "tool_calls") and message.tool_calls:
                # Append assistant tool call message
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in message.tool_calls
                    ],
                })

                # Execute requested tools and append tool responses
                for tc in message.tool_calls:
                    fn_name = tc.function.name
                    fn_args = tc.function.arguments
                    tool_output = execute_tool(fn_name, fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_output,
                    })
                continue

            # Model produced a final textual answer
            elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return AgentOutput(
                answer=message.content,
                error=None,
                latency_ms=elapsed_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                steps=steps,
            )

        # Loop completed without final answer -> step cap exceeded
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return AgentOutput(
            answer=None,
            error="Max steps exceeded (limit 6)",
            latency_ms=elapsed_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            steps=steps,
        )

    def _call_with_retry(
        self,
        messages: list[dict[str, Any]],
        seed: int,
    ) -> Any | AgentOutput:
        """Call Groq API with exponential backoff on 429 and 5xx errors."""
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    temperature=self.temperature,
                    seed=seed,
                )
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code is None and hasattr(exc, "response"):
                    status_code = getattr(exc.response, "status_code", None)

                # Retry on HTTP 429 (Rate Limit) and 5xx (Server Error)
                is_retriable = status_code == 429 or (
                    status_code is not None and 500 <= status_code < 600
                )

                if is_retriable and attempt < max_attempts:
                    retry_after = None
                    if hasattr(exc, "response") and hasattr(exc.response, "headers"):
                        hdr_val = exc.response.headers.get("Retry-After")
                        if hdr_val is not None:
                            try:
                                retry_after = float(hdr_val)
                            except (ValueError, TypeError):
                                pass

                    delay = calculate_backoff_delay(
                        attempt=attempt,
                        retry_after=retry_after,
                        jitter=True,
                    )
                    time.sleep(delay)
                    continue

                # Non-retriable error or attempts exhausted
                return AgentOutput(
                    answer=None,
                    error=f"Groq API error ({type(exc).__name__}): {exc}",
                )

        return AgentOutput(
            answer=None,
            error="Groq API error: Max retry attempts (6) exceeded",
        )
