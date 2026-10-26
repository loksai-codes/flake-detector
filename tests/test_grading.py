"""Tests for flake_detector.grading."""

from flake_detector.grading import extract_first_number, grade
from flake_detector.models import GraderSpec


def test_extract_first_number() -> None:
    """Verify number extraction from varied and messy text formats."""
    assert extract_first_number("The answer is 391.") == 391.0
    assert extract_first_number("Total: 1,024 items") == 1024.0
    assert extract_first_number("-42.5 degrees") == -42.5
    assert extract_first_number("Value: 1.5e3") == 1500.0
    assert extract_first_number("No digits here!") is None
    assert extract_first_number("") is None


def test_exact_grader() -> None:
    """Verify exact grader matching and failure reasons."""
    spec = GraderSpec(type="exact", expected="BLUE", case_sensitive=True, strip=True)

    ok, reason = grade("  BLUE  ", spec)
    assert ok is True
    assert reason is None

    ok, reason = grade("blue", spec)
    assert ok is False
    assert reason == "wrong_answer"

    # Case insensitive
    spec_ci = GraderSpec(type="exact", expected="BLUE", case_sensitive=False)
    ok, _ = grade("blue", spec_ci)
    assert ok is True

    # Empty / whitespace
    ok, reason = grade("", spec)
    assert ok is False
    assert reason == "no_answer"

    ok, reason = grade("   ", spec)
    assert ok is False
    assert reason == "no_answer"

    ok, reason = grade(None, spec)
    assert ok is False
    assert reason == "no_answer"


def test_contains_grader() -> None:
    """Verify contains grader matching and case options."""
    spec = GraderSpec(type="contains", expected="flaky", case_sensitive=False)

    ok, _ = grade("This test is FLAKY sometimes.", spec)
    assert ok is True

    ok, reason = grade("This test is stable.", spec)
    assert ok is False
    assert reason == "wrong_answer"


def test_regex_grader() -> None:
    """Verify regex pattern matching and invalid pattern handling."""
    spec = GraderSpec(type="regex", pattern=r'\{\s*"status":\s*"ok"\s*\}')

    ok, _ = grade('{"status": "ok"}', spec)
    assert ok is True

    ok, reason = grade('{"status": "error"}', spec)
    assert ok is False
    assert reason == "wrong_answer"

    # Invalid regex in pattern
    spec_invalid = GraderSpec(type="regex", pattern=r"[unclosed-bracket")
    ok, reason = grade("anything", spec_invalid)
    assert ok is False
    assert reason == "format_error"


def test_numeric_grader() -> None:
    """Verify numeric grader handles messy text, tolerances, and non-numbers."""
    spec = GraderSpec(type="numeric", expected=391.0, abs_tol=0.0)

    # Messy text with correct answer
    ok, _ = grade("The calculated product is 391.", spec)
    assert ok is True

    # Messy text with wrong answer
    ok, reason = grade("The answer is 390.", spec)
    assert ok is False
    assert reason == "wrong_answer"

    # No number extracted
    ok, reason = grade("I am unsure about the result.", spec)
    assert ok is False
    assert reason == "format_error"

    # Absolute tolerance
    spec_tol = GraderSpec(type="numeric", expected=100.0, abs_tol=0.5)
    ok, _ = grade("100.4", spec_tol)
    assert ok is True
    ok, _ = grade("100.6", spec_tol)
    assert ok is False
