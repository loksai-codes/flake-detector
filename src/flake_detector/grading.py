"""Deterministic answer grading for flake-detector.

Supports exact, contains, regex, and numeric graders according to
PRD Section 6 (FR-2).
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flake_detector.models import GraderSpec

NUMBER_PATTERN = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")


def extract_first_number(text: str) -> float | None:
    """Extract the first valid number from text, removing thousand separators.

    Args:
        text: String possibly containing a number (e.g. 'The answer is 391.').

    Returns:
        The extracted float, or None if no number was found.
    """
    match = NUMBER_PATTERN.search(text)
    if not match:
        return None
    raw = match.group(0).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def grade(answer: str | None, spec: GraderSpec) -> tuple[bool, str | None]:
    """Grade an answer against a GraderSpec.

    Returns:
        (True, None) on success, or (False, failure_reason) on failure.
        Valid failure reasons: 'no_answer', 'format_error', 'wrong_answer'.
    """
    if answer is None or not answer.strip():
        return False, "no_answer"

    text = answer.strip() if spec.strip else answer

    if spec.type == "exact":
        expected = str(spec.expected)
        if spec.strip:
            expected = expected.strip()
        if not spec.case_sensitive:
            text = text.lower()
            expected = expected.lower()
        if text == expected:
            return True, None
        return False, "wrong_answer"

    if spec.type == "contains":
        expected = str(spec.expected)
        if spec.strip:
            expected = expected.strip()
        if not spec.case_sensitive:
            text = text.lower()
            expected = expected.lower()
        if expected in text:
            return True, None
        return False, "wrong_answer"

    if spec.type == "regex":
        pattern = spec.pattern if spec.pattern is not None else str(spec.expected)
        flags = 0 if spec.case_sensitive else re.IGNORECASE
        try:
            if re.search(pattern, text, flags=flags):
                return True, None
            return False, "wrong_answer"
        except re.error:
            return False, "format_error"

    if spec.type == "numeric":
        extracted = extract_first_number(text)
        if extracted is None:
            return False, "format_error"
        if spec.expected is None:
            return False, "format_error"

        try:
            expected_num = float(spec.expected)
        except (ValueError, TypeError):
            return False, "format_error"

        if math.isclose(extracted, expected_num, rel_tol=spec.rel_tol, abs_tol=spec.abs_tol):
            return True, None
        return False, "wrong_answer"

    return False, "wrong_answer"
