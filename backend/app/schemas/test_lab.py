"""Request and response contracts for Test Lab and human decision feedback."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ExpectedAction = Literal["allow", "redact", "block"]
TestResultStatus = Literal[
    "passed",
    "mismatch",
    "unavailable",
    "not_run",
    "stale",
    "revision_conflict",
]


class TestCaseFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # These fields are checked by the route so validation errors never echo a
    # potentially sensitive prompt or note into a response body.
    name: Any
    prompt: Any
    expected_action: Any
    synthetic_data_acknowledged: Any


class TestCaseCreate(TestCaseFields):
    pass


class TestCaseUpdate(TestCaseFields):
    revision: int = Field(ge=1)


class TestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_revision: int
    status: TestResultStatus
    expected_action: ExpectedAction
    observed_action: ExpectedAction | None = None
    failure_codes: list[str] = Field(default_factory=list)
    preview: str | None = None
    redaction_counts: dict[str, int] = Field(default_factory=dict)
    snapshot_hash: str | None = None
    completed_at: datetime


class TestCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    prompt: str
    expected_action: ExpectedAction
    synthetic_data_acknowledged: bool
    revision: int
    source_feedback_id: UUID | None
    last_result: TestResult | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TestCaseListResponse(BaseModel):
    cases: list[TestCaseResponse]
    limit: int = 20


class TestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20)


class TestRunOutcome(BaseModel):
    case_id: UUID
    case_revision: int
    status: TestResultStatus
    expected_action: ExpectedAction
    observed_action: ExpectedAction | None = None
    failure_codes: list[str] = Field(default_factory=list)
    preview: str | None = None
    redaction_counts: dict[str, int] = Field(default_factory=dict)
    snapshot_hash: str | None = None
    completed_at: datetime


class TestRunResponse(BaseModel):
    results: list[TestRunOutcome]
    passed: int
    mismatched: int
    unavailable: int
    not_run: int
    revision_conflicts: int


class FeedbackUpsert(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Route-level validation keeps invalid note content out of HTTP error bodies.
    decision: Any
    expected_action: Any = None
    status: Any = "open"
    note: Any = None


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    audit_log_id: UUID
    decision: Literal["correct", "incorrect", "unsure"]
    expected_action: ExpectedAction | None
    status: Literal["open", "resolved"]
    note: str | None
    created_at: datetime
    updated_at: datetime
