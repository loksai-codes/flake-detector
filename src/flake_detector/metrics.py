"""Pure statistical and consistency metrics for flake-detector.

Implements Wilson 95% confidence intervals, pass@k, pass^k,
flakiness score, task status classifications, and suite summaries
according to PRD Section 5.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flake_detector.models import TaskResult


def wilson_interval(c: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a proportion.

    Given c successes in n trials, computes:
    center = (p + z^2 / (2n)) / (1 + z^2 / n)
    half = z * sqrt(p(1-p)/n + z^2 / (4n^2)) / (1 + z^2 / n)
    Interval is clipped to [0, 1].

    Args:
        c: Number of successful runs.
        n: Total number of runs.
        z: Z-score for confidence level (default 1.96 for 95% confidence).

    Returns:
        A tuple of (lower_bound, upper_bound) clipped to [0, 1].
    """
    if n <= 0:
        return 0.0, 0.0
    if c < 0 or c > n:
        raise ValueError(f"Successes c={c} must be between 0 and n={n}")

    p = c / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    variance_term = (p * (1.0 - p)) / n + z2 / (4.0 * n * n)
    half = (z * math.sqrt(variance_term)) / denom

    lower = max(0.0, center - half)
    upper = min(1.0, center + half)
    return lower, upper


def pass_at_k(n: int, c: int, k: int) -> float:
    """Calculate pass@k: probability that at least one of k sampled runs succeeds.

    Formula: 1 - C(n-c, k) / C(n, k).
    Equals 1.0 if n - c < k.
    Equals 0.0 if c == 0.

    Args:
        n: Total runs for the task.
        c: Successful runs for the task.
        k: Sample size to evaluate.

    Returns:
        Probability in [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError(f"k must be >= 1, got {k}")
    if n < k:
        raise ValueError(f"n ({n}) must be >= k ({k})")
    if c < 0 or c > n:
        raise ValueError(f"Successes c={c} must be between 0 and n={n}")

    if c == 0:
        return 0.0
    if n - c < k:
        return 1.0

    comb_n_k = math.comb(n, k)
    if comb_n_k == 0:
        return 0.0
    comb_fail_k = math.comb(n - c, k)
    return 1.0 - (comb_fail_k / comb_n_k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Calculate pass^k: probability that all k sampled runs succeed.

    Formula: C(c, k) / C(n, k).
    Equals 0.0 if c < k.

    Args:
        n: Total runs for the task.
        c: Successful runs for the task.
        k: Sample size to evaluate.

    Returns:
        Probability in [0.0, 1.0].
    """
    if k <= 0:
        raise ValueError(f"k must be >= 1, got {k}")
    if n < k:
        raise ValueError(f"n ({n}) must be >= k ({k})")
    if c < 0 or c > n:
        raise ValueError(f"Successes c={c} must be between 0 and n={n}")

    if c < k:
        return 0.0

    comb_n_k = math.comb(n, k)
    if comb_n_k == 0:
        return 0.0
    comb_c_k = math.comb(c, k)
    return comb_c_k / comb_n_k


def flakiness(c: int, n: int) -> float:
    """Calculate the flakiness score for a task: 4 * p * (1 - p).

    Returns 0.0 for always-pass or always-fail, and 1.0 at 50% success rate.
    """
    if n <= 0:
        return 0.0
    if c < 0 or c > n:
        raise ValueError(f"Successes c={c} must be between 0 and n={n}")
    p = c / n
    return 4.0 * p * (1.0 - p)


def task_status(c: int, n: int) -> str:
    """Classify task consistency status.

    Returns 'consistent' if c == n, 'failing' if c == 0, else 'flaky'.
    """
    if n <= 0:
        return "failing"
    if c == n:
        return "consistent"
    if c == 0:
        return "failing"
    return "flaky"


def pass_curves(task_results: list[TaskResult], max_k: int) -> dict[str, list[float]]:
    """Compute mean pass@k and pass^k curves across all tasks for k = 1..max_k.

    Returns:
        A dictionary with keys 'k', 'pass_at_k', and 'pass_hat_k'.
    """
    k_values = list(range(1, max_k + 1))
    mean_pass_at_k: list[float] = []
    mean_pass_hat_k: list[float] = []

    if not task_results:
        return {
            "k": [float(k) for k in k_values],
            "pass_at_k": [0.0] * len(k_values),
            "pass_hat_k": [0.0] * len(k_values),
        }

    for k in k_values:
        pass_at_k_sum = 0.0
        pass_hat_k_sum = 0.0
        valid_tasks = 0

        for task in task_results:
            n = len(task.runs)
            c = sum(1 for r in task.runs if r.success)
            if n >= k:
                pass_at_k_sum += pass_at_k(n, c, k)
                pass_hat_k_sum += pass_hat_k(n, c, k)
                valid_tasks += 1

        if valid_tasks > 0:
            mean_pass_at_k.append(pass_at_k_sum / valid_tasks)
            mean_pass_hat_k.append(pass_hat_k_sum / valid_tasks)
        else:
            mean_pass_at_k.append(0.0)
            mean_pass_hat_k.append(0.0)

    return {
        "k": [float(k) for k in k_values],
        "pass_at_k": mean_pass_at_k,
        "pass_hat_k": mean_pass_hat_k,
    }


def suite_summary(task_results: list[TaskResult], k: int) -> dict[str, Any]:
    """Calculate suite-level metrics and distribution over tasks.

    Returns a summary containing:
    - total_tasks, total_runs
    - mean_pass_1 (mean success rate)
    - mean_pass_at_k
    - mean_pass_hat_k
    - counts & percentages for consistent, flaky, and failing tasks
    - mean_latency_ms, total_tokens_in, total_tokens_out, total_tokens
    """
    total_tasks = len(task_results)
    if total_tasks == 0:
        return {
            "total_tasks": 0,
            "total_runs": 0,
            "mean_pass_1": 0.0,
            "mean_pass_at_k": 0.0,
            "mean_pass_hat_k": 0.0,
            "consistent_count": 0,
            "flaky_count": 0,
            "failing_count": 0,
            "pct_consistent": 0.0,
            "pct_flaky": 0.0,
            "pct_failing": 0.0,
            "mean_latency_ms": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_tokens": 0,
        }

    total_runs = 0
    pass_1_sum = 0.0
    pass_k_sum = 0.0
    pass_hat_k_sum = 0.0
    valid_k_tasks = 0

    consistent_count = 0
    flaky_count = 0
    failing_count = 0

    total_latency_ms = 0.0
    total_tokens_in = 0
    total_tokens_out = 0

    for task in task_results:
        n = len(task.runs)
        c = sum(1 for r in task.runs if r.success)
        total_runs += n

        # pass@1
        if n > 0:
            pass_1_sum += c / n
        status = task_status(c, n)
        if status == "consistent":
            consistent_count += 1
        elif status == "flaky":
            flaky_count += 1
        else:
            failing_count += 1

        if n >= k:
            pass_k_sum += pass_at_k(n, c, k)
            pass_hat_k_sum += pass_hat_k(n, c, k)
            valid_k_tasks += 1

        for r in task.runs:
            total_latency_ms += r.latency_ms
            total_tokens_in += r.tokens_in
            total_tokens_out += r.tokens_out

    mean_pass_1 = pass_1_sum / total_tasks
    mean_pass_at_k = (pass_k_sum / valid_k_tasks) if valid_k_tasks > 0 else 0.0
    mean_pass_hat_k = (pass_hat_k_sum / valid_k_tasks) if valid_k_tasks > 0 else 0.0
    mean_latency_ms = (total_latency_ms / total_runs) if total_runs > 0 else 0.0

    return {
        "total_tasks": total_tasks,
        "total_runs": total_runs,
        "mean_pass_1": mean_pass_1,
        "mean_pass_at_k": mean_pass_at_k,
        "mean_pass_hat_k": mean_pass_hat_k,
        "consistent_count": consistent_count,
        "flaky_count": flaky_count,
        "failing_count": failing_count,
        "pct_consistent": (consistent_count / total_tasks) * 100.0,
        "pct_flaky": (flaky_count / total_tasks) * 100.0,
        "pct_failing": (failing_count / total_tasks) * 100.0,
        "mean_latency_ms": mean_latency_ms,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "total_tokens": total_tokens_in + total_tokens_out,
    }
