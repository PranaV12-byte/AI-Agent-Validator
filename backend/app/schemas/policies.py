"""Pydantic schemas for policy APIs."""

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HTML_TAG_RE = re.compile(r"<[^>]+>")

PolicyRuleType = (
    "semantic",
    "keyword",
    "regex_match",
    "llm_eval",
    "pii_redaction",
    "prompt_injection",
)


def _validate_rule_parameters(
    rule_type: str, parameters: dict[str, Any] | None
) -> None:
    params = parameters or {}

    if rule_type == "regex_match":
        pattern = params.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(
                "regex_match requires parameters.pattern as non-empty string"
            )

    if rule_type == "llm_eval":
        rubric = params.get("rubric")
        if not isinstance(rubric, str) or not rubric.strip():
            raise ValueError("llm_eval requires parameters.rubric as non-empty string")

    if rule_type == "keyword":
        keyword = params.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("keyword requires parameters.keyword as non-empty string")


class PolicyCreate(BaseModel):
    """Request body for creating a policy."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rule_text: str = Field(min_length=1)
    rule_type: str = Field(default="semantic", max_length=50)
    parameters: dict[str, Any] | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_html(cls, value: str | None) -> str | None:
        """Strip HTML/script tags from string fields to prevent XSS."""
        if isinstance(value, str):
            return _HTML_TAG_RE.sub("", value).strip()
        return value

    @model_validator(mode="after")
    def validate_rule_parameters(self) -> "PolicyCreate":
        if self.rule_type not in PolicyRuleType:
            raise ValueError("Unsupported rule_type")
        _validate_rule_parameters(self.rule_type, self.parameters)
        return self


class PolicyUpdate(BaseModel):
    """Request body for updating a policy."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    rule_text: str | None = Field(default=None, min_length=1)
    rule_type: str | None = Field(default=None, max_length=50)
    parameters: dict[str, Any] | None = None
    is_enabled: bool | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_html(cls, value: str | None) -> str | None:
        """Strip HTML/script tags from string fields to prevent XSS."""
        if isinstance(value, str):
            return _HTML_TAG_RE.sub("", value).strip()
        return value

    @model_validator(mode="after")
    def validate_rule_parameters(self) -> "PolicyUpdate":
        if self.rule_type is not None and self.rule_type not in PolicyRuleType:
            raise ValueError("Unsupported rule_type")

        if self.parameters is not None and self.rule_type is None:
            raise ValueError("rule_type must be provided when parameters are updated")

        if self.rule_type is not None:
            _validate_rule_parameters(self.rule_type, self.parameters)

        return self


class PolicyResponse(BaseModel):
    """Policy response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    rule_text: str
    rule_type: str
    parameters: dict[str, Any]
    is_enabled: bool
    version: int
    policy_hash: str | None
    algorand_tx_id: str | None
    created_at: datetime
    updated_at: datetime


class PolicyListResponse(BaseModel):
    """Paginated-lite list response for policies."""

    policies: list[PolicyResponse]
    total: int


class PolicyConfigUpdate(BaseModel):
    """Request body for policy behavior configuration updates."""

    injection_protection: bool | None = None
    injection_sensitivity: Literal["strict", "moderate", "lenient"] | None = None
    pii_redaction: bool | None = None
    policy_enforcement: bool | None = None
    fail_mode: Literal["open", "closed"] | None = None
    fallback_message: str | None = None


class PolicyConfigResponse(BaseModel):
    """Tenant policy behavior configuration plus active version."""

    tenant_id: UUID
    active_policy_version: int
    injection_protection: bool
    injection_sensitivity: str
    pii_redaction: bool
    policy_enforcement: bool
    fail_mode: str
    fallback_message: str
