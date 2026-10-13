"""Protected demo-chat orchestration over one immutable safety snapshot."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal
from time import monotonic, perf_counter
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.safety_config import SafetyConfig
from app.services.guardrails.groq_client import GroqClient, GroqProviderError, groq_client
from app.services.guardrails.pipeline import (
    GuardrailConfigSnapshot,
    GuardrailEvaluation,
    GuardrailSnapshot,
    evaluate_guardrails,
    load_guardrail_snapshot,
)

PROTECTED_CHAT_WORK_TIMEOUT_SECONDS = 75.0
PROTECTED_CHAT_AUDIT_WRITE_TIMEOUT_SECONDS = 2.0


ChatStatus = Literal[
    "allowed",
    "redacted",
    "blocked",
    "evaluation_failed",
    "provider_unavailable",
    "service_unavailable",
    "busy",
]


@dataclass(frozen=True)
class ProtectedChatOutcome:
    status: ChatStatus
    answer: str | None
    fallback_message: str | None
    error_code: str | None
    input_redacted: bool
    output_redacted: bool
    policy_version: int
    snapshot_hash: str | None
    evaluations: tuple[GuardrailEvaluation, ...]
    provider_calls: int


AuditWriter = Callable[
    [str, str, GuardrailEvaluation | None, str | None, GuardrailSnapshot, int],
    Awaitable[UUID],
]


def _default_config() -> GuardrailConfigSnapshot:
    # Match SafetyConfig defaults without relying on SQLAlchemy's deferred
    # column defaults, which are not populated on a transient instance.
    return GuardrailConfigSnapshot(
        global_block_enabled=False,
        injection_protection=True,
        injection_sensitivity="moderate",
        pii_redaction=True,
        pii_types=("aadhaar", "email", "pan", "phone", "upi"),
        policy_enforcement=True,
        fail_mode="closed",
        fallback_message="I cannot help with that request. A human agent will follow up.",
    )


def _fallback(evaluation: GuardrailEvaluation) -> str:
    return evaluation.fallback_message


async def run_protected_chat(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    tenant_policy_version: int,
    message: str,
    write_audit: AuditWriter,
    client: GroqClient = groq_client,
) -> ProtectedChatOutcome:
    """Run pre-check, one generation, and post-check with mandatory audits.

    The callback commits each audit row. In particular, the pre-check must be
    durable before any provider request, and a post-check must be durable before
    returning generated text to the browser.
    """
    work_deadline = monotonic() + PROTECTED_CHAT_WORK_TIMEOUT_SECONDS
    default_config = _default_config()

    async def within_work_budget(awaitable):
        remaining = work_deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("protected_chat_deadline_exceeded")
        async with asyncio.timeout(remaining):
            return await awaitable

    async def write_audit_with_bound(*args):
        async with asyncio.timeout(PROTECTED_CHAT_AUDIT_WRITE_TIMEOUT_SECONDS):
            return await write_audit(*args)

    try:
        snapshot = await within_work_budget(
            load_guardrail_snapshot(
                db,
                tenant_id,
                tenant_policy_version,
                default_config,
            )
        )
    except TimeoutError:
        snapshot = GuardrailSnapshot(
            tenant_policy_version,
            default_config,
            (),
            None,
            "protected_chat_deadline_exceeded",
        )
    evaluations: list[GuardrailEvaluation] = []
    provider_calls = 0

    pre_started = perf_counter()
    try:
        pre = await within_work_budget(
            evaluate_guardrails(
                db,
                tenant_id,
                tenant_policy_version,
                SafetyConfig(tenant_id=tenant_id),
                message,
                force_fail_closed=True,
                snapshot=snapshot,
            )
        )
    except TimeoutError:
        pre = GuardrailEvaluation(
            status="evaluation_failed",
            safe_text=None,
            reason="The protected request exceeded its safety deadline.",
            violations=(),
            error_code="protected_chat_deadline_exceeded",
            failure_codes=("protected_chat_deadline_exceeded",),
            policy_version=snapshot.policy_version,
            policy_snapshot_hash=snapshot.policy_snapshot_hash,
            fail_mode="closed",
            fallback_message=snapshot.config.fallback_message,
            redaction_counts={},
        )
    except Exception:
        # Keep an unexpected engine defect explicit and non-forwarding.
        pre = GuardrailEvaluation(
            status="evaluation_failed",
            safe_text=None,
            reason="A safety check could not be completed.",
            violations=(),
            error_code="guardrail_evaluation_failed",
            failure_codes=("guardrail_evaluation_failed",),
            policy_version=snapshot.policy_version,
            policy_snapshot_hash=snapshot.policy_snapshot_hash,
            fail_mode="closed",
            fallback_message=snapshot.config.fallback_message,
            redaction_counts={},
        )
    evaluations.append(pre)
    pre_ms = max(0, int((perf_counter() - pre_started) * 1000))

    try:
        await write_audit_with_bound(
            "pre",
            message,
            pre,
            None,
            snapshot,
            pre_ms,
        )
    except Exception:
        return ProtectedChatOutcome(
            "service_unavailable",
            None,
            _fallback(pre),
            "audit_unavailable",
            bool(pre.redaction_counts),
            False,
            snapshot.policy_version,
            snapshot.policy_snapshot_hash,
            tuple(evaluations),
            provider_calls,
        )

    if pre.status == "blocked":
        return ProtectedChatOutcome(
            "blocked", None, _fallback(pre), None,
            bool(pre.redaction_counts), False,
            snapshot.policy_version, snapshot.policy_snapshot_hash,
            tuple(evaluations), provider_calls,
        )
    if pre.status == "evaluation_failed" or pre.safe_text is None:
        return ProtectedChatOutcome(
            "evaluation_failed", None, _fallback(pre),
            pre.error_code or "guardrail_evaluation_failed",
            bool(pre.redaction_counts), False,
            snapshot.policy_version, snapshot.policy_snapshot_hash,
            tuple(evaluations), provider_calls,
        )

    generation_started = perf_counter()
    try:
        remaining = work_deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("protected_chat_deadline_exceeded")
        provider_calls += 1
        async with asyncio.timeout(remaining):
            generated = await client.complete(pre.safe_text)
    except GroqProviderError as exc:
        code = exc.code
        generation_ms = max(0, int((perf_counter() - generation_started) * 1000))
        try:
            await write_audit_with_bound(
                "generation", pre.safe_text, None, code, snapshot, generation_ms
            )
        except Exception:
            return ProtectedChatOutcome(
                "service_unavailable", None, _fallback(pre), "audit_unavailable",
                bool(pre.redaction_counts), False, snapshot.policy_version,
                snapshot.policy_snapshot_hash, tuple(evaluations), provider_calls,
            )
        return ProtectedChatOutcome(
            "provider_unavailable", None, _fallback(pre), code,
            bool(pre.redaction_counts), False, snapshot.policy_version,
            snapshot.policy_snapshot_hash, tuple(evaluations), provider_calls,
        )
    except TimeoutError:
        code = "protected_chat_deadline_exceeded"
        generation_ms = max(0, int((perf_counter() - generation_started) * 1000))
        try:
            await write_audit_with_bound(
                "generation", pre.safe_text, None, code, snapshot, generation_ms
            )
        except Exception:
            return ProtectedChatOutcome(
                "service_unavailable", None, _fallback(pre), "audit_unavailable",
                bool(pre.redaction_counts), False, snapshot.policy_version,
                snapshot.policy_snapshot_hash, tuple(evaluations), provider_calls,
            )
        return ProtectedChatOutcome(
            "provider_unavailable", None, _fallback(pre), code,
            bool(pre.redaction_counts), False, snapshot.policy_version,
            snapshot.policy_snapshot_hash, tuple(evaluations), provider_calls,
        )
    except Exception:
        code = "groq_client_error"
        generation_ms = max(0, int((perf_counter() - generation_started) * 1000))
        try:
            await write_audit_with_bound(
                "generation", pre.safe_text, None, code, snapshot, generation_ms
            )
        except Exception:
            return ProtectedChatOutcome(
                "service_unavailable", None, _fallback(pre), "audit_unavailable",
                bool(pre.redaction_counts), False, snapshot.policy_version,
                snapshot.policy_snapshot_hash, tuple(evaluations), provider_calls,
            )
        return ProtectedChatOutcome(
            "provider_unavailable", None, _fallback(pre), code,
            bool(pre.redaction_counts), False, snapshot.policy_version,
            snapshot.policy_snapshot_hash, tuple(evaluations), provider_calls,
        )

    post_started = perf_counter()
    try:
        post = await within_work_budget(
            evaluate_guardrails(
                db,
                tenant_id,
                tenant_policy_version,
                SafetyConfig(tenant_id=tenant_id),
                generated,
                force_fail_closed=True,
                snapshot=snapshot,
            )
        )
    except TimeoutError:
        post = GuardrailEvaluation(
            status="evaluation_failed",
            safe_text=None,
            reason="The output safety check exceeded its deadline.",
            violations=(),
            error_code="protected_chat_deadline_exceeded",
            failure_codes=("protected_chat_deadline_exceeded",),
            policy_version=snapshot.policy_version,
            policy_snapshot_hash=snapshot.policy_snapshot_hash,
            fail_mode="closed",
            fallback_message=snapshot.config.fallback_message,
            redaction_counts={},
        )
    except Exception:
        post = GuardrailEvaluation(
            status="evaluation_failed",
            safe_text=None,
            reason="A safety check could not be completed.",
            violations=(),
            error_code="guardrail_evaluation_failed",
            failure_codes=("guardrail_evaluation_failed",),
            policy_version=snapshot.policy_version,
            policy_snapshot_hash=snapshot.policy_snapshot_hash,
            fail_mode="closed",
            fallback_message=snapshot.config.fallback_message,
            redaction_counts={},
        )
    evaluations.append(post)
    post_ms = max(0, int((perf_counter() - post_started) * 1000))

    try:
        await write_audit_with_bound("post", generated, post, None, snapshot, post_ms)
    except Exception:
        return ProtectedChatOutcome(
            "service_unavailable", None, _fallback(post), "audit_unavailable",
            bool(pre.redaction_counts), bool(post.redaction_counts),
            snapshot.policy_version, snapshot.policy_snapshot_hash,
            tuple(evaluations), provider_calls,
        )

    if post.status == "blocked":
        return ProtectedChatOutcome(
            "blocked", None, _fallback(post), None,
            bool(pre.redaction_counts), bool(post.redaction_counts),
            snapshot.policy_version, snapshot.policy_snapshot_hash,
            tuple(evaluations), provider_calls,
        )
    if post.status == "evaluation_failed" or post.safe_text is None:
        return ProtectedChatOutcome(
            "evaluation_failed", None, _fallback(post),
            post.error_code or "guardrail_evaluation_failed",
            bool(pre.redaction_counts), bool(post.redaction_counts),
            snapshot.policy_version, snapshot.policy_snapshot_hash,
            tuple(evaluations), provider_calls,
        )

    status: ChatStatus = "redacted" if post.redaction_counts else "allowed"
    return ProtectedChatOutcome(
        status,
        post.safe_text,
        None,
        None,
        bool(pre.redaction_counts),
        bool(post.redaction_counts),
        snapshot.policy_version,
        snapshot.policy_snapshot_hash,
        tuple(evaluations),
        provider_calls,
    )
