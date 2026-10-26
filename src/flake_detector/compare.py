"""Regression comparison between evaluation runs for flake-detector.

Performs per-task non-overlapping Wilson interval tests and suite-level
paired bootstrap testing on the difference in mean success rate according
to PRD Section 8.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from flake_detector.metrics import wilson_interval

if TYPE_CHECKING:
    from flake_detector.models import RunResults


class TaskComparison(BaseModel):
    """Comparison outcome for a single shared task."""

    task_id: str
    category: str
    rate_a: float
    rate_b: float
    diff: float
    ci_a: tuple[float, float]
    ci_b: tuple[float, float]
    status: str  # "improved", "regressed", "unchanged"


class ComparisonResult(BaseModel):
    """Suite-level comparison results and statistical significance test."""

    baseline_id: str
    candidate_id: str
    shared_tasks_count: int
    tasks_only_in_baseline: list[str] = Field(default_factory=list)
    tasks_only_in_candidate: list[str] = Field(default_factory=list)
    improved_tasks: list[str] = Field(default_factory=list)
    regressed_tasks: list[str] = Field(default_factory=list)
    unchanged_tasks: list[str] = Field(default_factory=list)
    mean_diff: float
    bootstrap_ci: tuple[float, float]
    is_regression: bool
    task_comparisons: list[TaskComparison] = Field(default_factory=list)
    markdown_report: str = ""


def compare_runs(
    baseline: RunResults,
    candidate: RunResults,
    alpha: float = 0.05,
    bootstrap_resamples: int = 1000,
    seed: int = 42,
) -> ComparisonResult:
    """Compare two evaluation runs and determine if candidate regressed.

    Args:
        baseline: Baseline RunResults (Run A).
        candidate: Candidate RunResults (Run B).
        alpha: Significance level for bootstrap interval (default 0.05 for 95% CI).
        bootstrap_resamples: Number of paired bootstrap iterations.
        seed: Fixed seed for reproducible bootstrap sampling.

    Returns:
        A ComparisonResult with per-task and suite-level findings.
    """
    baseline_map = {t.id: t for t in baseline.tasks}
    candidate_map = {t.id: t for t in candidate.tasks}

    all_baseline_ids = set(baseline_map.keys())
    all_candidate_ids = set(candidate_map.keys())

    shared_ids = sorted(all_baseline_ids & all_candidate_ids)
    only_in_baseline = sorted(all_baseline_ids - all_candidate_ids)
    only_in_candidate = sorted(all_candidate_ids - all_baseline_ids)

    if not shared_ids:
        raise ValueError("Cannot compare runs: no common task IDs found between runs.")

    task_comps: list[TaskComparison] = []
    differences: list[float] = []

    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []

    for tid in shared_ids:
        t_a = baseline_map[tid]
        t_b = candidate_map[tid]

        n_a = len(t_a.runs)
        c_a = sum(1 for r in t_a.runs if r.success)
        p_a = c_a / n_a if n_a > 0 else 0.0
        ci_a = wilson_interval(c_a, n_a)

        n_b = len(t_b.runs)
        c_b = sum(1 for r in t_b.runs if r.success)
        p_b = c_b / n_b if n_b > 0 else 0.0
        ci_b = wilson_interval(c_b, n_b)

        diff = p_b - p_a
        differences.append(diff)

        # Non-overlapping Wilson intervals check
        if ci_b[0] > ci_a[1]:
            status = "improved"
            improved.append(tid)
        elif ci_b[1] < ci_a[0]:
            status = "regressed"
            regressed.append(tid)
        else:
            status = "unchanged"
            unchanged.append(tid)

        task_comps.append(
            TaskComparison(
                task_id=tid,
                category=t_b.category,
                rate_a=round(p_a, 4),
                rate_b=round(p_b, 4),
                diff=round(diff, 4),
                ci_a=(round(ci_a[0], 4), round(ci_a[1], 4)),
                ci_b=(round(ci_b[0], 4), round(ci_b[1], 4)),
                status=status,
            )
        )

    # Suite-level paired bootstrap over shared tasks
    m = len(differences)
    mean_diff = sum(differences) / m

    rng = random.Random(seed)
    bootstrap_means: list[float] = []
    for _ in range(bootstrap_resamples):
        sample = rng.choices(differences, k=m)
        bootstrap_means.append(sum(sample) / m)

    bootstrap_means.sort()
    idx_low = int((alpha / 2.0) * bootstrap_resamples)
    idx_high = min(
        bootstrap_resamples - 1,
        int((1.0 - alpha / 2.0) * bootstrap_resamples),
    )
    ci_low = round(bootstrap_means[idx_low], 4)
    ci_high = round(bootstrap_means[idx_high], 4)

    # A regression is a suite-level interval whose upper bound is below 0
    is_regression = ci_high < 0.0

    # Build markdown comparison report
    verdict_text = "REGRESSION DETECTED" if is_regression else "NO REGRESSION DETECTED"
    md_lines: list[str] = [
        "# Flake Detector Regression Report",
        "",
        f"- **Baseline Run (A):** `{baseline.run_id}` ({baseline.agent.name})",
        f"- **Candidate Run (B):** `{candidate.run_id}` ({candidate.agent.name})",
        f"- **Shared Tasks Compared:** {m}",
        f"- **Mean Difference (B - A):** {mean_diff:+.4f} "
        f"(95% CI: [{ci_low:+.4f}, {ci_high:+.4f}])",
        f"- **Verdict:** **{verdict_text}**",
        "",
    ]

    if only_in_baseline or only_in_candidate:
        md_lines.append("## Unshared Tasks")
        if only_in_baseline:
            base_str = ", ".join(f"`{t}`" for t in only_in_baseline)
            md_lines.append(f"- Only in Baseline: {base_str}")
        if only_in_candidate:
            cand_str = ", ".join(f"`{t}`" for t in only_in_candidate)
            md_lines.append(f"- Only in Candidate: {cand_str}")
        md_lines.append("")

    md_lines.append("## Task Comparison Summary")
    md_lines.append(f"- **Improved Tasks:** {len(improved)}")
    md_lines.append(f"- **Regressed Tasks:** {len(regressed)}")
    md_lines.append(f"- **Unchanged Tasks:** {len(unchanged)}")
    md_lines.append("")

    header = (
        "| Task ID | Baseline Rate | Candidate Rate | "
        "Difference | 95% CI (A) | 95% CI (B) | Significance |"
    )
    md_lines.append(header)
    md_lines.append("|:---|:---:|:---:|:---:|:---:|:---:|:---:|")
    for tc in task_comps:
        status_badge = {
            "improved": "Improved",
            "regressed": "Regressed",
            "unchanged": "Unchanged",
        }.get(tc.status, tc.status)
        ci_a_str = f"[{tc.ci_a[0]:.3f}, {tc.ci_a[1]:.3f}]"
        ci_b_str = f"[{tc.ci_b[0]:.3f}, {tc.ci_b[1]:.3f}]"
        row_str = (
            f"| `{tc.task_id}` | {tc.rate_a:.3f} | {tc.rate_b:.3f} | "
            f"{tc.diff:+.3f} | {ci_a_str} | {ci_b_str} | {status_badge} |"
        )
        md_lines.append(row_str)
    md_lines.append("")

    report_str = "\n".join(md_lines)

    return ComparisonResult(
        baseline_id=baseline.run_id,
        candidate_id=candidate.run_id,
        shared_tasks_count=m,
        tasks_only_in_baseline=only_in_baseline,
        tasks_only_in_candidate=only_in_candidate,
        improved_tasks=improved,
        regressed_tasks=regressed,
        unchanged_tasks=unchanged,
        mean_diff=round(mean_diff, 4),
        bootstrap_ci=(ci_low, ci_high),
        is_regression=is_regression,
        task_comparisons=task_comps,
        markdown_report=report_str,
    )
