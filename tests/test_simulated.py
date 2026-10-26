"""Tests for SimulatedAgent and seed derivation in flake_detector.agents.simulated."""

from flake_detector.agents.simulated import SimulatedAgent, derive_run_seed
from flake_detector.grading import grade
from flake_detector.models import GraderSpec, SimConfig, Task


def test_derive_run_seed_determinism() -> None:
    """derive_run_seed must produce the identical integer for identical inputs
    and differ otherwise.
    """
    s1 = derive_run_seed(42, "task-01", 0)
    s2 = derive_run_seed(42, "task-01", 0)
    assert s1 == s2
    assert isinstance(s1, int)

    # Different seed, task, or run_index must differ
    assert derive_run_seed(43, "task-01", 0) != s1
    assert derive_run_seed(42, "task-02", 0) != s1
    assert derive_run_seed(42, "task-01", 1) != s1


def test_simulated_agent_determinism() -> None:
    """Running SimulatedAgent twice with the identical seed must return identical outputs."""
    agent = SimulatedAgent()
    task = Task(
        id="math-01",
        category="math",
        prompt="17 * 23",
        grader=GraderSpec(type="numeric", expected=391),
        sim=SimConfig(p_success=0.5),
    )

    seed = derive_run_seed(1234, task.id, 0)
    out1 = agent.run(task, seed)
    out2 = agent.run(task, seed)

    assert out1.model_dump() == out2.model_dump()


def test_simulated_agent_statistical_sanity() -> None:
    """Over 2000 runs, a task with p_success=0.7 lands within 0.03 of 0.7."""
    agent = SimulatedAgent()
    task = Task(
        id="stat-01",
        category="math",
        prompt="Calculate something",
        grader=GraderSpec(type="numeric", expected=100),
        sim=SimConfig(p_success=0.7),
    )

    base_seed = 9999
    successes = 0
    total = 2000

    for i in range(total):
        seed = derive_run_seed(base_seed, task.id, i)
        out = agent.run(task, seed)
        ok, _ = grade(out.answer, task.grader)
        if ok:
            successes += 1

    rate = successes / total
    assert abs(rate - 0.7) <= 0.03, f"Observed success rate {rate} was not within 0.03 of 0.7"
