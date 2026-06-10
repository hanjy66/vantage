"""Mode resolution from LangGraph runnable config."""

from langchain_core.runnables import RunnableConfig

from src.modes.loader import load_mode
from src.modes.schema import ModeConfig


def resolve_mode(config: RunnableConfig) -> ModeConfig:
    """Resolve the requested mode from RunnableConfig."""
    configurable = config.get("configurable", {}) if config else {}
    return load_mode(configurable.get("mode", "general"))
