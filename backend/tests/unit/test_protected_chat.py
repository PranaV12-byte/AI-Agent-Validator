"""Local protected-chat orchestration tests with no DB or provider access."""

import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.services.guardrails.groq_client import GroqClient, GroqProviderError, JudgeRule
from app.services.guardrails.pipeline import (
    GuardrailConfigSnapshot,
    GuardrailEvaluation,
    GuardrailSnapshot,
)
from app.services.guardrails import protected_chat as protected_chat_module


def _snapshot() -> GuardrailSnapshot:
    return GuardrailSnapshot(
        policy_version=7,
        config=GuardrailConfigSnapshot(
            global_block_enabled=False,
            injection_protection=True,
            injection_sensitivity="moderate",
            pii_redaction=True,
            pii_types=("email",),
            policy_enforcement=True,
            fail_mode="open",
            fallback_message="Safe fallback.",
        ),
        policies=(),
        policy_snapshot_hash="snapshot-hash",
    )


def _evaluation(
    status: str,
    *,
    safe_text: str | None,
    failure_codes: tuple[str, ...] = (),
    redaction_counts: dict[str, int] | None = None,
) -> GuardrailEvaluation:
    return GuardrailEvaluation(
        status=status,  # type: ignore[arg-type]
        safe_text=safe_text,
        reason="synthetic test result",
        violations=(),
        error_code=failure_codes[0] if failure_codes else None,
        failure_codes=failure_codes,
        policy_version=7,
        policy_snapshot_hash="snapshot-hash",
        fail_mode="closed",
        fallback_message="Safe fallback.",
        redaction_counts=redaction_counts or {},
    )


class _Provider:
    def __init__(self, answer: str = "Safe answer.", error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.mark.asyncio
async def test_blocked_precheck_is_audited_and_never_calls_provider(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    monkeypatch.setattr(
        protected_chat_module,
        "evaluate_guardrails",
        _async_value(_evaluation("blocked", safe_text=None)),
    )
    writes: list[str] = []
    provider = _Provider()

    async def write(stage, *_args):
        writes.append(stage)
        return uuid4()

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic blocked input",
        write_audit=write,
        client=provider,  # type: ignore[arg-type]
    )

    assert result.status == "blocked"
    assert result.answer is None
    assert result.provider_calls == 0
    assert provider.prompts == []
    assert writes == ["pre"]


@pytest.mark.asyncio
async def test_precheck_failure_never_forwards_even_with_open_snapshot(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    calls = 0

    async def fail_open_evaluation(*_args, **kwargs):
        nonlocal calls
        calls += 1
        assert kwargs["force_fail_closed"] is True
        return _evaluation(
            "evaluation_failed",
            safe_text="sanitized but unchecked",
            failure_codes=("injection_detector_unavailable",),
        )

    monkeypatch.setattr(
        protected_chat_module,
        "evaluate_guardrails",
        fail_open_evaluation,
    )
    writes: list[str] = []
    provider = _Provider()

    async def write(stage, *_args):
        writes.append(stage)
        return uuid4()

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic input",
        write_audit=write,
        client=provider,  # type: ignore[arg-type]
    )

    assert calls == 1
    assert result.status == "evaluation_failed"
    assert result.answer is None
    assert result.provider_calls == 0
    assert provider.prompts == []
    assert writes == ["pre"]


@pytest.mark.asyncio
async def test_success_uses_one_snapshot_and_audits_before_return(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    seen_snapshots: list[GuardrailSnapshot] = []
    results = iter(
        [
            _evaluation("redacted", safe_text="safe user text", redaction_counts={"email": 1}),
            _evaluation("allowed", safe_text="Safe answer."),
        ]
    )

    async def evaluate(*_args, **kwargs):
        seen_snapshots.append(kwargs["snapshot"])
        return next(results)

    monkeypatch.setattr(protected_chat_module, "evaluate_guardrails", evaluate)
    writes: list[tuple[str, str]] = []
    provider = _Provider()

    async def write(stage, text, *_args):
        writes.append((stage, text))
        return uuid4()

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="raw user text",
        write_audit=write,
        client=provider,  # type: ignore[arg-type]
    )

    assert result.status == "allowed"
    assert result.answer == "Safe answer."
    assert result.input_redacted is True
    assert result.provider_calls == 1
    assert provider.prompts == ["safe user text"]
    assert seen_snapshots == [snapshot, snapshot]
    assert writes == [
        ("pre", "raw user text"),
        ("post", "Safe answer."),
    ]


@pytest.mark.asyncio
async def test_pre_judge_generation_and_post_judge_use_at_most_three_mocked_requests(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if payload.get("response_format") == {"type": "json_object"}:
            content = json.dumps({"results": [{"id": "r1", "decision": "allow"}]})
        else:
            content = "Safe answer."
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": content}, "finish_reason": "stop"}
                ]
            },
        )

    settings = SimpleNamespace(
        groq_api_key="synthetic-test-key-never-valid",
        groq_live_enabled=True,
        groq_free_plan_confirmed=True,
        groq_model="openai/gpt-oss-20b",
        groq_timeout_seconds=2.0,
        groq_max_completion_tokens=1024,
    )

    def client_factory(*, timeout):
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
        )

    judge_client = GroqClient(settings, client_factory=client_factory)
    generation_client = GroqClient(settings, client_factory=client_factory)
    results = iter(
        [
            _evaluation("allowed", safe_text="safe user text"),
            _evaluation("allowed", safe_text="Safe answer."),
        ]
    )

    async def evaluate(*args, **kwargs):
        await judge_client.judge(
            args[4],
            [JudgeRule("Apply this synthetic, bounded criterion.")],
        )
        return next(results)

    monkeypatch.setattr(protected_chat_module, "evaluate_guardrails", evaluate)

    async def write(_stage, *_args):
        return uuid4()

    outcome = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic user request",
        write_audit=write,
        client=generation_client,
    )

    payloads = [json.loads(request.content) for request in requests]
    assert outcome.status == "allowed"
    assert outcome.provider_calls == 1  # generation only; judges are separate HTTP calls
    assert len(requests) == 3
    assert sum("response_format" in payload for payload in payloads) == 2
    assert sum("response_format" not in payload for payload in payloads) == 1


@pytest.mark.asyncio
async def test_provider_error_is_audited_and_never_returns_fake_answer(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    monkeypatch.setattr(
        protected_chat_module,
        "evaluate_guardrails",
        _async_value(_evaluation("allowed", safe_text="safe user text")),
    )
    writes: list[tuple[str, str | None]] = []
    provider = _Provider(error=GroqProviderError("groq_api_key_missing"))

    async def write(stage, _text, _evaluation, error_code, *_args):
        writes.append((stage, error_code))
        return uuid4()

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic input",
        write_audit=write,
        client=provider,  # type: ignore[arg-type]
    )

    assert result.status == "provider_unavailable"
    assert result.answer is None
    assert result.error_code == "groq_api_key_missing"
    assert result.provider_calls == 1
    assert writes == [("pre", None), ("generation", "groq_api_key_missing")]


@pytest.mark.asyncio
async def test_postcheck_block_never_returns_generated_answer(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    results = iter(
        [
            _evaluation("allowed", safe_text="safe user text"),
            _evaluation("blocked", safe_text=None),
        ]
    )
    monkeypatch.setattr(
        protected_chat_module,
        "evaluate_guardrails",
        _async_iterator(results),
    )
    writes: list[str] = []

    async def write(stage, *_args):
        writes.append(stage)
        return uuid4()

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic input",
        write_audit=write,
        client=_Provider(answer="unsafe output"),  # type: ignore[arg-type]
    )

    assert result.status == "blocked"
    assert result.answer is None
    assert result.fallback_message == "Safe fallback."
    assert writes == ["pre", "post"]


@pytest.mark.asyncio
async def test_failed_pre_audit_stops_before_provider(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    monkeypatch.setattr(
        protected_chat_module,
        "evaluate_guardrails",
        _async_value(_evaluation("allowed", safe_text="safe user text")),
    )
    provider = _Provider()

    async def fail_audit(*_args):
        raise RuntimeError("synthetic audit write failure")

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic input",
        write_audit=fail_audit,
        client=provider,  # type: ignore[arg-type]
    )

    assert result.status == "service_unavailable"
    assert result.error_code == "audit_unavailable"
    assert result.answer is None
    assert result.provider_calls == 0
    assert provider.prompts == []


@pytest.mark.asyncio
async def test_total_deadline_records_failure_without_late_provider_call(monkeypatch) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        protected_chat_module,
        "load_guardrail_snapshot",
        _async_value(snapshot),
    )
    monkeypatch.setattr(
        protected_chat_module,
        "evaluate_guardrails",
        _async_value(_evaluation("allowed", safe_text="safe user text")),
    )
    clock_values = iter((0.0, 0.0, 0.0, 76.0))
    monkeypatch.setattr(protected_chat_module, "monotonic", lambda: next(clock_values))
    writes: list[tuple[str, str | None]] = []
    provider = _Provider()

    async def write(stage, _text, _evaluation, error_code, *_args):
        writes.append((stage, error_code))
        return uuid4()

    result = await protected_chat_module.run_protected_chat(
        db=SimpleNamespace(),
        tenant_id=uuid4(),
        tenant_policy_version=3,
        message="synthetic input",
        write_audit=write,
        client=provider,  # type: ignore[arg-type]
    )

    assert result.status == "provider_unavailable"
    assert result.error_code == "protected_chat_deadline_exceeded"
    assert result.answer is None
    assert result.provider_calls == 0
    assert provider.prompts == []
    assert writes == [
        ("pre", None),
        ("generation", "protected_chat_deadline_exceeded"),
    ]


def _async_value(value):
    async def resolved(*_args, **_kwargs):
        return value

    return resolved


def _async_iterator(values):
    async def next_value(*_args, **_kwargs):
        return next(values)

    return next_value
