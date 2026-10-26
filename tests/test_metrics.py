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
