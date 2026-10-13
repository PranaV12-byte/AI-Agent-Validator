"""Pydantic schemas for policy APIs."""

import re
import math
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
SUPPORTED_PII_TYPES = frozenset({"aadhaar", "pan", "email", "phone", "upi"})
MAX_KEYWORD_CHARS = 256
MAX_REGEX_PATTERN_CHARS = 256
MAX_LLM_RUBRIC_CHARS = 600


def validate_rule_parameters(
    rule_type: str, parameters: dict[str, Any] | None
) -> None:
    params = parameters or {}

    if rule_type == "semantic" and "threshold" in params:
        threshold = params["threshold"]
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or not 0 <= threshold <= 1
        ):
            raise ValueError("semantic threshold must be a finite number from 0 to 1")

    if rule_type == "regex_match":
        pattern = params.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(
                "regex_match requires parameters.pattern as non-empty string"
            )
        if len(pattern) > MAX_REGEX_PATTERN_CHARS:
            raise ValueError(
                f"regex_match pattern must be at most {MAX_REGEX_PATTERN_CHARS} characters"
            )
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError("regex_match pattern is invalid") from exc

    if rule_type == "llm_eval":
        rubric = params.get("rubric")
        if not isinstance(rubric, str) or not rubric.strip():
            raise ValueError("llm_eval requires parameters.rubric as non-empty string")
        if len(rubric) > MAX_LLM_RUBRIC_CHARS:
            raise ValueError(
                f"llm_eval rubric must be at most {MAX_LLM_RUBRIC_CHARS} characters"
            )

    if rule_type == "keyword":
        keyword = params.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("keyword requires parameters.keyword as non-empty string")
        if len(keyword) > MAX_KEYWORD_CHARS:
            raise ValueError(
                f"keyword must be at most {MAX_KEYWORD_CHARS} characters"
            )

    if rule_type == "pii_redaction":
        pii_types = params.get("pii_types", sorted(SUPPORTED_PII_TYPES))
        if (
            not isinstance(pii_types, list)
            or not pii_types
            or any(
                not isinstance(pii_type, str) or pii_type not in SUPPORTED_PII_TYPES
                for pii_type in pii_types
            )
        ):
            raise ValueError(
                "pii_redaction requires parameters.pii_types from the supported categories"
            )

    if rule_type == "prompt_injection":
        sensitivity = params.get("sensitivity", "moderate")
        if not isinstance(sensitivity, str) or sensitivity not in {
            "strict",
            "moderate",
            "lenient",
        }:
            raise ValueError(
                "prompt_injection sensitivity must be strict, moderate, or lenient"
            )


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
        validate_rule_parameters(self.rule_type, self.parameters)
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

        if self.rule_type is not None and "parameters" in self.model_fields_set:
            validate_rule_parameters(self.rule_type, self.parameters)
        # The current type/parameters live in the database; the CRUD adapter
        # validates the merged pair when either field is updated independently.

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

    model_config = ConfigDict(extra="forbid")

    injection_protection: bool | None = None
    injection_sensitivity: Literal["strict", "moderate", "lenient"] | None = None
    pii_redaction: bool | None = None
    policy_enforcement: bool | None = None
    fail_mode: Literal["open", "closed"] | None = None
    fallback_message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "PolicyConfigUpdate":
        null_fields = [
            name
            for name in self.model_fields_set
            if getattr(self, name) is None
        ]
        if null_fields:
            raise ValueError(
                "Fields cannot be null: " + ", ".join(sorted(null_fields))
            )
        return self


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
