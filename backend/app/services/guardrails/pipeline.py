"""Shared, fail-explicit guardrail evaluation for SDK and demo routes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.safety_config import SafetyConfig
from app.services.guardrails import injection_detector, pii_redactor, policy_engine
from app.services.guardrails.policy_snapshot import (
    PolicyRuleSnapshot,
    load_behavior_snapshot,
)

logger = structlog.get_logger()

EvaluationStatus = Literal["allowed", "redacted", "blocked", "evaluation_failed"]


@dataclass(frozen=True)
class GuardrailConfigSnapshot:
    global_block_enabled: bool
    injection_protection: bool
    injection_sensitivity: str
    pii_redaction: bool
    pii_types: tuple[str, ...]
    policy_enforcement: bool
    fail_mode: Literal["open", "closed"]
    fallback_message: str

    @classmethod
    def from_config(cls, config: SafetyConfig) -> "GuardrailConfigSnapshot":
        fail_mode: Literal["open", "closed"] = (
            "open" if config.fail_mode == "open" else "closed"
        )
        return cls(
            global_block_enabled=bool(config.global_block_enabled),
            injection_protection=bool(config.injection_protection),
            injection_sensitivity=str(config.injection_sensitivity),
            pii_redaction=bool(config.pii_redaction),
            pii_types=tuple(sorted(config.pii_types or [])),
            policy_enforcement=bool(config.policy_enforcement),
            fail_mode=fail_mode,
            fallback_message=str(config.fallback_message),
        )

    @classmethod
    def from_values(cls, values: dict[str, Any]) -> "GuardrailConfigSnapshot":
        fail_mode: Literal["open", "closed"] = (
            "open" if values["fail_mode"] == "open" else "closed"
        )
        return cls(
            global_block_enabled=bool(values["global_block_enabled"]),
            injection_protection=bool(values["injection_protection"]),
            injection_sensitivity=str(values["injection_sensitivity"]),
            pii_redaction=bool(values["pii_redaction"]),
            pii_types=tuple(sorted(values["pii_types"] or [])),
            policy_enforcement=bool(values["policy_enforcement"]),
            fail_mode=fail_mode,
            fallback_message=str(values["fallback_message"]),
        )

    def as_hash_record(self) -> dict[str, Any]:
        return {
            "global_block_enabled": self.global_block_enabled,
            "injection_protection": self.injection_protection,
            "injection_sensitivity": self.injection_sensitivity,
            "pii_redaction": self.pii_redaction,
            "pii_types": list(self.pii_types),
            "policy_enforcement": self.policy_enforcement,
            "fail_mode": self.fail_mode,
            "fallback_message": self.fallback_message,
        }


@dataclass(frozen=True)
class GuardrailSnapshot:
    policy_version: int
    config: GuardrailConfigSnapshot
    policies: tuple[PolicyRuleSnapshot, ...]
    policy_snapshot_hash: str | None
    load_error_code: str | None = None


@dataclass(frozen=True)
class GuardrailEvaluation:
    status: EvaluationStatus
    safe_text: str | None
    reason: str
    violations: tuple[dict[str, Any], ...]
    error_code: str | None
    failure_codes: tuple[str, ...]
    policy_version: int
    policy_snapshot_hash: str | None
    fail_mode: Literal["open", "closed"]
    fallback_message: str
    redaction_counts: dict[str, int]

    @property
    def action(self) -> Literal["allow", "redact", "block"]:
        if self.status == "blocked":
            return "block"
        if self.status == "redacted":
            return "redact"
        if self.status == "evaluation_failed":
            if self.fail_mode == "closed" or self.safe_text is None:
                return "block"
            return "redact" if self.redaction_counts else "allow"
        return "allow"


def _snapshot_hash(
    policy_version: int,
    config: GuardrailConfigSnapshot,
    policies: tuple[PolicyRuleSnapshot, ...],
) -> str:
    snapshot = {
        "tenant_policy_version": policy_version,
        "settings": config.as_hash_record(),
        "policies": [policy.as_hash_record() for policy in policies],
    }
    canonical = json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log_evaluator_failure(tenant_id: UUID, error_code: str, exc: Exception) -> None:
    logger.error(
        "guardrail_evaluation_failed",
        tenant_id=str(tenant_id),
        error_code=error_code,
        exception_type=type(exc).__name__,
    )


async def load_guardrail_snapshot(
    db: AsyncSession,
    tenant_id: UUID,
    policy_version: int,
    config: GuardrailConfigSnapshot,
) -> GuardrailSnapshot:
    """Capture immutable settings and rules for one or more related checks."""
    try:
        # The savepoint contains any SQL failure without expiring the ORM
        # tenant/config objects loaded earlier in this request.
        async with db.begin_nested():
            behavior = await load_behavior_snapshot(db, tenant_id)
        frozen_config = (
            GuardrailConfigSnapshot.from_values(behavior.config_values)
            if behavior.config_values is not None
            else config
        )
        digest = _snapshot_hash(
            behavior.active_policy_version,
            frozen_config,
            behavior.policies,
        )
        return GuardrailSnapshot(
            behavior.active_policy_version,
            frozen_config,
            behavior.policies,
            digest,
        )
    except Exception as exc:
        logger.warning(
            "behavior_snapshot_unavailable",
            tenant_id=str(tenant_id),
            exception_type=type(exc).__name__,
        )
        return GuardrailSnapshot(
            policy_version,
            config,
            (),
            None,
            "behavior_snapshot_unavailable",
        )


def _result(
    *,
    status: EvaluationStatus,
    safe_text: str | None,
    reason: str,
    violations: list[dict[str, Any]],
    failure_codes: list[str],
    policy_version: int,
    snapshot_hash: str | None,
    fail_mode: Literal["open", "closed"],
    fallback_message: str,
    redaction_counts: dict[str, int],
) -> GuardrailEvaluation:
    return GuardrailEvaluation(
        status=status,
        safe_text=safe_text,
        reason=reason,
        violations=tuple(violations),
        error_code=failure_codes[0] if failure_codes else None,
        failure_codes=tuple(failure_codes),
        policy_version=policy_version,
        policy_snapshot_hash=snapshot_hash,
        fail_mode=fail_mode,
        fallback_message=fallback_message,
        redaction_counts=dict(redaction_counts),
    )


async def evaluate_guardrails(
    db: AsyncSession,
    tenant_id: UUID,
    policy_version: int,
    config: SafetyConfig,
    message: str,
    *,
    force_fail_closed: bool = False,
    snapshot: GuardrailSnapshot | None = None,
) -> GuardrailEvaluation:
    """Evaluate one immutable settings/rules snapshot and preserve safe text.

    Affirmative blocking findings always win. Evaluator failures are accumulated
    so a broken injection classifier does not skip working PII redaction or a
    usable policy evaluator. `fail_mode=open` may permit only text whose
    configured PII checks completed; it never forwards the original text after
    an enabled redactor failed.
    """
    if snapshot is None:
        frozen_config = GuardrailConfigSnapshot.from_config(config)
        if frozen_config.global_block_enabled:
            return _result(
                status="blocked",
                safe_text=None,
                reason="Global block is enabled.",
                violations=[{"type": "global_block", "severity": "critical"}],
                failure_codes=[],
                policy_version=policy_version,
                snapshot_hash=None,
                fail_mode=(
                    "closed" if force_fail_closed else frozen_config.fail_mode
                ),
                fallback_message=frozen_config.fallback_message,
                redaction_counts={},
            )
        snapshot = await load_guardrail_snapshot(
            db, tenant_id, policy_version, frozen_config
        )
    frozen_config = snapshot.config
    policy_version = snapshot.policy_version
    fail_mode: Literal["open", "closed"] = (
        "closed" if force_fail_closed else frozen_config.fail_mode
    )
    violations: list[dict[str, Any]] = []
    failure_codes: list[str] = []
    redaction_counts: dict[str, int] = {}

    if frozen_config.global_block_enabled:
        return _result(
            status="blocked",
            safe_text=None,
            reason="Global block is enabled.",
            violations=[{"type": "global_block", "severity": "critical"}],
            failure_codes=[],
            policy_version=policy_version,
            snapshot_hash=snapshot.policy_snapshot_hash,
            fail_mode=fail_mode,
            fallback_message=frozen_config.fallback_message,
            redaction_counts={},
        )

    policies = snapshot.policies
    snapshot_hash = snapshot.policy_snapshot_hash
    policy_snapshot_loaded = snapshot.load_error_code is None
    if snapshot.load_error_code:
        failure_codes.append(snapshot.load_error_code)

    # No check can overturn a positive injection result, but failures from
    # snapshot acquisition are retained for the audit record.
    if frozen_config.injection_protection:
        try:
            injection = await run_in_threadpool(
                injection_detector.detect_full_text,
                message,
                frozen_config.injection_sensitivity,
            )
            if injection.is_injection:
                violations.append(
                    {
                        "type": "prompt_injection",
                        "severity": "critical",
                        "confidence": float(injection.confidence),
                        "method": injection.method,
                    }
                )
                return _result(
                    status="blocked",
                    safe_text=None,
                    reason="Prompt injection was detected.",
                    violations=violations,
                    failure_codes=failure_codes,
                    policy_version=policy_version,
                    snapshot_hash=snapshot_hash,
                    fail_mode=fail_mode,
                    fallback_message=frozen_config.fallback_message,
                    redaction_counts={},
                )
            if not injection.complete:
                code = "injection_detector_unavailable"
                _log_evaluator_failure(
                    tenant_id, code, RuntimeError("classifier_not_loaded")
                )
                failure_codes.append(code)
        except Exception as exc:
            _log_evaluator_failure(tenant_id, "injection_evaluation_failed", exc)
            failure_codes.append("injection_evaluation_failed")

    safe_text: str | None = message if not frozen_config.pii_redaction else None
    if frozen_config.pii_redaction:
        try:
            redaction = await run_in_threadpool(
                pii_redactor.redact,
                message,
                list(frozen_config.pii_types),
            )
            safe_text = redaction.sanitized_text
            for item in redaction.redactions:
                redaction_counts[item.type] = redaction_counts.get(item.type, 0) + 1
            if redaction_counts:
                violations.append(
                    {
                        "type": "pii_detected",
                        "severity": "high",
                        "redaction_counts": dict(redaction_counts),
                    }
                )
        except Exception as exc:
            safe_text = None
            _log_evaluator_failure(tenant_id, "pii_evaluation_failed", exc)
            failure_codes.append("pii_evaluation_failed")

    if frozen_config.policy_enforcement:
        if not policy_snapshot_loaded:
            # Snapshot failure already explains why policy checks cannot run.
            pass
        elif safe_text is None:
            code = "policy_evaluation_skipped_unsafe_input"
            _log_evaluator_failure(
                tenant_id, code, RuntimeError("safe_input_unavailable")
            )
            failure_codes.append(code)
        else:
            active_policies = tuple(policy for policy in policies if policy.is_enabled)
            if active_policies:
                try:
                    policy_result = await policy_engine.check_message(
                        db,
                        tenant_id,
                        safe_text,
                        policy_snapshot=active_policies,
                        fail_closed=fail_mode == "closed",
                        prior_evaluator_failure=bool(failure_codes),
                    )
                    for code in getattr(policy_result, "error_codes", ()):
                        if code not in failure_codes:
                            _log_evaluator_failure(
                                tenant_id,
                                code,
                                RuntimeError("policy_rule_evaluation_incomplete"),
                            )
                            failure_codes.append(code)
                    if hasattr(policy_result, "safe_text"):
                        safe_text = policy_result.safe_text
                    for pii_type, count in getattr(
                        policy_result,
                        "redaction_counts",
                        {},
                    ).items():
                        redaction_counts[pii_type] = (
                            redaction_counts.get(pii_type, 0) + count
                        )
                    if getattr(policy_result, "redaction_counts", {}):
                        pii_finding = next(
                            (
                                finding
                                for finding in violations
                                if finding["type"] == "pii_detected"
                            ),
                            None,
                        )
                        if pii_finding is None:
                            violations.append(
                                {
                                    "type": "pii_detected",
                                    "severity": "high",
                                    "redaction_counts": dict(redaction_counts),
                                }
                            )
                        else:
                            pii_finding["redaction_counts"] = dict(redaction_counts)
                    if policy_result.violated:
                        for match in policy_result.matched_policies:
                            finding = {
                                "type": "policy_violation",
                                "severity": "high",
                                "policy_id": match.policy_id,
                                "policy_type": getattr(
                                    match,
                                    "rule_type",
                                    "semantic",
                                ),
                            }
                            similarity = getattr(match, "similarity_score", None)
                            if similarity is not None:
                                finding["similarity"] = float(similarity)
                            violations.append(finding)
                    if getattr(policy_result, "block_on_error", False):
                        # An incomplete evaluator is not an affirmative rule
                        # violation. Keep it distinct so callers and dashboards
                        # can report an error, while refusing to forward text
                        # even when the tenant's ordinary mode is fail-open.
                        if not failure_codes:
                            code = "policy_evaluation_uncertain"
                            _log_evaluator_failure(
                                tenant_id,
                                code,
                                RuntimeError("policy_evaluation_incomplete"),
                            )
                            failure_codes.append(code)
                        safe_text = None
                except Exception as exc:
                    _log_evaluator_failure(
                        tenant_id, "policy_evaluation_failed", exc
                    )
                    failure_codes.append("policy_evaluation_failed")

    if any(
        finding["type"]
        in (
            "prompt_injection",
            "policy_violation",
        )
        for finding in violations
    ):
        reason = (
            "Prompt injection was detected."
            if any(finding["type"] == "prompt_injection" for finding in violations)
            else (
                "A configured policy was violated."
                if any(
                    finding["type"] == "policy_violation"
                    for finding in violations
                )
                else "A configured policy was violated."
            )
        )
        return _result(
            status="blocked",
            safe_text=None,
            reason=reason,
            violations=violations,
            failure_codes=failure_codes,
            policy_version=policy_version,
            snapshot_hash=snapshot_hash,
            fail_mode=fail_mode,
            fallback_message=frozen_config.fallback_message,
            redaction_counts=redaction_counts,
        )

    if failure_codes:
        return _result(
            status="evaluation_failed",
            safe_text=safe_text,
            reason="One or more enabled safety checks could not be completed.",
            violations=violations,
            failure_codes=failure_codes,
            policy_version=policy_version,
            snapshot_hash=snapshot_hash,
            fail_mode=fail_mode,
            fallback_message=frozen_config.fallback_message,
            redaction_counts=redaction_counts,
        )

    if redaction_counts:
        return _result(
            status="redacted",
            safe_text=safe_text,
            reason="Sensitive information was redacted.",
            violations=violations,
            failure_codes=[],
            policy_version=policy_version,
            snapshot_hash=snapshot_hash,
            fail_mode=fail_mode,
            fallback_message=frozen_config.fallback_message,
            redaction_counts=redaction_counts,
        )

    checks_enabled = (
        frozen_config.injection_protection
        or frozen_config.pii_redaction
        or frozen_config.policy_enforcement
    )
    return _result(
        status="allowed",
        safe_text=safe_text,
        reason=(
            "All enabled checks passed."
            if checks_enabled
            else "No safety checks are enabled."
        ),
        violations=violations,
        failure_codes=[],
        policy_version=policy_version,
        snapshot_hash=snapshot_hash,
        fail_mode=fail_mode,
        fallback_message=frozen_config.fallback_message,
        redaction_counts={},
    )
