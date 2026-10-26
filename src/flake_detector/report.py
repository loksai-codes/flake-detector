"""Report generation and Matplotlib charts for flake-detector.

Generates the five-section Markdown report and colorblind-safe consistency
charts according to PRD Section 9.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt

from flake_detector.metrics import (
    flakiness,
    pass_at_k,
    pass_curves,
    pass_hat_k,
    suite_summary,
    task_status,
    wilson_interval,
)

if TYPE_CHECKING:
    from flake_detector.models import RunResults


def generate_charts(results: RunResults, charts_dir: str | Path) -> dict[str, Path]:
    """Generate Matplotlib charts for pass curves and task success rates.

    Args:
        results: RunResults instance.
        charts_dir: Directory where PNG charts should be saved.

    Returns:
        A dictionary mapping chart keys ('pass_curves', 'task_rates') to Path objects.
    """
    out_dir = Path(charts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pass_curves_path = out_dir / "pass_curves.png"
    task_rates_path = out_dir / "task_rates.png"

    # Style configuration for clean, publication-grade aesthetics
    plt.rcParams.update({
        "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
        "axes.edgecolor": "#94a3b8",
        "axes.linewidth": 1.0,
        "grid.color": "#e2e8f0",
        "grid.linestyle": "--",
        "grid.alpha": 0.7,
    })

    # ================= 1. pass_curves.png =================
    k_max = results.params.k
    curves = pass_curves(results.tasks, max_k=k_max)
    k_vals = curves["k"]
    p_at = curves["pass_at_k"]
    p_hat = curves["pass_hat_k"]

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=200)
    ax.plot(
        k_vals, p_at, marker="o", color="#0284c7", linewidth=2.2,
        label=r"$\mathrm{pass}@k$ (Can succeed)",
    )
    ax.plot(
        k_vals, p_hat, marker="s", color="#7c3aed", linewidth=2.2,
        label=r"$\mathrm{pass}^k$ (Always succeeds)",
    )
    ax.fill_between(k_vals, p_hat, p_at, color="#38bdf8", alpha=0.18, label="Dependability Gap")

    ax.set_title(
        f"Suite Consistency Curves ({results.suite.name})",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_xlabel("Sample Size (k)", fontsize=11, labelpad=8)
    ax.set_ylabel("Probability", fontsize=11, labelpad=8)
    ax.set_ylim(-0.02, 1.05)
    ax.set_xticks([int(k) for k in k_vals])
    ax.grid(True)
    ax.legend(frameon=True, facecolor="white", edgecolor="#cbd5e1", fontsize=10)
    fig.tight_layout()
    fig.savefig(pass_curves_path)
    plt.close(fig)

    # ================= 2. task_rates.png =================
    # Collect per-task success rates and Wilson 95% confidence intervals
    task_data: list[dict] = []
    for t in results.tasks:
        n = len(t.runs)
        c = sum(1 for r in t.runs if r.success)
        p = c / n if n > 0 else 0.0
        low, high = wilson_interval(c, n)
        task_data.append({
            "id": t.id,
            "rate": p,
            "low": low,
            "high": high,
            "err_minus": max(0.0, p - low),
            "err_plus": max(0.0, high - p),
            "status": task_status(c, n),
        })

    # Sort tasks by success rate ascending for horizontal bar chart
    task_data.sort(key=lambda d: d["rate"])

    fig, ax = plt.subplots(figsize=(8, max(4.0, len(task_data) * 0.38)), dpi=200)
    y_positions = list(range(len(task_data)))
    labels = [d["id"] for d in task_data]
    rates = [d["rate"] for d in task_data]
    xerr = [
        [d["err_minus"] for d in task_data],
        [d["err_plus"] for d in task_data],
    ]

    # Colorblind-safe palette by task status
    color_map = {
        "consistent": "#10b981",  # Emerald green
        "flaky": "#f59e0b",       # Amber
        "failing": "#ef4444",     # Rose / red
    }
    bar_colors = [color_map.get(d["status"], "#64748b") for d in task_data]

    ax.barh(
        y_positions, rates, xerr=xerr, color=bar_colors, alpha=0.85, height=0.6,
        capsize=4, error_kw={"elinewidth": 1.5, "ecolor": "#334155", "capthick": 1.5},
    )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.set_xlim(-0.02, 1.05)
    ax.set_xlabel(
        "Success Rate (p) with Wilson 95% Confidence Interval",
        fontsize=10.5, labelpad=8,
    )
    ax.set_title("Per-Task Success Rates & Uncertainty", fontsize=12.5, fontweight="bold", pad=12)
    ax.grid(axis="x")

    # Legend elements for status colors
    handles = [
        plt.Rectangle((0, 0), 1, 1, color="#10b981", label="Consistent (100%)"),
        plt.Rectangle((0, 0), 1, 1, color="#f59e0b", label="Flaky"),
        plt.Rectangle((0, 0), 1, 1, color="#ef4444", label="Failing (0%)"),
    ]
    ax.legend(
        handles=handles, loc="lower right", frameon=True,
        facecolor="white", edgecolor="#cbd5e1", fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(task_rates_path)
    plt.close(fig)

    return {
        "pass_curves": pass_curves_path,
        "task_rates": task_rates_path,
    }


def generate_markdown_report(
    results: RunResults,
    charts_dir: str | Path | None = None,
) -> str:
    """Build the Markdown report according to PRD Section 9.

    Contains:
    1. Run metadata
    2. Suite summary (with plain-language notes and wide-interval warning if n < 10)
    3. Per-task table sorted by flakiness descending
    4. Failure reasons breakdown
    5. Charts embedded by relative path
    """
    summary = suite_summary(results.tasks, results.params.k)
    runs_per_task = results.params.runs
    k = results.params.k

    lines: list[str] = []

    # Title
    lines.append(f"# Flake Detector Report: `{results.suite.name}`")
    lines.append("")

    # Section 1: Run Metadata
    lines.append("## 1. Run Metadata")
    agent_info = f"- **Agent:** `{results.agent.name}`"
    if results.agent.model:
        agent_info += f" (model: `{results.agent.model}`)"
    lines.append(agent_info)
    lines.append(f"- **Suite:** `{results.suite.name}` (SHA-256: `{results.suite.sha256_12}`)")
    lines.append(f"- **Parameters:** `runs={runs_per_task}`, `k={k}`, `seed={results.params.seed}`")
    lines.append(f"- **Created At:** {results.created_at}")
    lines.append(f"- **Run ID:** `{results.run_id}`")
    lines.append("")

    # Section 2: Suite Summary
    p1 = summary["mean_pass_1"]
    phat = summary["mean_pass_hat_k"]
    pat = summary["mean_pass_at_k"]
    lines.append("## 2. Suite Summary")
    lines.append(f"- **Mean pass@1 (Success Rate):** {p1:.4f} ({p1 * 100:.1f}%)")
    lines.append(f"- **Mean pass^{k} (All {k} Succeed):** {phat:.4f} ({phat * 100:.1f}%)")
    lines.append(f"- **Mean pass@{k} (At least 1 Succeeds):** {pat:.4f} ({pat * 100:.1f}%)")
    dist_str = (
        f"- **Task Distribution:** {summary['pct_consistent']:.1f}% consistent "
        f"({summary['consistent_count']}), {summary['pct_flaky']:.1f}% flaky "
        f"({summary['flaky_count']}), {summary['pct_failing']:.1f}% failing "
        f"({summary['failing_count']})"
    )
    lines.append(dist_str)
    lines.append(f"- **Mean Latency:** {summary['mean_latency_ms']:.1f} ms")
    tokens_str = (
        f"- **Total Tokens:** {summary['total_tokens']:,} "
        f"(in: {summary['total_tokens_in']:,}, out: {summary['total_tokens_out']:,})"
    )
    lines.append(tokens_str)
    lines.append("")

    # Plain language notes & sample size warning
    lines.append("> **Understanding `pass@k` vs `pass^k`:**")
    note1 = (
        f"> `pass@{k}` is the probability that *at least one* out of {k} attempts "
        "succeeds (optimistic capability)."
    )
    note2 = (
        f"> `pass^{k}` is the probability that *all* {k} attempts succeed without "
        "failure (true dependability)."
    )
    lines.append(note1)
    lines.append(note2)
    lines.append("> The difference between them represents the agent's flakiness gap.")
    lines.append("")

    if runs_per_task < 10:
        warn = (
            f"> **Warning:** Sample size per task is small (`n = {runs_per_task} < 10`). "
            "Confidence intervals are wide."
        )
        lines.append(warn)
        lines.append("")

    # Section 3: Per-Task Table (Sorted by flakiness descending)
    lines.append("## 3. Per-Task Consistency")
    tbl_hdr = (
        "| Task ID | Category | Runs (n) | Passes (c) | "
        "Success Rate | 95% CI (Wilson) | pass@k | pass^k | Status |"
    )
    lines.append(tbl_hdr)
    lines.append("|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|")

    task_rows: list[dict] = []
    for t in results.tasks:
        n = len(t.runs)
        c = sum(1 for r in t.runs if r.success)
        p = c / n if n > 0 else 0.0
        low, high = wilson_interval(c, n)
        p_at = pass_at_k(n, c, k) if n >= k else p
        p_hat = pass_hat_k(n, c, k) if n >= k else p
        f_score = flakiness(c, n)
        status = task_status(c, n)
        task_rows.append({
            "id": t.id,
            "category": t.category,
            "n": n,
            "c": c,
            "p": p,
            "ci": f"[{low:.3f}, {high:.3f}]",
            "p_at": p_at,
            "p_hat": p_hat,
            "status": status,
            "flakiness": f_score,
        })

    # Sort by flakiness descending, then by rate ascending
    task_rows.sort(key=lambda row: (-row["flakiness"], row["p"]))

    for row in task_rows:
        row_str = (
            f"| `{row['id']}` | {row['category']} | {row['n']} | {row['c']} | "
            f"{row['p']:.3f} | {row['ci']} | {row['p_at']:.3f} | {row['p_hat']:.3f} | "
            f"`{row['status']}` |"
        )
        lines.append(row_str)
    lines.append("")

    # Section 4: Failure Reasons Breakdown
    lines.append("## 4. Failure Reasons Breakdown")
    reasons_count: dict[str, int] = {}
    total_failures = 0

    for t in results.tasks:
        for r in t.runs:
            if not r.success:
                reason = r.failure_reason or "unknown"
                reasons_count[reason] = reasons_count.get(reason, 0) + 1
                total_failures += 1

    if total_failures == 0:
        lines.append("No failures recorded across any task runs! (100% success)")
    else:
        lines.append("| Failure Reason | Count | Percentage |")
        lines.append("|:---|:---:|:---:|")
        sorted_reasons = sorted(reasons_count.items(), key=lambda item: -item[1])
        for reason, count in sorted_reasons:
            pct = (count / total_failures) * 100.0
            lines.append(f"| `{reason}` | {count} | {pct:.1f}% |")
    lines.append("")

    # Section 5: Charts
    lines.append("## 5. Consistency Charts")
    if charts_dir is not None:
        c_path = Path(charts_dir)
        lines.append(f"![Pass Curves]({c_path.as_posix()}/pass_curves.png)")
        lines.append("")
        lines.append(f"![Task Rates]({c_path.as_posix()}/task_rates.png)")
    else:
        lines.append("![Pass Curves](charts/pass_curves.png)")
        lines.append("")
        lines.append("![Task Rates](charts/task_rates.png)")
    lines.append("")

    return "\n".join(lines)
