"""Tests for flake_detector.compare."""

from flake_detector.agents.simulated import SimulatedAgent
from flake_detector.compare import compare_runs
from flake_detector.runner import run_suite
from flake_detector.suite import load_suite


def test_compare_identical_runs() -> None:
    """Comparing a run to itself or identical runs yields no regression and 0 difference."""
    suite, sha = load_suite("suites/demo_sim.yaml")
    agent = SimulatedAgent()

    run_a = run_suite(suite, agent, runs=10, seed=42)
    run_b = run_suite(suite, agent, runs=10, seed=42)

    comp = compare_runs(run_a, run_b)
    assert comp.is_regression is False
    assert comp.mean_diff == 0.0
    assert len(comp.regressed_tasks) == 0
    assert len(comp.improved_tasks) == 0
    assert len(comp.unchanged_tasks) == len(suite.tasks)
    assert "NO REGRESSION DETECTED" in comp.markdown_report


def test_compare_degraded_run_triggers_regression() -> None:
    """Comparing baseline to degraded suite detects a statistically significant regression."""
    suite_base, sha_b = load_suite("suites/demo_sim.yaml")
    suite_deg, sha_d = load_suite("suites/demo_sim_degraded.yaml")
    agent = SimulatedAgent()

    run_base = run_suite(suite_base, agent, runs=20, seed=42)
    run_deg = run_suite(suite_deg, agent, runs=20, seed=42)

    comp = compare_runs(run_base, run_deg)
    assert comp.is_regression is True
    assert comp.mean_diff < 0.0
    assert comp.bootstrap_ci[1] < 0.0  # Upper bound of difference is negative
    assert len(comp.regressed_tasks) > 0
    assert "REGRESSION DETECTED" in comp.markdown_report


def test_compare_unshared_tasks_and_validation() -> None:
    """Verify handling of unshared tasks and error when no common tasks exist."""
    import pytest

    from flake_detector.models import GraderSpec, Suite, Task

    suite_a = Suite(
        name="suite-a",
        tasks=[
            Task(id="shared-01", prompt="p1", grader=GraderSpec(type="exact", expected="x")),
            Task(id="only-a", prompt="p2", grader=GraderSpec(type="exact", expected="y")),
        ],
    )
    suite_b = Suite(
        name="suite-b",
        tasks=[
            Task(id="shared-01", prompt="p1", grader=GraderSpec(type="exact", expected="x")),
            Task(id="only-b", prompt="p3", grader=GraderSpec(type="exact", expected="z")),
        ],
    )
    suite_c = Suite(
        name="suite-c",
        tasks=[
            Task(id="disjoint", prompt="p4", grader=GraderSpec(type="exact", expected="w")),
        ],
    )

    agent = SimulatedAgent()
    run_a = run_suite(suite_a, agent, runs=5, seed=42)
    run_b = run_suite(suite_b, agent, runs=5, seed=42)
    run_c = run_suite(suite_c, agent, runs=5, seed=42)

    comp = compare_runs(run_a, run_b)
    assert comp.tasks_only_in_baseline == ["only-a"]
    assert comp.tasks_only_in_candidate == ["only-b"]
    assert "Unshared Tasks" in comp.markdown_report
    assert "Only in Baseline: `only-a`" in comp.markdown_report
    assert "Only in Candidate: `only-b`" in comp.markdown_report

    with pytest.raises(ValueError, match="no common task IDs found"):
        compare_runs(run_a, run_c)

