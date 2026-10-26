"""Deterministic simulated agent for flake-detector.

Simulates agent executions with per-task success probabilities, realistic
latency distributions, token usage, and plausible failure outputs without
making any network calls. Conforms to PRD Section 10.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

from flake_detector.models import AgentOutput, Task


def derive_run_seed(base_seed: int, task_id: str, run_index: int) -> int:
    """Derive a deterministic integer seed using a stable SHA-256 hash.

    Avoids Python's built-in salted hash() and ensures full cross-platform,
    cross-process determinism.
    """
    key = f"{base_seed}:{task_id}:{run_index}".encode()
    digest = hashlib.sha256(key).hexdigest()
    # Take first 16 hex characters (64 bits) for an integer seed
    return int(digest[:16], 16)


class SimulatedAgent:
    """Deterministic agent simulator using suite-configured probabilities."""

    name: str = "sim"
    model: str | None = None
    config: dict[str, Any]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def run(self, task: Task, seed: int) -> AgentOutput:
        """Run the simulated task deterministically with the provided seed."""
        # Initialize an isolated, private RNG
        rng = random.Random(seed)

        p_success = task.sim.p_success if task.sim is not None else 0.8
        roll = rng.random()
        success = roll < p_success

        # Simulated latency drawn from log-normal distribution (~120ms - 280ms)
        latency_ms = round(math.exp(rng.gauss(5.2, 0.35)), 2)
        tokens_in = rng.randint(20, 50)
        tokens_out = rng.randint(8, 30)

        if success:
            answer = self._generate_success_answer(task, rng)
            return AgentOutput(
                answer=answer,
                error=None,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                steps=1,
            )

        # On failure, choose a failure reason with realistic distribution
        failure_reasons = ["wrong_answer", "format_error", "no_answer", "tool_error", "timeout"]
        weights = [0.50, 0.20, 0.10, 0.10, 0.10]
        chosen_reason = rng.choices(failure_reasons, weights=weights, k=1)[0]

        if chosen_reason == "tool_error":
            return AgentOutput(
                answer=None,
                error="Tool execution error: safe evaluation rejected expression",
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                steps=2,
            )
        if chosen_reason == "timeout":
            return AgentOutput(
                answer=None,
                error="Execution timed out after 10000ms",
                latency_ms=10000.0,
                tokens_in=tokens_in,
                tokens_out=0,
                steps=1,
            )
        if chosen_reason == "no_answer":
            return AgentOutput(
                answer="",
                error=None,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=0,
                steps=1,
            )
        if chosen_reason == "format_error":
            return AgentOutput(
                answer="I was unable to determine a numeric value or valid format.",
                error=None,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                steps=1,
            )

        # wrong_answer
        wrong_answer = self._generate_wrong_answer(task, rng)
        return AgentOutput(
            answer=wrong_answer,
            error=None,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            steps=1,
        )

    def _generate_success_answer(self, task: Task, rng: random.Random) -> str:
        """Produce a valid answer conforming to the task grader."""
        grader = task.grader
        if grader.type == "numeric":
            val = grader.expected if grader.expected is not None else 0
            # Occasionally embed the answer in natural language to exercise regex extraction
            if rng.random() < 0.4:
                return f"The calculated result is {val}."
            return str(val)

        if grader.type == "exact":
            return str(grader.expected)

        if grader.type == "contains":
            return f"The output definitely includes {grader.expected}."

        if grader.type == "regex":
            if "status" in (grader.pattern or ""):
                return '{"status": "ok"}'
            if grader.expected is not None:
                return str(grader.expected)
            return "matched"

        return str(grader.expected)

    def _generate_wrong_answer(self, task: Task, rng: random.Random) -> str:
        """Produce an incorrect answer for the task grader."""
        grader = task.grader
        if grader.type == "numeric":
            try:
                base = float(grader.expected or 0)
                offset = rng.choice([-10.0, -1.0, 1.0, 5.0, 42.0])
                return str(base + offset)
            except (ValueError, TypeError):
                return "0.0"

        if grader.type == "exact":
            return f"incorrect_{grader.expected}"

        if grader.type == "contains":
            return "Completely unrelated content without the keyword."

        if grader.type == "regex":
            return '{"status": "error", "code": 500}'

        return "wrong"
