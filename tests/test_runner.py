"""Tests for the execution runner and atomic storage in flake-detector."""

from pathlib import Path

from flake_detector.agents.simulated import SimulatedAgent
from flake_detector.models import AgentOutput, GraderSpec, SimConfig, Suite, Task
from flake_detector.runner import run_suite
from flake_detector.storage import load_results, save_results_atomic


def _create_test_suite() -> Suite:
    """Create a minimal 3-task suite for testing."""
    return Suite(
        name="test-runner-suite",
        tasks=[
            Task(
                id="t1",
                category="math",
                prompt="17 * 23",
                grader=GraderSpec(type="numeric", expected=391),
                sim=SimConfig(p_success=0.8),
            ),
            Task(
                id="t2",
                category="formatting",
                prompt="Return BLUE",
                grader=GraderSpec(type="exact", expected="BLUE"),
                sim=SimConfig(p_success=0.5),
            ),
            Task(
                id="t3",
                category="math",
                prompt="1000 / 8",
                grader=GraderSpec(type="numeric", expected=125),
                sim=SimConfig(p_success=0.2),
            ),
        ],
    )


def test_runner_determinism() -> None:
    """Identical seeds give identical suite results; different seeds differ."""
    suite = _create_test_suite()
    agent = SimulatedAgent()

    res1 = run_suite(suite, agent, runs=10, seed=42, workers=2)
    res2 = run_suite(suite, agent, runs=10, seed=42, workers=2)
    res_diff = run_suite(suite, agent, runs=10, seed=999, workers=2)

    # Identical runs have matching task runs
    for t1, t2 in zip(res1.tasks, res2.tasks, strict=True):
        assert [r.model_dump() for r in t1.runs] == [r.model_dump() for r in t2.runs]

    # Different seed produces differences
    runs_1 = [r.success for t in res1.tasks for r in t.runs]
    runs_diff = [r.success for t in res_diff.tasks for r in t.runs]
    assert runs_1 != runs_diff


def test_runner_order_independence_workers() -> None:
    """workers=1 and workers=8 must give identical results."""
    suite = _create_test_suite()
    agent = SimulatedAgent()

    res_single = run_suite(suite, agent, runs=15, seed=777, workers=1)
    res_multi = run_suite(suite, agent, runs=15, seed=777, workers=8)

    for t_s, t_m in zip(res_single.tasks, res_multi.tasks, strict=True):
        assert [r.model_dump() for r in t_s.runs] == [r.model_dump() for r in t_m.runs]


def test_runner_crash_safety() -> None:
    """An agent that raises on every call yields all-failed runs and a completed suite."""
    suite = _create_test_suite()

    class ExplodingAgent:
        name = "exploding"
        model = None
        config: dict = {}

        def run(self, task: Task, seed: int) -> AgentOutput:
            raise RuntimeError("Intentional test crash")

    agent = ExplodingAgent()
    results = run_suite(suite, agent, runs=5, seed=42, workers=2)

    assert len(results.tasks) == 3
    for task in results.tasks:
        assert len(task.runs) == 5
        for run in task.runs:
            assert run.success is False
            assert run.failure_reason == "exception"
            assert "RuntimeError: Intentional test crash" in (run.error or "")


def test_runner_resume_functionality() -> None:
    """Resuming from 5 existing runs to 10 runs only computes missing runs and merges."""
    suite = _create_test_suite()
    agent = SimulatedAgent()

    res_initial = run_suite(suite, agent, runs=5, seed=101, workers=1)
    assert all(len(t.runs) == 5 for t in res_initial.tasks)

    # Count how many calls are made when resuming
    call_count = 0

    class CountingAgent:
        name = "sim"
        model = None
        config: dict = {}

        def run(self, task: Task, seed: int) -> AgentOutput:
            nonlocal call_count
            call_count += 1
            return agent.run(task, seed)

    counting_agent = CountingAgent()
    res_resumed = run_suite(
        suite,
        counting_agent,
        runs=10,
        seed=101,
        workers=2,
        existing=res_initial,
    )

    # 3 tasks * 5 new runs = 15 calls
    assert call_count == 15
    assert all(len(t.runs) == 10 for t in res_resumed.tasks)

    # First 5 runs must match initial exactly
    for t_init, t_res in zip(res_initial.tasks, res_resumed.tasks, strict=True):
        assert [r.model_dump() for r in t_init.runs] == [r.model_dump() for r in t_res.runs[:5]]


def test_storage_round_trip(tmp_path: Path) -> None:
    """Atomic write followed by load equals original results."""
    suite = _create_test_suite()
    agent = SimulatedAgent()
    results = run_suite(suite, agent, runs=4, seed=55)

    target_file = tmp_path / "results.json"
    saved_path = save_results_atomic(results, target_file)
    assert saved_path == target_file
    assert target_file.exists()

    loaded = load_results(target_file)
    assert loaded.model_dump() == results.model_dump()


def test_runner_validations_and_error_mappings() -> None:
    """Verify runner validates parameters and classifies diverse agent error strings."""
    import pytest
    suite = _create_test_suite()
    agent = SimulatedAgent()

    with pytest.raises(ValueError, match="runs must be >= 1"):
        run_suite(suite, agent, runs=0, seed=42)

    with pytest.raises(ValueError, match="must satisfy 1 <= k <= runs"):
        run_suite(suite, agent, runs=5, k=10, seed=42)

    # Test error mapping in _execute_single_run
    class TimeoutAgent:
        name = "timeout"
        model = None
        config: dict = {}

        def run(self, task: Task, seed: int) -> AgentOutput:
            return AgentOutput(answer=None, error="Execution timeout after 5000ms")

    res_timeout = run_suite(suite, TimeoutAgent(), runs=1, seed=42)
    assert res_timeout.tasks[0].runs[0].failure_reason == "timeout"

    class MaxStepsAgent:
        name = "max_steps"
        model = None
        config: dict = {}

        def run(self, task: Task, seed: int) -> AgentOutput:
            return AgentOutput(answer=None, error="Exceeded max_steps limit")

    res_steps = run_suite(suite, MaxStepsAgent(), runs=1, seed=42)
    assert res_steps.tasks[0].runs[0].failure_reason == "max_steps"

