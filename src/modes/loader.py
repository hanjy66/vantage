"""Loader for mode YAML files."""

from functools import lru_cache
from pathlib import Path

import yaml

from src.modes.schema import ModeConfig


MODES_DIR = Path(__file__).parent


@lru_cache
def _load_constitution_enforcement() -> str:
    """Load constitution_enforcement block (empty string if file missing)."""
    path = MODES_DIR / "constitution.yaml"
    if not path.exists():
        return ""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("constitution_enforcement", "")


@lru_cache
def load_mode(name: str) -> ModeConfig:
    """Load and validate a mode config by name, merging constitution rules."""
    mode_path = MODES_DIR / f"{name}.yaml"
    if not mode_path.exists():
        raise FileNotFoundError(f"Mode config not found: {mode_path}")

    with mode_path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)

    data["constitution_rules"] = _load_constitution_enforcement()
    config = ModeConfig.model_validate(data)
    if config.mode != name:
        raise ValueError(
            f"Mode config mismatch: requested {name!r}, got {config.mode!r}"
        )

    return config
