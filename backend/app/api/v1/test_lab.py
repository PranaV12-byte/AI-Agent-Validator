"""Tenant-scoped synthetic Test Lab and audit decision feedback endpoints."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.database import MANUAL_COMMIT_REQUEST_STATE_KEY, get_db
from app.dependencies import get_current_tenant
from app.models.audit_log import AuditLog
from app.models.safety_config import SafetyConfig
from app.models.test_lab import DecisionFeedback, TestCase
from app.models.tenant import Tenant
from app.schemas.test_lab import (
    ExpectedAction,
    FeedbackResponse,
    FeedbackUpsert,
    TestCaseCreate,
    TestCaseListResponse,
    TestCaseResponse,
    TestCaseUpdate,
    TestRunOutcome,
    TestRunRequest,
    TestRunResponse,
)
from app.services.guardrails.audit_safety import (
    contains_recognized_secret,
    sanitize_audit_metadata,
    sanitize_text_for_external_judge,
)
from app.services.guardrails.pipeline import (
    GuardrailConfigSnapshot,
    GuardrailEvaluation,
    GuardrailSnapshot,
    evaluate_guardrails,
    load_guardrail_snapshot,
)

async def _mark_manual_commits(request: Request) -> None:
    setattr(request.state, MANUAL_COMMIT_REQUEST_STATE_KEY, True)


class _SafeValidationRoute(APIRoute):
    """Prevent FastAPI validation responses from echoing untrusted request data."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={"detail": "Invalid request"})

        return safe_handler


router = APIRouter(
    prefix="/test-lab",
    tags=["Test Lab"],
    route_class=_SafeValidationRoute,
    dependencies=[Depends(_mark_manual_commits)],
)
feedback_router = APIRouter(
    prefix="/audit",
    tags=["Audit Logs"],
    route_class=_SafeValidationRoute,
    dependencies=[Depends(_mark_manual_commits)],
)

CASE_LIMIT = 20
MAX_PROMPT_CHARS = 4000
MAX_NAME_CHARS = 120
MAX_NOTE_CHARS = 500
RUN_RATE_LIMIT = 6
RUN_RATE_WINDOW_SECONDS = 60
RUN_DEADLINE_SECONDS = 12
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RUN_RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


@dataclass(frozen=True)
class _RunCaseSnapshot:
    """Primitive case values frozen before any asynchronous evaluation starts."""

    id: UUID
    revision: int
    prompt: str
    expected_action: ExpectedAction


def _safe_error(detail: str, code: int = 422) -> HTTPException:
    """Build a validation error whose body never contains submitted text."""
    return HTTPException(status_code=code, detail=detail)


async def _commit_changes(db: AsyncSession) -> bool:
    """Commit before returning success; manual routes skip get_db's teardown commit."""
    try:
        await db.commit()
        return True
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return False


def _validated_case_fields(payload: TestCaseCreate | TestCaseUpdate) -> tuple[str, str, ExpectedAction]:
    if (
        not isinstance(payload.name, str)
        or not isinstance(payload.prompt, str)
        or not isinstance(payload.expected_action, str)
    ):
        raise _safe_error("Enter a valid name, prompt, and expected action.")
    name = payload.name.strip()
    prompt = payload.prompt.strip()
    if not name or len(name) > MAX_NAME_CHARS:
        raise _safe_error("Name must contain 1 to 120 characters.")
    if not prompt or len(prompt) > MAX_PROMPT_CHARS:
        raise _safe_error("Prompt must contain 1 to 4,000 characters.")
    if payload.expected_action not in ("allow", "redact", "block"):
        raise _safe_error("Choose allow, redact, or block as the expected action.")
    if payload.synthetic_data_acknowledged is not True:
        raise _safe_error("Confirm that the test prompt uses synthetic data.")
    if contains_recognized_secret(prompt):
        raise _safe_error("Remove credential-like text before saving this prompt.")
    return name, prompt, payload.expected_action  # type: ignore[return-value]


def _sanitize_required_text(value: str, *, max_length: int, label: str) -> str:
    safe = sanitize_audit_metadata(value, max_length=max_length)
    if safe is None:
        raise _safe_error(f"Could not safely store {label}.")
    safe = _CONTROL_CHARS.sub("", safe).strip()
    if not safe:
        raise _safe_error(f"Enter a valid {label}.")
    return safe


def _sanitize_note(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_NOTE_CHARS:
        raise _safe_error("Review note must contain at most 500 characters.")
    note = value.strip()
    if not note:
        return None
    return _sanitize_required_text(note, max_length=MAX_NOTE_CHARS, label="review note")


async def _current_snapshot(
    db: AsyncSession,
    tenant: Tenant,
) -> tuple[SafetyConfig | None, GuardrailSnapshot | None]:
    config_result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant.id)
    )
    config = config_result.scalar_one_or_none()
    if config is None:
        return None, None
    snapshot = await load_guardrail_snapshot(
        db,
        tenant.id,
        tenant.active_policy_version,
        GuardrailConfigSnapshot.from_config(config),
    )
    return config, snapshot


def _case_response(case: TestCase, snapshot_hash: str | None) -> TestCaseResponse:
    response = TestCaseResponse.model_validate(case)
    result = response.last_result
    if result is None:
        return response
    stale = result.case_revision != case.revision
    if result.snapshot_hash is not None and result.snapshot_hash != snapshot_hash:
        stale = True
    if result.snapshot_hash is not None and snapshot_hash is None:
        stale = True
    if stale and result.status != "stale":
        response = response.model_copy(
            update={"last_result": result.model_copy(update={"status": "stale"})}
        )
    return response


@router.get("/cases", response_model=TestCaseListResponse)
async def list_test_cases(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TestCaseListResponse:
    cases_result = await db.execute(
        select(TestCase)
        .where(TestCase.tenant_id == tenant.id)
        .order_by(TestCase.created_at.desc(), TestCase.id)
    )
    cases = cases_result.scalars().all()
    _, snapshot = await _current_snapshot(db, tenant)
    snapshot_hash = snapshot.policy_snapshot_hash if snapshot is not None else None
    return TestCaseListResponse(
        cases=[_case_response(case, snapshot_hash) for case in cases],
        limit=CASE_LIMIT,
    )


async def _create_case(
    payload: TestCaseCreate,
    *,
    tenant: Tenant,
    db: AsyncSession,
    source_feedback_id: UUID | None = None,
) -> TestCaseResponse:
    name, prompt, expected_action = _validated_case_fields(payload)
    safe_name = _sanitize_required_text(name, max_length=MAX_NAME_CHARS, label="name")
    if source_feedback_id is not None:
        feedback_result = await db.execute(
            select(DecisionFeedback.id).where(
                DecisionFeedback.id == source_feedback_id,
                DecisionFeedback.tenant_id == tenant.id,
            )
        )
        if feedback_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Review not found")

    # Serialize tenant creates so simultaneous requests cannot pass the cap.
    locked_tenant = await db.execute(
        select(Tenant.id)
        .where(Tenant.id == tenant.id)
        .with_for_update()
    )
    if locked_tenant.scalar_one_or_none() is None:
        raise HTTPException(status_code=401, detail="Tenant is unavailable")
    count_result = await db.execute(
        select(func.count()).select_from(TestCase).where(TestCase.tenant_id == tenant.id)
    )
    if count_result.scalar_one() >= CASE_LIMIT:
        raise HTTPException(status_code=409, detail="Test Lab is limited to 20 saved cases")

    case = TestCase(
        tenant_id=tenant.id,
        source_feedback_id=source_feedback_id,
        name=safe_name,
        prompt=prompt,
        expected_action=expected_action,
        synthetic_data_acknowledged=True,
    )
    db.add(case)
    await db.flush()
    await db.refresh(case)
    if not await _commit_changes(db):
        raise HTTPException(status_code=503, detail="Could not save the test case")
    return _case_response(case, None)


@router.post(
    "/cases",
    response_model=TestCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_case(
    payload: TestCaseCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TestCaseResponse:
    return await _create_case(payload, tenant=tenant, db=db)


@router.post(
    "/feedback/{feedback_id}/cases",
    response_model=TestCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_case_from_feedback(
    feedback_id: UUID,
    payload: TestCaseCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TestCaseResponse:
    """Persist only the prompt manually entered in the synthetic test editor."""
    return await _create_case(
        payload,
        tenant=tenant,
        db=db,
        source_feedback_id=feedback_id,
    )


@router.put("/cases/{case_id}", response_model=TestCaseResponse)
async def update_test_case(
    case_id: UUID,
    payload: TestCaseUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TestCaseResponse:
    name, prompt, expected_action = _validated_case_fields(payload)
    safe_name = _sanitize_required_text(name, max_length=MAX_NAME_CHARS, label="name")
    result = await db.execute(
        update(TestCase)
        .where(
            TestCase.id == case_id,
            TestCase.tenant_id == tenant.id,
            TestCase.revision == payload.revision,
        )
        .values(
            name=safe_name,
            prompt=prompt,
            expected_action=expected_action,
            synthetic_data_acknowledged=True,
            revision=payload.revision + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        current_result = await db.execute(
            select(TestCase.revision).where(
                TestCase.id == case_id,
                TestCase.tenant_id == tenant.id,
            )
        )
        if current_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Test case not found")
        raise HTTPException(status_code=409, detail="Test case changed. Reload before saving.")
    case_result = await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.tenant_id == tenant.id)
    )
    case = case_result.scalar_one()
    if not await _commit_changes(db):
        raise HTTPException(status_code=503, detail="Could not save the test case")
    return _case_response(case, None)


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test_case(
    case_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(TestCase).where(TestCase.id == case_id, TestCase.tenant_id == tenant.id)
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    await db.delete(case)
    if not await _commit_changes(db):
        raise HTTPException(status_code=503, detail="Could not delete the test case")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _enforce_run_rate_limit(tenant_id: UUID) -> None:
    bucket = int(time.time() // RUN_RATE_WINDOW_SECONDS)
    key = f"test-lab:run:{tenant_id}:{bucket}"
    try:
        redis = await get_redis()
        current = int(
            await redis.eval(
                _RUN_RATE_SCRIPT,
                1,
                key,
                RUN_RATE_WINDOW_SECONDS * 2,
            )
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Test runs are temporarily unavailable",
        ) from exc
    if current > RUN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Test run rate limit exceeded")


def _safe_failure_codes(values: tuple[str, ...] | list[str]) -> list[str]:
    safe_codes = []
    for value in values:
        code = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value))[:80]
        if code and code not in safe_codes:
            safe_codes.append(code)
        if len(safe_codes) == 10:
            break
    return safe_codes


def _safe_result_preview(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        sanitized, _ = sanitize_text_for_external_judge(value)
    except Exception:
        return None
    return sanitized[:200]


def _evaluation_outcome(
    case: _RunCaseSnapshot,
    snapshot_hash: str | None,
    *,
    evaluation: GuardrailEvaluation | None = None,
    failure_codes: list[str] | None = None,
    status_override: str | None = None,
) -> TestRunOutcome:
    codes = list(failure_codes or [])
    observed_action: ExpectedAction | None = None
    preview = None
    redaction_counts: dict[str, int] = {}
    outcome_status: str = status_override or "unavailable"
    if evaluation is not None:
        codes.extend(evaluation.failure_codes)
        if evaluation.status == "evaluation_failed" or evaluation.failure_codes:
            outcome_status = "unavailable"
        else:
            observed_action = evaluation.action
            outcome_status = (
                "passed" if observed_action == case.expected_action else "mismatch"
            )
        preview = _safe_result_preview(evaluation.safe_text)
        redaction_counts = {
            key: min(1000, max(0, int(count)))
            for key, count in evaluation.redaction_counts.items()
            if key in {"aadhaar", "pan", "email", "phone", "upi"}
        }
    safe_codes = _safe_failure_codes(codes)
    return TestRunOutcome(
        case_id=case.id,
        case_revision=case.revision,
        status=outcome_status,  # type: ignore[arg-type]
        expected_action=case.expected_action,
        observed_action=observed_action,
        failure_codes=safe_codes,
        preview=preview,
        redaction_counts=redaction_counts,
        snapshot_hash=snapshot_hash,
        completed_at=datetime.now(timezone.utc),
    )


async def _persist_outcome(
    outcome: TestRunOutcome,
    *,
    tenant_id: UUID,
    db_session: AsyncSession,
) -> TestRunOutcome:
    try:
        async with db_session.begin_nested():
            write_result = await db_session.execute(
                update(TestCase)
                .where(
                    TestCase.id == outcome.case_id,
                    TestCase.tenant_id == tenant_id,
                    TestCase.revision == outcome.case_revision,
                )
                .values(
                    last_result={
                        "case_revision": outcome.case_revision,
                        "status": outcome.status,
                        "expected_action": outcome.expected_action,
                        "observed_action": outcome.observed_action,
                        "failure_codes": outcome.failure_codes,
                        "preview": outcome.preview,
                        "redaction_counts": outcome.redaction_counts,
                        "snapshot_hash": outcome.snapshot_hash,
                        "completed_at": outcome.completed_at.isoformat(),
                    },
                    last_run_at=outcome.completed_at,
                )
            )
    except Exception:
        return outcome.model_copy(
            update={
                "status": "unavailable",
                "observed_action": None,
                "failure_codes": ["result_persistence_failed"],
                "preview": None,
                "redaction_counts": {},
            }
        )
    if write_result.rowcount != 1:
        return outcome.model_copy(
            update={
                "status": "revision_conflict",
                "observed_action": None,
                "failure_codes": ["case_revision_changed"],
                "preview": None,
                "redaction_counts": {},
            }
        )
    return outcome


@router.post("/run", response_model=TestRunResponse)
async def run_test_cases(
    payload: TestRunRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> TestRunResponse:
    # Never touch expired ORM attributes after a deadline rollback.
    tenant_id = UUID(str(tenant.id))
    if payload.case_ids is not None and len(set(payload.case_ids)) != len(payload.case_ids):
        raise HTTPException(status_code=422, detail="Choose each test case only once")

    cases_query = select(TestCase).where(TestCase.tenant_id == tenant_id)
    if payload.case_ids is not None:
        cases_query = cases_query.where(TestCase.id.in_(payload.case_ids))
    cases_result = await db.execute(cases_query.order_by(TestCase.created_at, TestCase.id))
    cases = list(cases_result.scalars().all())
    if payload.case_ids is not None and len(cases) != len(payload.case_ids):
        raise HTTPException(status_code=404, detail="One or more test cases were not found")
    if not cases:
        return TestRunResponse(
            results=[], passed=0, mismatched=0, unavailable=0, not_run=0, revision_conflicts=0
        )

    # ORM objects can be refreshed or changed while evaluation awaits. Copy only
    # the inputs and expected outcome so every result is tied to one frozen case
    # revision, and the final conditional write can reject concurrent edits.
    run_cases = [
        _RunCaseSnapshot(
            id=case.id,
            revision=case.revision,
            prompt=case.prompt,
            expected_action=case.expected_action,
        )
        for case in cases
    ]

    await _enforce_run_rate_limit(tenant_id)
    config, snapshot = await _current_snapshot(db, tenant)
    snapshot_hash = snapshot.policy_snapshot_hash if snapshot is not None else None
    preflight_failure: str | None = None
    if config is None or snapshot is None:
        preflight_failure = "settings_unavailable"
    elif snapshot.load_error_code is not None or snapshot.policy_snapshot_hash is None:
        preflight_failure = "snapshot_unavailable"
    elif snapshot.config.policy_enforcement and any(
        policy.is_enabled and policy.rule_type == "llm_eval"
        for policy in snapshot.policies
    ):
        preflight_failure = "external_judge_required"

    outcomes: list[TestRunOutcome] = []
    if preflight_failure:
        outcomes = [
            _evaluation_outcome(
                case,
                snapshot_hash,
                failure_codes=[preflight_failure],
            )
            for case in run_cases
        ]
    else:
        assert config is not None and snapshot is not None
        deadline = time.monotonic() + RUN_DEADLINE_SECONDS
        for index, case in enumerate(run_cases):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcomes.append(
                    _evaluation_outcome(
                        case,
                        snapshot_hash,
                        failure_codes=["run_deadline_exceeded"],
                    )
                )
                for not_started in run_cases[index + 1 :]:
                    outcomes.append(
                        _evaluation_outcome(
                            not_started,
                            snapshot_hash,
                            failure_codes=["not_started_before_deadline"],
                            status_override="not_run",
                        )
                    )
                break
            try:
                async with asyncio.timeout(remaining):
                    evaluation = await evaluate_guardrails(
                        db,
                        tenant_id,
                        snapshot.policy_version,
                        config,
                        case.prompt,
                        snapshot=snapshot,
                    )
            except TimeoutError:
                # Evaluation is read-only; reset any cancelled DB transaction before
                # recording truthful unavailable/not-run outcomes below.
                await db.rollback()
                outcomes.append(
                    _evaluation_outcome(
                        case,
                        snapshot_hash,
                        failure_codes=["run_deadline_exceeded"],
                    )
                )
                for not_started in run_cases[index + 1 :]:
                    outcomes.append(
                        _evaluation_outcome(
                            not_started,
                            snapshot_hash,
                            failure_codes=["not_started_before_deadline"],
                            status_override="not_run",
                        )
                    )
                break
            except Exception:
                outcomes.append(
                    _evaluation_outcome(
                        case,
                        snapshot_hash,
                        failure_codes=["evaluation_unavailable"],
                    )
                )
            else:
                outcomes.append(_evaluation_outcome(case, snapshot_hash, evaluation=evaluation))

    persisted: list[TestRunOutcome] = []
    for outcome in outcomes:
        persisted.append(
            await _persist_outcome(outcome, tenant_id=tenant_id, db_session=db)
        )

    if not await _commit_changes(db):
        persisted = [
            outcome.model_copy(
                update={
                    "status": "unavailable",
                    "observed_action": None,
                    "failure_codes": ["result_commit_failed"],
                    "preview": None,
                    "redaction_counts": {},
                }
            )
            for outcome in persisted
        ]

    return TestRunResponse(
        results=persisted,
        passed=sum(item.status == "passed" for item in persisted),
        mismatched=sum(item.status == "mismatch" for item in persisted),
        unavailable=sum(item.status == "unavailable" for item in persisted),
        not_run=sum(item.status == "not_run" for item in persisted),
        revision_conflicts=sum(item.status == "revision_conflict" for item in persisted),
    )


def _validated_feedback(payload: FeedbackUpsert) -> tuple[str, ExpectedAction | None, str, str | None]:
    if payload.decision not in ("correct", "incorrect", "unsure"):
        raise _safe_error("Choose Correct, Incorrect, or Unsure.")
    if payload.status not in ("open", "resolved"):
        raise _safe_error("Choose Open or Resolved.")
    expected_action = payload.expected_action
    if expected_action is not None and expected_action not in ("allow", "redact", "block"):
        raise _safe_error("Choose allow, redact, or block as the expected action.")
    if payload.decision == "incorrect" and expected_action is None:
        raise _safe_error("Choose the expected action for an incorrect decision.")
    if payload.decision != "incorrect" and expected_action is not None:
        raise _safe_error("Expected action is only used for an incorrect decision.")
    note = _sanitize_note(payload.note)
    return payload.decision, expected_action, payload.status, note  # type: ignore[return-value]


@feedback_router.get("/{audit_log_id}/feedback", response_model=FeedbackResponse | None)
async def get_decision_feedback(
    audit_log_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse | None:
    audit_result = await db.execute(
        select(AuditLog.id).where(
            AuditLog.id == audit_log_id,
            AuditLog.tenant_id == tenant.id,
        )
    )
    if audit_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    feedback_result = await db.execute(
        select(DecisionFeedback).where(
            DecisionFeedback.audit_log_id == audit_log_id,
            DecisionFeedback.tenant_id == tenant.id,
        )
    )
    feedback = feedback_result.scalar_one_or_none()
    return FeedbackResponse.model_validate(feedback) if feedback else None


@feedback_router.put("/{audit_log_id}/feedback", response_model=FeedbackResponse)
async def upsert_decision_feedback(
    audit_log_id: UUID,
    payload: FeedbackUpsert,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    decision, expected_action, review_status, note = _validated_feedback(payload)
    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.id == audit_log_id, AuditLog.tenant_id == tenant.id)
        .with_for_update()
    )
    if audit_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    feedback_result = await db.execute(
        select(DecisionFeedback).where(
            DecisionFeedback.audit_log_id == audit_log_id,
            DecisionFeedback.tenant_id == tenant.id,
        )
    )
    feedback = feedback_result.scalar_one_or_none()
    if feedback is None:
        feedback = DecisionFeedback(
            tenant_id=tenant.id,
            audit_log_id=audit_log_id,
            decision=decision,
            expected_action=expected_action,
            status=review_status,
            note=note,
        )
        db.add(feedback)
    else:
        feedback.decision = decision
        feedback.expected_action = expected_action
        feedback.status = review_status
        feedback.note = note
        feedback.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(feedback)
    if not await _commit_changes(db):
        raise HTTPException(status_code=503, detail="Could not save the decision review")
    return FeedbackResponse.model_validate(feedback)
