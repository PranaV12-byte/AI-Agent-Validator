"""Partial safety-config payload validation without database access."""

import pytest
from pydantic import ValidationError

from app.schemas.dashboard import SafetyConfigUpdate
from app.schemas.policies import PolicyConfigUpdate


def test_safety_config_partial_update_keeps_omitted_fields_unset() -> None:
    update = SafetyConfigUpdate(injection_protection=False)

    assert update.model_dump(exclude_unset=True) == {"injection_protection": False}


@pytest.mark.parametrize(
    "field",
    [
        "global_block_enabled",
        "injection_protection",
        "injection_sensitivity",
        "pii_redaction",
        "pii_types",
        "policy_enforcement",
        "fail_mode",
        "fallback_message",
        "log_retention_days",
    ],
)
def test_safety_config_rejects_explicit_null(field: str) -> None:
    with pytest.raises(ValidationError):
        SafetyConfigUpdate.model_validate({field: None})


@pytest.mark.parametrize(
    "payload",
    [
        {"injection_sensitivity": "unknown"},
        {"fail_mode": "sometimes"},
        {"pii_types": ["ssn"]},
        {"log_retention_days": 0},
        {"unexpected": True},
    ],
)
def test_safety_config_rejects_unsupported_values(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SafetyConfigUpdate.model_validate(payload)


def test_policy_config_partial_update_keeps_omitted_fields_unset() -> None:
    update = PolicyConfigUpdate(injection_protection=False)

    assert update.model_dump(exclude_unset=True) == {"injection_protection": False}


@pytest.mark.parametrize(
    "field",
    [
        "injection_protection",
        "injection_sensitivity",
        "pii_redaction",
        "policy_enforcement",
        "fail_mode",
        "fallback_message",
    ],
)
def test_policy_and_dashboard_config_reject_null_on_shared_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        SafetyConfigUpdate.model_validate({field: None})
    with pytest.raises(ValidationError):
        PolicyConfigUpdate.model_validate({field: None})


@pytest.mark.parametrize(
    "payload",
    [
        {"fallback_message": "x" * 2001},
        {"unexpected": True},
    ],
)
def test_policy_config_rejects_oversized_or_unknown_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PolicyConfigUpdate.model_validate(payload)
