"""Tests for flake_detector.metrics matching PRD Section 5 specifications."""

import pytest

from flake_detector.metrics import (
    flakiness,
    pass_at_k,
    pass_curves,
    pass_hat_k,
    suite_summary,
    task_status,
    wilson_interval,
)
from flake_detector.models import RunRecord, TaskResult


def test_wilson_interval_test_vectors() -> None:
    """Verify Wilson interval against PRD Section 5 test vectors within 1e-3 tolerance."""
    # Vector 1: n=10, c=7 -> [0.397, 0.892]
    low1, high1 = wilson_interval(7, 10)
    assert pytest.approx(0.397, abs=1e-3) == low1
    assert pytest.approx(0.892, abs=1e-3) == high1

    # Vector 2: n=5, c=5 -> [0.5655, 1.0]
    low2, high2 = wilson_interval(5, 5)
    assert pytest.approx(0.5655, abs=1e-3) == low2
    assert pytest.approx(1.0, abs=1e-3) == high2


def test_pass_at_k_and_hat_k_test_vectors() -> None:
    """Verify pass@k and pass^k against PRD Section 5 test vectors within 1e-3 tolerance."""
    # n=10, c=3, k=1 -> pass@1 = 0.3, pass^1 = 0.3
    assert pytest.approx(0.3, abs=1e-3) == pass_at_k(10, 3, 1)
    assert pytest.approx(0.3, abs=1e-3) == pass_hat_k(10, 3, 1)

    # n=10, c=3, k=2 -> pass@2 = 0.5333, pass^2 = 0.0667
    assert pytest.approx(0.5333, abs=1e-3) == pass_at_k(10, 3, 2)
    assert pytest.approx(0.0667, abs=1e-3) == pass_hat_k(10, 3, 2)

    # n=10, c=3, k=5 -> pass@5 = 0.9167, pass^5 = 0.0
    assert pytest.approx(0.9167, abs=1e-3) == pass_at_k(10, 3, 5)
    assert pytest.approx(0.0, abs=1e-3) == pass_hat_k(10, 3, 5)

    # n=10, c=10, k=5 -> pass@5 = 1.0, pass^5 = 1.0
    assert pytest.approx(1.0, abs=1e-3) == pass_at_k(10, 10, 5)
    assert pytest.approx(1.0, abs=1e-3) == pass_hat_k(10, 10, 5)

    # n=10, c=0, k=5 -> pass@5 = 0.0, pass^5 = 0.0
    assert pytest.approx(0.0, abs=1e-3) == pass_at_k(10, 0, 5)
    assert pytest.approx(0.0, abs=1e-3) == pass_hat_k(10, 0, 5)


def test_metrics_property_checks() -> None:
    """Check mathematical invariants: 0 <= pass^k <= pass@k <= 1 and p in Wilson interval."""
    test_cases = [
        (n, c, k)
        for n in [1, 2, 5, 10, 15]
        for c in range(n + 1)
        for k in range(1, n + 1)
    ]

    for n, c, k in test_cases:
        p_at = pass_at_k(n, c, k)
        p_hat = pass_hat_k(n, c, k)

        assert 0.0 <= p_hat <= 1.0, f"pass^k out of bounds for n={n}, c={c}, k={k}"
        assert 0.0 <= p_at <= 1.0, f"pass@k out of bounds for n={n}, c={c}, k={k}"
        assert p_hat <= p_at + 1e-9, f"pass^k > pass@k for n={n}, c={c}, k={k}"

        p = c / n
        low, high = wilson_interval(c, n)
        assert 0.0 <= low <= high <= 1.0
        assert low <= p + 1e-9 and p - 1e-9 <= high, f"p={p} not in [{low}, {high}]"


def test_flakiness_and_task_status() -> None:
    """Verify flakiness score and status classifications."""
    assert flakiness(0, 10) == 0.0
    assert flakiness(10, 10) == 0.0
    assert flakiness(5, 10) == 1.0
    assert flakiness(2, 10) == pytest.approx(4 * 0.2 * 0.8)

    assert task_status(10, 10) == "consistent"
    assert task_status(0, 10) == "failing"
    assert task_status(7, 10) == "flaky"
    assert task_status(0, 0) == "failing"


def test_suite_summary_and_pass_curves() -> None:
    """Verify suite_summary and pass_curves aggregation."""
    task1 = TaskResult(
        id="t1",
        category="c1",
        runs=[
            RunRecord(index=0, success=True, latency_ms=100.0, tokens_in=10, tokens_out=5),
            RunRecord(index=1, success=True, latency_ms=120.0, tokens_in=10, tokens_out=5),
        ],
    )
    task2 = TaskResult(
        id="t2",
        category="c2",
        runs=[
            RunRecord(index=0, success=False, failure_reason="wrong_answer", latency_ms=80.0),
            RunRecord(index=1, success=False, failure_reason="wrong_answer", latency_ms=90.0),
        ],
    )
    task3 = TaskResult(
        id="t3",
        category="c1",
        runs=[
            RunRecord(index=0, success=True, latency_ms=110.0),
            RunRecord(index=1, success=False, failure_reason="format_error", latency_ms=95.0),
        ],
    )

    summary = suite_summary([task1, task2, task3], k=2)
    assert summary["total_tasks"] == 3
    assert summary["total_runs"] == 6
    assert summary["consistent_count"] == 1
    assert summary["failing_count"] == 1
    assert summary["flaky_count"] == 1
    assert pytest.approx(100.0 / 3.0) == summary["pct_consistent"]
    assert pytest.approx(0.5) == summary["mean_pass_1"]

    curves = pass_curves([task1, task2, task3], max_k=2)
    assert curves["k"] == [1.0, 2.0]
    assert len(curves["pass_at_k"]) == 2
    assert len(curves["pass_hat_k"]) == 2


def test_metrics_edge_cases_and_validations() -> None:
    """Verify bounds checks, invalid inputs, and empty collection handling."""
    # Wilson interval edge cases
    assert wilson_interval(0, 0) == (0.0, 0.0)
    with pytest.raises(ValueError, match="Successes c"):
        wilson_interval(5, 4)
    with pytest.raises(ValueError, match="Successes c"):
        wilson_interval(-1, 5)

    # pass@k edge cases
    with pytest.raises(ValueError, match="k must be >= 1"):
        pass_at_k(5, 2, 0)
    with pytest.raises(ValueError, match="must be >= k"):
        pass_at_k(4, 2, 5)
    with pytest.raises(ValueError, match="Successes c"):
        pass_at_k(5, 6, 2)
    assert pass_at_k(5, 0, 2) == 0.0
    assert pass_at_k(5, 5, 2) == 1.0

    # pass^k edge cases
    with pytest.raises(ValueError, match="k must be >= 1"):
        pass_hat_k(5, 2, 0)
    with pytest.raises(ValueError, match="must be >= k"):
        pass_hat_k(4, 2, 5)
    with pytest.raises(ValueError, match="Successes c"):
        pass_hat_k(5, 6, 2)
    assert pass_hat_k(5, 1, 2) == 0.0

    # flakiness edge cases
    assert flakiness(0, 0) == 0.0
    with pytest.raises(ValueError, match="Successes c"):
        flakiness(5, 4)

    # empty suite summary and pass curves
    empty_summary = suite_summary([], k=2)
    assert empty_summary["total_tasks"] == 0
    assert empty_summary["total_runs"] == 0

    empty_curves = pass_curves([], max_k=3)
    assert empty_curves["pass_at_k"] == [0.0, 0.0, 0.0]

