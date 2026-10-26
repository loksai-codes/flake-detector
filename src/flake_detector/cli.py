"""CLI commands for flake-detector.

Implements `flake run`, `flake report`, and `flake compare` with Rich formatting
and strict exit codes according to PRD Section 8.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from flake_detector.compare import compare_runs
from flake_detector.metrics import suite_summary
from flake_detector.report import generate_charts, generate_markdown_report
from flake_detector.runner import run_suite
from flake_detector.storage import load_results, save_results_atomic
from flake_detector.suite import SuiteLoadError, load_suite

app = typer.Typer(
    name="flake",
    help="AI Agent consistency, flakiness, and CI regression evaluator.",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def run(
    suite: Path = typer.Option(..., "--suite", "-s", help="Path to YAML suite file"),
    agent: str = typer.Option("sim", "--agent", "-a", help="Agent type: 'sim' or 'groq'"),
    runs: int = typer.Option(20, "--runs", "-n", help="Number of runs per task"),
    k: int = typer.Option(5, "--k", "-k", help="Sample size k for pass@k and pass^k"),
    seed: int = typer.Option(42, "--seed", help="Deterministic base seed"),
    workers: int | None = typer.Option(
        None, "--workers", "-w", help="Worker threads (default: 8 for sim, 1 for groq)"
    ),
    out: Path = typer.Option(Path("results"), "--out", "-o", help="Output directory or file"),
    resume: bool = typer.Option(False, "--resume", help="Skip runs already present in results"),
    max_rpm: int = typer.Option(20, "--max-rpm", help="Rate limit for API calls (Groq)"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name override"),
) -> None:
    """Run an AI agent on a task suite N times and record consistency data."""
    # 1. Validation
    if runs < 1:
        err_console.print(f"[bold red]Validation error:[/bold red] runs must be >= 1, got {runs}")
        raise typer.Exit(code=2)
    if k < 1 or k > runs:
        err_console.print(
            f"[bold red]Validation error:[/bold red] k must satisfy 1 <= k <= runs ({runs}), "
            f"got {k}"
        )
        raise typer.Exit(code=2)

    if not suite.exists():
        err_console.print(f"[bold red]Error:[/bold red] Suite file not found: {suite}")
        raise typer.Exit(code=2)

    try:
        suite_obj, sha256_12 = load_suite(suite)
    except SuiteLoadError as exc:
        err_console.print(f"[bold red]Suite loading error:[/bold red]\n{exc}")
        raise typer.Exit(code=2)

    # 2. Agent instantiation
    agent_type = agent.lower().strip()
    if agent_type == "sim":
        from flake_detector.agents.simulated import SimulatedAgent
        agent_obj = SimulatedAgent(config={"seed": seed})
    elif agent_type == "groq":
        try:
            from flake_detector.agents.groq_agent import GroqAgent
            agent_obj = GroqAgent(model=model, max_rpm=max_rpm)
        except Exception as exc:
            err_console.print(f"[bold red]Groq agent initialization error:[/bold red] {exc}")
            raise typer.Exit(code=2)
    else:
        err_console.print(
            f"[bold red]Error:[/bold red] Unknown agent '{agent}'. Supported: 'sim', 'groq'"
        )
        raise typer.Exit(code=2)

    # 3. Resume handling
    existing_results = None
    if resume:
        if out.is_file() and out.suffix == ".json":
            try:
                existing_results = load_results(out)
                console.print(f"[cyan]Resuming from existing file:[/cyan] {out}")
            except Exception as exc:
                err_console.print(
                    f"[yellow]Warning: Could not load resume file {out}: {exc}[/yellow]"
                )
        elif out.is_dir():
            matching = sorted(out.glob(f"*{suite_obj.name}_{agent_type}*.json"), reverse=True)
            if matching:
                try:
                    existing_results = load_results(matching[0])
                    console.print(f"[cyan]Resuming from latest run:[/cyan] {matching[0].name}")
                except Exception as exc:
                    err_console.print(
                        f"[yellow]Warning: Could not load {matching[0]}: {exc}[/yellow]"
                    )

    total_tasks = len(suite_obj.tasks)
    total_runs = total_tasks * runs
    header_msg = (
        f"[bold cyan]flake run[/bold cyan]\n"
        f"Suite: [bold]{suite_obj.name}[/bold] ({total_tasks} tasks) | "
        f"Agent: [bold]{agent_type}[/bold] | "
        f"Runs: [bold]{runs}[/bold] | k: [bold]{k}[/bold] | Seed: [bold]{seed}[/bold]"
    )
    console.print(Panel(header_msg, border_style="cyan"))

    # 4. Execution with Rich Progress
    actual_workers = workers if workers is not None else (1 if agent_type == "groq" else 8)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(complete_style="cyan", finished_style="green"),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_tracker = progress.add_task("[cyan]Running suite...", total=total_runs)

        def on_progress(completed: int, total: int, task_id: str, record) -> None:
            progress.update(task_tracker, advance=1, description=f"[cyan]Task: {task_id}")

        results = run_suite(
            suite=suite_obj,
            agent=agent_obj,
            runs=runs,
            seed=seed,
            workers=actual_workers,
            k=k,
            suite_sha256=sha256_12,
            existing=existing_results,
            on_progress=on_progress,
        )

    # 5. Save results
    saved_path = save_results_atomic(results, out)
    console.print(f"[green][OK][/green] Results saved to: [bold]{saved_path}[/bold]")

    # 6. Display summary
    summary = suite_summary(results.tasks, k)
    table = Table(title=f"Suite Summary: {suite_obj.name}", border_style="dim")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    p1 = summary["mean_pass_1"]
    phat = summary["mean_pass_hat_k"]
    pat = summary["mean_pass_at_k"]
    table.add_row("Mean pass@1 (Success Rate)", f"{p1:.4f} ({p1*100:.1f}%)")
    table.add_row(f"Mean pass^{k} (All {k} Succeed)", f"{phat:.4f} ({phat*100:.1f}%)")
    table.add_row(f"Mean pass@{k} (>=1 Succeeds)", f"{pat:.4f} ({pat*100:.1f}%)")
    table.add_row(
        "Consistent Tasks (100%)",
        f"{summary['consistent_count']} ({summary['pct_consistent']:.1f}%)",
    )
    table.add_row("Flaky Tasks", f"{summary['flaky_count']} ({summary['pct_flaky']:.1f}%)")
    table.add_row(
        "Failing Tasks (0%)",
        f"{summary['failing_count']} ({summary['pct_failing']:.1f}%)",
    )
    table.add_row("Mean Latency", f"{summary['mean_latency_ms']:.1f} ms")
    table.add_row("Total Tokens", f"{summary['total_tokens']:,}")
    console.print(table)


@app.command()
def report(
    results_file: Path = typer.Argument(..., help="Path to JSON results file"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output Markdown report path"),
    charts_dir: Path = typer.Option(Path("charts"), "--charts-dir", help="Directory for charts"),
) -> None:
    """Generate Markdown report and Matplotlib consistency charts from a results file."""
    if not results_file.exists():
        err_console.print(f"[bold red]Error:[/bold red] Results file not found: {results_file}")
        raise typer.Exit(code=2)

    try:
        results = load_results(results_file)
    except Exception as exc:
        err_console.print(f"[bold red]Error loading results file:[/bold red] {exc}")
        raise typer.Exit(code=2)

    charts_dir.mkdir(parents=True, exist_ok=True)
    with console.status("[cyan]Generating consistency charts..."):
        chart_paths = generate_charts(results, charts_dir)

    report_content = generate_markdown_report(results, charts_dir=charts_dir)

    target_report_file = out if out is not None else results_file.with_suffix(".md")
    target_report_file.write_text(report_content, encoding="utf-8")

    console.print(f"[green][OK][/green] Report generated: [bold]{target_report_file}[/bold]")
    console.print(f"[green][OK][/green] Charts generated in: [bold]{charts_dir}[/bold]")
    for name, path in chart_paths.items():
        console.print(f"  - {name}: {path}")


@app.command()
def compare(
    baseline_file: Path = typer.Argument(..., help="Baseline results JSON (Run A)"),
    candidate_file: Path = typer.Argument(..., help="Candidate results JSON (Run B)"),
    alpha: float = typer.Option(0.05, "--alpha", help="Significance level (default 0.05)"),
    fail_on_regression: bool = typer.Option(
        False, "--fail-on-regression", help="Exit 1 on regression"
    ),
) -> None:
    """Compare two runs and detect statistical regressions using paired bootstrap."""
    if not baseline_file.exists():
        err_console.print(f"[bold red]Error:[/bold red] Baseline file not found: {baseline_file}")
        raise typer.Exit(code=2)
    if not candidate_file.exists():
        err_console.print(f"[bold red]Error:[/bold red] Candidate file not found: {candidate_file}")
        raise typer.Exit(code=2)

    try:
        baseline_res = load_results(baseline_file)
        candidate_res = load_results(candidate_file)
    except Exception as exc:
        err_console.print(f"[bold red]Error loading results:[/bold red] {exc}")
        raise typer.Exit(code=2)

    try:
        comp = compare_runs(baseline_res, candidate_res, alpha=alpha)
    except ValueError as exc:
        err_console.print(f"[bold red]Comparison error:[/bold red] {exc}")
        raise typer.Exit(code=2)

    # Display comparison summary
    if comp.is_regression:
        panel_title = "[bold red]REGRESSION DETECTED[/bold red]"
        border = "red"
    else:
        panel_title = "[bold green]NO REGRESSION DETECTED[/bold green]"
        border = "green"

    ci_str = f"[{comp.bootstrap_ci[0]:+.4f}, {comp.bootstrap_ci[1]:+.4f}]"
    summary_text = (
        f"Baseline (A): [bold]{comp.baseline_id}[/bold]\n"
        f"Candidate (B): [bold]{comp.candidate_id}[/bold]\n"
        f"Shared Tasks: {comp.shared_tasks_count} | "
        f"Improved: [green]{len(comp.improved_tasks)}[/green] | "
        f"Regressed: [red]{len(comp.regressed_tasks)}[/red] | "
        f"Unchanged: {len(comp.unchanged_tasks)}\n"
        f"Mean Difference: [bold]{comp.mean_diff:+.4f}[/bold] (95% CI: {ci_str})"
    )
    console.print(Panel(summary_text, title=panel_title, border_style=border))

    table = Table(title="Task Comparison", border_style="dim")
    table.add_column("Task ID", style="bold")
    table.add_column("Base Rate", justify="right")
    table.add_column("Cand Rate", justify="right")
    table.add_column("Diff", justify="right")
    table.add_column("Significance")

    for tc in comp.task_comparisons:
        if tc.status == "improved":
            color = "green"
        elif tc.status == "regressed":
            color = "red"
        else:
            color = "dim"
        table.add_row(
            tc.task_id,
            f"{tc.rate_a:.3f}",
            f"{tc.rate_b:.3f}",
            f"{tc.diff:+.3f}",
            f"[{color}]{tc.status}[/{color}]",
        )
    console.print(table)

    if comp.is_regression and fail_on_regression:
        err_console.print(
            "[bold red]Exiting with code 1 due to detected regression "
            "(--fail-on-regression).[/bold red]"
        )
        raise typer.Exit(code=1)

    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()

