"""Shared utility helpers used across planning modules."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, List


def project_root() -> Path:
    """Return repository root folder from src module context."""
    return Path(__file__).resolve().parent.parent


def ensure_dir(path: Path) -> None:
    """Create folder if missing."""
    path.mkdir(parents=True, exist_ok=True)


def quarter_labels(num_quarters: int) -> List[str]:
    """Generate labels like Q1, Q2, ..."""
    return [f"Q{i}" for i in range(1, num_quarters + 1)]


def period_to_quarter(period_idx: int, periods_per_quarter: int) -> int:
    """Map 0-indexed period number to 0-indexed quarter."""
    return period_idx // periods_per_quarter


def round_up_to_multiple(value: int, multiple: int) -> int:
    """Round integer up to nearest multiple."""
    if multiple <= 0:
        return value
    return int(math.ceil(value / multiple) * multiple)


def safe_int(value: float) -> int:
    """Round then cast to int for cleaner table values."""
    return int(round(value))


def chunks(values: Iterable[int], size: int) -> List[List[int]]:
    """Split values into chunks of fixed length."""
    values = list(values)
    return [values[i : i + size] for i in range(0, len(values), size)]
