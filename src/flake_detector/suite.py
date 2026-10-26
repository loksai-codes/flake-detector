"""Suite loading and validation for flake-detector.

Loads YAML suites, validates against Pydantic models with clear task-specific
error messages, and computes sha256_12 hashes for run provenance.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError

from flake_detector.models import Suite


class SuiteLoadError(Exception):
    """Raised when a suite file cannot be loaded or fails validation."""


def compute_sha256_12(data: bytes) -> str:
    """Compute the first 12 characters of the SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()[:12]


def load_suite(path: str | Path) -> tuple[Suite, str]:
    """Load and validate a YAML suite file.

    Args:
        path: Filepath to the YAML suite.

    Returns:
        A tuple of (Suite, sha256_12 hash of file content).

    Raises:
        SuiteLoadError: If file is missing, invalid YAML, or fails schema validation.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise SuiteLoadError(f"Suite file not found: {file_path}")

    try:
        raw_bytes = file_path.read_bytes()
    except Exception as e:
        raise SuiteLoadError(f"Error reading suite file '{file_path}': {e}") from e

    sha256_12 = compute_sha256_12(raw_bytes)

    try:
        content = yaml.safe_load(raw_bytes.decode("utf-8"))
    except yaml.YAMLError as e:
        raise SuiteLoadError(f"YAML syntax error in suite file '{file_path}': {e}") from e

    if not isinstance(content, dict):
        raise SuiteLoadError(f"Invalid suite format in '{file_path}': root must be a YAML mapping")

    try:
        suite = Suite.model_validate(content)
    except ValidationError as err:
        messages = []
        for error in err.errors():
            loc = error.get("loc", ())
            msg = error.get("msg", "")
            # Attempt to identify task_id if location points to tasks list
            task_hint = ""
            if len(loc) >= 2 and loc[0] == "tasks" and isinstance(loc[1], int):
                tasks_raw = content.get("tasks", [])
                if isinstance(tasks_raw, list) and loc[1] < len(tasks_raw):
                    task_dict = tasks_raw[loc[1]]
                    if isinstance(task_dict, dict) and "id" in task_dict:
                        task_hint = f" (task id: '{task_dict['id']}')"
            location_str = " -> ".join(str(part) for part in loc)
            messages.append(f"Field '{location_str}'{task_hint}: {msg}")
        joined = "\n  - ".join(messages)
        raise SuiteLoadError(
            f"Validation error loading suite '{file_path}':\n  - {joined}"
        ) from err

    return suite, sha256_12
