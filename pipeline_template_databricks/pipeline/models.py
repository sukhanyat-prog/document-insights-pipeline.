"""What the LLM must return for one document. Change these fields if you extract something else."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Finding(BaseModel):
    theme_hint: str = Field(description="Short free-text label for the theme (2-6 words)")
    direction: Literal["negative", "positive", "neutral", "mixed"] = "neutral"
    severity: Literal["high", "medium", "low"] = "medium"
    evidence_text: str = Field(description="Verbatim quote from the document, max 300 characters")
    page_ref: int | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("direction", "severity", mode="before")
    @classmethod
    def _lower(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("page_ref", mode="before")
    @classmethod
    def _page(cls, value):
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, value):
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return 0.5


class DocumentExtraction(BaseModel):
    title: str | None = None
    summary: str | None = None
    source: str | None = None
    document_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD if visible")
    findings: list[Finding] = Field(default_factory=list)
