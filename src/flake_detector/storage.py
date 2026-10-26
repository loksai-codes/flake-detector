"""Atomic storage and persistence helpers for evaluation results.

Ensures results are written atomically (temp file -> replace) to prevent
partial/corrupted files, and validates schemas on load according to PRD Section 7.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from flake_detector.models import RunResults


def generate_run_id(
    suite_name: str,
    agent_name: str,
    timestamp: datetime | None = None,
) -> str:
    """Generate a sanitized, human-readable run_id.

    Format: YYYY-MM-DDTHH-MM-SS_{suite_name}_{agent_name}
    Using hyphens in timestamps ensures full cross-platform filesystem compatibility.
    """
    ts = timestamp or datetime.now(UTC)
    ts_str = ts.strftime("%Y-%m-%dT%H-%M-%S")
    clean_suite = re.sub(r"[^a-zA-Z0-9_\-]", "-", suite_name)
    clean_agent = re.sub(r"[^a-zA-Z0-9_\-]", "-", agent_name)
    return f"{ts_str}_{clean_suite}_{clean_agent}"


def save_results_atomic(results: RunResults, out_path: str | Path) -> Path:
    """Atomically save a RunResults object to disk.

    Writes to a temporary file in the target directory first, then performs
    an atomic replace to ensure no partial files exist on crash or interruption.

    Args:
        results: RunResults model instance to serialize.
        out_path: Target directory or file path.

    Returns:
        The final Path where results were saved.
    """
    target = Path(out_path)
    if target.is_dir() or target.suffix != ".json":
        target = target / f"{results.run_id}.json"

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = target.parent / f".{target.name}.tmp.{uuid.uuid4().hex[:8]}"

    try:
        json_data = results.model_dump_json(indent=2)
        tmp_file.write_text(json_data, encoding="utf-8")
        # os.replace is atomic on both POSIX and Windows (NTFS)
        os.replace(tmp_file, target)
    except Exception:
        if tmp_file.exists():
            tmp_file.unlink(missing_ok=True)
        raise

    return target


def load_results(path: str | Path) -> RunResults:
    """Load and validate a RunResults JSON file.

    Args:
        path: Path to the JSON results file.

    Returns:
        The validated RunResults instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValidationError: If JSON format does not match the schema.
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Results file not found: {target}")

    content = target.read_text(encoding="utf-8")
    return RunResults.model_validate_json(content)
