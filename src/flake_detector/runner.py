"""Execution engine and deterministic runner for flake-detector.

Concurrently executes agent evaluation suites across tasks and runs,
isolating exceptions, supporting resume, and ensuring determinism across worker counts.
Conforms to PRD Section 6 (FR-4, FR-6) and Milestone 02.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from flake_detector.agents.simulated import derive_run_seed
from flake_detector.grading import grade
from flake_detector.models import (
    AgentMetadata,
    RunParams,
    RunRecord,
    RunResults,
    SuiteMetadata,
    TaskResult,
)
from flake_detector.storage import generate_run_id

if TYPE_CHECKING:
    from flake_detector.agents.base import Agent
    from flake_detector.models import Suite, Task


ProgressCallback = Callable[[int, int, str, RunRecord], None]


def _execute_single_run(task: Task, run_index: int, run_seed: int, agent: Agent) -> RunRecord:
    """Execute a single run of a task, catching all exceptions safely."""
    try:
        output = agent.run(task, run_seed)

        # Handle agent-reported errors (timeouts, tool errors, etc.)
        if output.error:
            reason = "exception"
            err_lower = output.error.lower()
            if "timeout" in err_lower:
                reason = "timeout"
            elif "tool" in err_lower:
                reason = "tool_error"
            elif "max_step" in err_lower or "max step" in err_lower:
                reason = "max_steps"

            return RunRecord(
                index=run_index,
                success=False,
                failure_reason=reason,
                answer=output.answer,
                error=output.error,
                latency_ms=output.latency_ms,
                tokens_in=output.tokens_in,
                tokens_out=output.tokens_out,
                steps=output.steps,
            )

        # Grade the answer deterministically
        success, grader_reason = grade(output.answer, task.grader)
        return RunRecord(
            index=run_index,
            success=success,
            failure_reason=grader_reason if not success else None,
            answer=output.answer,
            error=None,
            latency_ms=output.latency_ms,
            tokens_in=output.tokens_in,
            tokens_out=output.tokens_out,
            steps=output.steps,
        )

    except Exception as exc:
        # A single run crash must NEVER terminate the suite
        return RunRecord(
            index=run_index,
            success=False,
            failure_reason="exception",
            answer=None,
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=0.0,
            tokens_in=0,
            tokens_out=0,
            steps=1,
        )


def run_suite(
    suite: Suite,
    agent: Agent,
    runs: int,
    seed: int,
    workers: int = 1,
    k: int = 1,
    suite_sha256: str = "0" * 12,
    existing: RunResults | None = None,
    on_progress: ProgressCallback | None = None,
) -> RunResults:
    """Run an evaluation suite across N runs per task.

    Args:
        suite: The loaded and validated Suite.
        agent: The Agent protocol instance to evaluate.
        runs: Total number of runs per task.
        seed: Base seed for deterministic run derivation.
        workers: Concurrency level (1 = sequential, >1 = ThreadPoolExecutor).
        k: Sample parameter k for pass@k and pass^k.
        suite_sha256: 12-char SHA-256 hash of the suite file.
        existing: Optional prior RunResults to resume from.
        on_progress: Optional callback invoked as runs complete.

    Returns:
        A RunResults object sorted deterministically.
    """
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    if k < 1 or k > runs:
        raise ValueError(f"k must satisfy 1 <= k <= runs, got k={k}, runs={runs}")

    # Build resume mapping: task_id -> {run_index: RunRecord}
    existing_records: dict[str, dict[int, RunRecord]] = {}
    if existing is not None:
        for t_res in existing.tasks:
            existing_records[t_res.id] = {r.index: r for r in t_res.runs if r.index < runs}

    # Prepare execution jobs: (task, run_index, run_seed)
    jobs: list[tuple[Task, int, int]] = []
    task_results_map: dict[str, list[RunRecord]] = {task.id: [] for task in suite.tasks}

    for task in suite.tasks:
        completed = existing_records.get(task.id, {})
        for run_idx in range(runs):
            if run_idx in completed:
                task_results_map[task.id].append(completed[run_idx])
            else:
                run_seed = derive_run_seed(seed, task.id, run_idx)
                jobs.append((task, run_idx, run_seed))

    total_jobs = len(jobs)
    completed_jobs = 0

    if workers <= 1 or total_jobs <= 1:
        # Sequential execution
        for task, run_idx, run_seed in jobs:
            record = _execute_single_run(task, run_idx, run_seed, agent)
            task_results_map[task.id].append(record)
            completed_jobs += 1
            if on_progress:
                on_progress(completed_jobs, total_jobs, task.id, record)
    else:
        # Concurrent execution with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_job = {
                executor.submit(
                    _execute_single_run, task, run_idx, run_seed, agent
                ): (task, run_idx)
                for task, run_idx, run_seed in jobs
            }
            for future in as_completed(future_to_job):
                task, _ = future_to_job[future]
                record = future.result()
                task_results_map[task.id].append(record)
                completed_jobs += 1
                if on_progress:
                    on_progress(completed_jobs, total_jobs, task.id, record)

    # Order invariance: Sort tasks in suite order and runs by index ascending
    ordered_tasks: list[TaskResult] = []
    for task in suite.tasks:
        runs_list = task_results_map[task.id]
        runs_list.sort(key=lambda r: r.index)
        ordered_tasks.append(
            TaskResult(
                id=task.id,
                category=task.category,
                runs=runs_list,
            )
        )

    run_id = (
        existing.run_id
        if existing is not None
        else generate_run_id(suite.name, getattr(agent, "name", "agent"))
    )

    return RunResults(
        schema_version="1.0.0",
        run_id=run_id,
        created_at=datetime.now(UTC).isoformat(),
        agent=AgentMetadata(
            name=getattr(agent, "name", "agent"),
            model=getattr(agent, "model", None),
            config=getattr(agent, "config", {}),
        ),
        suite=SuiteMetadata(
            name=suite.name,
            sha256_12=suite_sha256,
        ),
        params=RunParams(
            runs=runs,
            k=k,
            seed=seed,
        ),
        tasks=ordered_tasks,
    )
