"""Data models for flake-detector.

Defines Pydantic v2 schemas for tasks, suites, grader specifications,
and execution results matching PRD Section 7.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

GraderType = Literal["exact", "contains", "regex", "numeric"]
FailureReason = Literal[
    "wrong_answer",
    "format_error",
    "no_answer",
    "tool_error",
    "timeout",
    "exception",
    "max_steps",
]


class GraderSpec(BaseModel):
    """Specification for deterministic grading of an agent's answer."""

    type: GraderType
    expected: str | float | int | None = None
    case_sensitive: bool = True
    strip: bool = True
    pattern: str | None = None
    abs_tol: float = 0.0
    rel_tol: float = 0.0

    @model_validator(mode="after")
    def validate_spec(self) -> GraderSpec:
        """Ensure required fields are present based on grader type."""
        if self.type == "regex" and not self.pattern and self.expected is None:
            raise ValueError("Regex grader requires 'pattern' or 'expected' regex string")
        if self.type == "numeric" and self.expected is None:
            raise ValueError("Numeric grader requires 'expected' number")
        if self.type in ("exact", "contains") and self.expected is None:
            raise ValueError(f"{self.type} grader requires 'expected' string")
        return self


class SimConfig(BaseModel):
    """Configuration specific to the simulated agent."""

    p_success: float = Field(default=0.8, ge=0.0, le=1.0)


class Task(BaseModel):
    """A single evaluation task in a suite."""

    id: str
    category: str = "general"
    prompt: str
    grader: GraderSpec
    sim: SimConfig = Field(default_factory=SimConfig)


class Suite(BaseModel):
    """A collection of tasks to evaluate."""

    name: str
    description: str = ""
    tasks: list[Task]

    @model_validator(mode="after")
    def validate_unique_task_ids(self) -> Suite:
        """Verify that all task IDs within the suite are unique."""
        seen: set[str] = set()
        duplicates: list[str] = []
        for task in self.tasks:
            if task.id in seen:
                duplicates.append(task.id)
            seen.add(task.id)
        if duplicates:
            raise ValueError(f"Duplicate task IDs found: {', '.join(duplicates)}")
        return self


class AgentOutput(BaseModel):
    """Output produced by an agent for a single run."""

    answer: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    steps: int = 1


class RunRecord(BaseModel):
    """Outcome and execution metadata for a single run of a task."""

    index: int
    success: bool
    failure_reason: str | None = None
    answer: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    steps: int = 1


class TaskResult(BaseModel):
    """Aggregated runs for a specific task."""

    id: str
    category: str
    runs: list[RunRecord] = Field(default_factory=list)


class AgentMetadata(BaseModel):
    """Metadata describing the agent evaluated."""

    name: str
    model: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class SuiteMetadata(BaseModel):
    """Metadata describing the suite evaluated."""

    name: str
    sha256_12: str


class RunParams(BaseModel):
    """Parameters used during the test execution."""

    runs: int
    k: int
    seed: int


class RunResults(BaseModel):
    """Top-level results container conforming to PRD Section 7."""

    schema_version: str = "1.0.0"
    run_id: str
    created_at: str
    agent: AgentMetadata
    suite: SuiteMetadata
    params: RunParams
    tasks: list[TaskResult] = Field(default_factory=list)
