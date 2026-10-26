"""Tests for the flake CLI using Typer CliRunner."""

from pathlib import Path

from typer.testing import CliRunner

from flake_detector.cli import app
from flake_detector.suite import load_suite

runner = CliRunner()


def test_cli_validation_errors() -> None:
    """Validation errors must output a clear message and exit with code 2."""
    # 1. k > runs
    res = runner.invoke(app, [
        "run", "--suite", "suites/demo_sim.yaml", "--runs", "5", "--k", "10",
    ])
    assert res.exit_code == 2
    assert "k must satisfy 1 <= k <= runs" in res.output

    # 2. Missing suite file
    res = runner.invoke(app, ["run", "--suite", "suites/nonexistent.yaml"])
    assert res.exit_code == 2
    assert "Suite file not found" in res.output

    # 3. Missing results file in report
    res = runner.invoke(app, ["report", "missing_results.json"])
    assert res.exit_code == 2
    assert "Results file not found" in res.output

    # 4. Missing files in compare
    res = runner.invoke(app, ["compare", "missing_a.json", "missing_b.json"])
    assert res.exit_code == 2
    assert "Baseline file not found" in res.output


def test_cli_run_and_report_end_to_end(tmp_path: Path) -> None:
    """End-to-end run and report creating 5-section markdown and non-empty charts."""
    results_dir = tmp_path / "results"
    charts_dir = tmp_path / "charts"
    report_file = tmp_path / "report.md"

    # 1. Execute run
    res_run = runner.invoke(app, [
        "run",
        "--suite", "suites/demo_sim.yaml",
        "--agent", "sim",
        "--runs", "10",
        "--k", "3",
        "--seed", "42",
        "--out", str(results_dir),
    ])
    assert res_run.exit_code == 0

    json_files = list(results_dir.glob("*.json"))
    assert len(json_files) == 1
    results_json = json_files[0]

    # 2. Generate report
    res_report = runner.invoke(app, [
        "report",
        str(results_json),
        "--out", str(report_file),
        "--charts-dir", str(charts_dir),
    ])
    assert res_report.exit_code == 0
    assert report_file.exists()

    report_text = report_file.read_text(encoding="utf-8")
    suite, _ = load_suite("suites/demo_sim.yaml")

    # Verify all 5 sections present
    assert "## 1. Run Metadata" in report_text
    assert "## 2. Suite Summary" in report_text
    assert "## 3. Per-Task Consistency" in report_text
    assert "## 4. Failure Reasons Breakdown" in report_text
    assert "## 5. Consistency Charts" in report_text

    # Verify every task ID is present
    for task in suite.tasks:
        assert task.id in report_text

    # Verify charts are created and non-empty
    pass_curves = charts_dir / "pass_curves.png"
    task_rates = charts_dir / "task_rates.png"
    assert pass_curves.exists() and pass_curves.stat().st_size > 0
    assert task_rates.exists() and task_rates.stat().st_size > 0


def test_cli_compare_exit_codes(tmp_path: Path) -> None:
    """Compare exits 0 for same runs; for degraded runs exits 0 without flag and 1 with flag."""
    dir_base = tmp_path / "base"
    dir_deg = tmp_path / "deg"

    # Run baseline
    runner.invoke(app, [
        "run",
        "--suite", "suites/demo_sim.yaml",
        "--agent", "sim",
        "--runs", "20",
        "--k", "5",
        "--seed", "42",
        "--out", str(dir_base),
    ])
    # Run degraded
    runner.invoke(app, [
        "run",
        "--suite", "suites/demo_sim_degraded.yaml",
        "--agent", "sim",
        "--runs", "20",
        "--k", "5",
        "--seed", "42",
        "--out", str(dir_deg),
    ])

    base_json = list(dir_base.glob("*.json"))[0]
    deg_json = list(dir_deg.glob("*.json"))[0]

    # Identical runs with --fail-on-regression -> exit 0
    res_same = runner.invoke(app, [
        "compare",
        str(base_json),
        str(base_json),
        "--fail-on-regression",
    ])
    assert res_same.exit_code == 0

    # Degraded run WITHOUT --fail-on-regression -> exit 0
    res_deg_no_flag = runner.invoke(app, [
        "compare",
        str(base_json),
        str(deg_json),
    ])
    assert res_deg_no_flag.exit_code == 0

    # Degraded run WITH --fail-on-regression -> exit 1
    res_deg_flag = runner.invoke(app, [
        "compare",
        str(base_json),
        str(deg_json),
        "--fail-on-regression",
    ])
    assert res_deg_flag.exit_code == 1
    has_regression_text = (
        "REGRESSION DETECTED" in res_deg_flag.output
        or "regression" in res_deg_flag.output.lower()
    )
    assert has_regression_text
