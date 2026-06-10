"""Pydantic schema for mode configuration files."""

from typing import Any

from pydantic import BaseModel, Field


class PromptSet(BaseModel, frozen=True):
    """Prompt bundle injected by mode."""

    clarify_with_user: str
    transform_messages_into_research_topic: str
    lead_researcher: str
    final_report: str


class CriticCriterion(BaseModel, frozen=True):
    """A single criterion in a critic rubric."""

    id: str
    label: str
    description: str


class CriticRubric(BaseModel, frozen=True):
    """Mode-injected rubric for the critic node."""

    pass_threshold: int = 7
    criteria: list[CriticCriterion] = Field(default_factory=list)
    system_prompt: str = ""


class ModeConfig(BaseModel, frozen=True):
    """Validated configuration for a research mode."""

    mode: str
    display_name: str
    description: str
    prompts: PromptSet
    output_templates: dict[str, Any] = Field(default_factory=dict)
    critic_rubric: CriticRubric = Field(default_factory=CriticRubric)
    kg_recall_strategy: dict[str, Any] = Field(default_factory=dict)
    constitution_rules: str = ""
