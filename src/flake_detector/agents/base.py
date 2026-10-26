"""Agent protocol definition for flake-detector.

Conforms to PRD Section 6 (FR-3) and Milestone 02.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from flake_detector.models import AgentOutput, Task


@runtime_checkable
class Agent(Protocol):
    """Protocol defining the interface for an AI agent runner."""

    name: str
    model: str | None
    config: dict[str, Any]

    def run(self, task: Task, seed: int) -> AgentOutput:
        """Execute a single run of a task with a deterministically provided seed.

        Args:
            task: The evaluation task specification.
            seed: Deterministically derived seed for this specific run.

        Returns:
            An AgentOutput containing the answer, optional error, and telemetry.
        """
        ...
