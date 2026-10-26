"""Tests for suite loading and validation in flake_detector.suite."""

from pathlib import Path

import pytest

from flake_detector.suite import SuiteLoadError, load_suite


def test_load_valid_demo_suite() -> None:
    """Verify demo_sim.yaml loads cleanly with 12 tasks and valid sha256_12."""
    suite_path = Path("suites/demo_sim.yaml")
    suite, sha = load_suite(suite_path)

    assert suite.name == "demo-sim"
    assert len(suite.tasks) == 12
    assert len(sha) == 12
    assert all(c in "0123456789abcdef" for c in sha)

    # Check categories
    categories = {t.category for t in suite.tasks}
    assert {"math", "formatting", "reasoning"}.issubset(categories)


def test_missing_file_raises_error() -> None:
    """Loading a nonexistent suite file should raise SuiteLoadError."""
    with pytest.raises(SuiteLoadError, match="Suite file not found"):
        load_suite("suites/nonexistent_suite.yaml")


def test_duplicate_task_id_raises_error(tmp_path: Path) -> None:
    """Duplicate task IDs must be detected and report the duplicate ID."""
    yaml_content = """
name: dupe-test
tasks:
  - id: task-01
    prompt: "First task"
    grader: { type: exact, expected: "a" }
  - id: task-01
    prompt: "Duplicate task"
    grader: { type: exact, expected: "b" }
"""
    p = tmp_path / "dupe.yaml"
    p.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(SuiteLoadError, match="Duplicate task IDs found: task-01"):
        load_suite(p)


def test_unknown_grader_type_raises_error(tmp_path: Path) -> None:
    """Unknown grader type in YAML should produce a clear validation error."""
    yaml_content = """
name: unknown-grader-test
tasks:
  - id: task-01
    prompt: "Test task"
    grader: { type: magical_grader, expected: "a" }
"""
    p = tmp_path / "unknown.yaml"
    p.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(SuiteLoadError, match="Validation error loading suite"):
        load_suite(p)


def test_missing_prompt_raises_error(tmp_path: Path) -> None:
    """Missing required prompt field should fail with field/task identifier."""
    yaml_content = """
name: missing-prompt-test
tasks:
  - id: task-01
    grader: { type: exact, expected: "a" }
"""
    p = tmp_path / "missing.yaml"
    p.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(SuiteLoadError, match="task-01"):
        load_suite(p)
