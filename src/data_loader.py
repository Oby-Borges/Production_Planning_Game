"""Load and lightly validate project inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from utils import project_root


def load_inputs(path: Path | None = None) -> Dict[str, Any]:
    """Load JSON input file into dictionary.

    Parameters
    ----------
    path:
        Optional custom path. Defaults to data/game_inputs.json.
    """
    input_path = path or (project_root() / "data" / "game_inputs.json")
    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Minimal structural checks to fail early if data file is edited incorrectly.
    required = ["horizon", "aggregate", "products", "fruits", "bom", "mrp", "mps"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required top-level key: {key}")

    return data
