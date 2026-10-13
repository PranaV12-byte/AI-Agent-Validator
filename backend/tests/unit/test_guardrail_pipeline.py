"""Pure contracts for fail-explicit shared guardrail evaluation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.guardrails.pipeline import (
    GuardrailConfigSnapshot,
    GuardrailSnapshot,
    evaluate_guardrails,
)
from app.services.guardrails.policy_snapshot import (
    PolicyRuleSnapshot,
    PolicyVectorSnapshot,
)


@pytest.mark.asyncio
async def test_global_block_blocks_without_a_database_read() -> None:
    db = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("unexpected DB read")))
    config = SimpleNamespace(
        global_block_enabled=True,
        injection_protection=True,
        injection_sensitivity="moderate",
        pii_redaction=True,
        pii_types=["email"],
        policy_enforcement=True,
        fail_mode="open",
        fallback_message="blocked",
    )

    result = await evaluate_guardrails(
        db,
        uuid4(),
        4,
        config,
        "synthetic request",
    )

    assert result.status == "blocked"
    assert result.action == "block"
    assert result.error_code is None
    assert result.violations[0]["type"] == "global_block"
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_enabled_checks_is_not_reported_as_a_successful_evaluation() -> None:
    from app.services.guardrails import pipeline

    snapshot = GuardrailSnapshot(
        policy_version=3,
        config=GuardrailConfigSnapshot(
            global_block_enabled=False,
            injection_protection=False,
            injection_sensitivity="moderate",
            pii_redaction=False,
            pii_types=(),
            policy_enforcement=False,
            fail_mode="open",
            fallback_message="blocked",
        ),
        policies=(),
        policy_snapshot_hash="synthetic-snapshot-hash",
    )

    result = await pipeline.evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "ordinary synthetic input",
        snapshot=snapshot,
    )

    assert result.status == "allowed"
    assert result.reason == "No safety checks are enabled."


@pytest.mark.asyncio
async def test_failed_injection_check_does_not_claim_all_checks_passed(monkeypatch) -> None:
    from app.services.guardrails import pipeline

    monkeypatch.setattr(
        pipeline.injection_detector,
        "detect_full_text",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_injection=False,
            complete=False,
            confidence=0.0,
            method="heuristic_only",
        ),
    )
    result = await pipeline.evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "ordinary synthetic input",
        snapshot=_snapshot(pii_redaction=False),
    )

    assert result.status == "evaluation_failed"
    assert result.reason != "All enabled checks passed."
    assert result.failure_codes == ("injection_detector_unavailable",)


def _snapshot(
    *,
    pii_redaction: bool = True,
    policy_enforcement: bool = False,
    policies: tuple[PolicyRuleSnapshot, ...] = (),
    fail_mode: str = "open",
) -> GuardrailSnapshot:
    config = GuardrailConfigSnapshot(
        global_block_enabled=False,
        injection_protection=True,
        injection_sensitivity="moderate",
        pii_redaction=pii_redaction,
        pii_types=("email", "phone", "aadhaar", "pan", "upi"),
        policy_enforcement=policy_enforcement,
        fail_mode=fail_mode,
        fallback_message="blocked",
    )
    return GuardrailSnapshot(3, config, policies, "synthetic-snapshot-hash")


@pytest.mark.parametrize("insertion", [500, 2000, 7900])
@pytest.mark.asyncio
async def test_global_injection_check_uses_full_overlapping_windows(
    monkeypatch,
    insertion: int,
) -> None:
    from app.services.guardrails import pipeline

    marker = "SyntheticClassifierOnlyAttack"

    class CharacterOffsetTokenizer:
        model_max_length = 512

        def num_special_tokens_to_add(self, pair: bool = False) -> int:
            return 0

        def __call__(self, text: str, **_kwargs):
            return {"offset_mapping": [(index, index + 1) for index in range(len(text))]}

    class Classifier:
        tokenizer = CharacterOffsetTokenizer()

        def __init__(self):
            self.windows: list[str] = []

        def __call__(self, window: str):
            self.windows.append(window)
            is_injection = marker in window
            return [
                {
                    "label": "INJECTION" if is_injection else "SAFE",
                    "score": 0.99 if is_injection else 0.01,
                }
            ]

    classifier = Classifier()
    monkeypatch.setattr(pipeline.injection_detector, "_classifier", classifier)
    message = "x" * insertion + marker + "x" * (8000 - insertion - len(marker))
    result = await pipeline.evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        message,
        snapshot=_snapshot(pii_redaction=False),
    )

    assert result.status == "blocked"
    assert result.action == "block"
    assert classifier.windows
    assert any(marker in window for window in classifier.windows)


def _enabled_policy() -> PolicyRuleSnapshot:
    return PolicyRuleSnapshot(
        policy_id=uuid4(),
        version=1,
        name="synthetic",
        rule_type="semantic",
        rule_text="synthetic rule",
        parameters_json="{}",
        is_enabled=True,
        policy_hash="synthetic-policy-hash",
    )


@pytest.mark.asyncio
async def test_injection_failure_does_not_skip_successful_pii_redaction(monkeypatch) -> None:
    from app.services.guardrails import pipeline

    def _broken_detector(*_args, **_kwargs):
        raise RuntimeError("synthetic detector failure")

    monkeypatch.setattr(pipeline.injection_detector, "detect_full_text", _broken_detector)
    result = await evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "Contact alice@example.com",
        snapshot=_snapshot(),
    )

    assert result.status == "evaluation_failed"
    assert result.action == "redact"
    assert result.failure_codes == ("injection_evaluation_failed",)
    assert result.safe_text == "Contact [EMAIL_REDACTED]"


@pytest.mark.asyncio
async def test_open_mode_never_forwards_input_when_pii_redactor_fails(monkeypatch) -> None:
    from app.services.guardrails import pipeline

    def _broken_detector(*_args, **_kwargs):
        raise RuntimeError("synthetic detector failure")

    def _broken_redactor(*_args, **_kwargs):
        raise RuntimeError("synthetic redactor failure")

    monkeypatch.setattr(pipeline.injection_detector, "detect_full_text", _broken_detector)
    monkeypatch.setattr(pipeline.pii_redactor, "redact", _broken_redactor)
    result = await evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "Contact alice@example.com",
        snapshot=_snapshot(policy_enforcement=True, policies=(_enabled_policy(),)),
    )

    assert result.status == "evaluation_failed"
    assert result.action == "block"
    assert result.safe_text is None
    assert result.failure_codes == (
        "injection_evaluation_failed",
        "pii_evaluation_failed",
        "policy_evaluation_skipped_unsafe_input",
    )


@pytest.mark.asyncio
async def test_positive_policy_finding_blocks_even_when_injection_check_failed(monkeypatch) -> None:
    from app.services.guardrails import pipeline

    def _broken_detector(*_args, **_kwargs):
        raise RuntimeError("synthetic detector failure")

    async def _violated_policy(*_args, **_kwargs):
        return SimpleNamespace(
            violated=True,
            matched_policies=[
                SimpleNamespace(policy_id="synthetic-policy", similarity_score=0.91)
            ],
        )

    monkeypatch.setattr(pipeline.injection_detector, "detect_full_text", _broken_detector)
    monkeypatch.setattr(pipeline.policy_engine, "check_message", _violated_policy)
    result = await evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "ordinary synthetic input",
        snapshot=_snapshot(
            policy_enforcement=True,
            policies=(_enabled_policy(),),
        ),
    )

    assert result.status == "blocked"
    assert result.action == "block"
    assert result.failure_codes == ("injection_evaluation_failed",)
    assert any(item["type"] == "policy_violation" for item in result.violations)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.asyncio
async def test_policy_match_blocks_fail_open_even_if_another_rule_is_unavailable(
    monkeypatch,
    reverse,
) -> None:
    from app.services.guardrails import pipeline

    monkeypatch.setattr(
        pipeline.injection_detector,
        "detect_full_text",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_injection=False,
            complete=True,
            confidence=0.0,
            method="synthetic",
        ),
    )
    monkeypatch.setattr(pipeline.policy_engine, "_model", object())
    monkeypatch.setattr(pipeline.policy_engine, "encode", lambda _text: [1.0, 0.0])

    matching_policy = PolicyRuleSnapshot(
        policy_id=uuid4(),
        version=1,
        name="synthetic matching policy",
        rule_type="semantic",
        rule_text="synthetic rule",
        parameters_json="{}",
        is_enabled=True,
        policy_hash="synthetic-policy-hash",
        embeddings=(
            PolicyVectorSnapshot(
                chunk_text="synthetic rule",
                embedding=(1.0, 0.0),
            ),
        ),
    )
    unavailable_policy = PolicyRuleSnapshot(
        policy_id=uuid4(),
        version=1,
        name="synthetic unavailable policy",
        rule_type="semantic",
        rule_text="another synthetic rule",
        parameters_json="{}",
        is_enabled=True,
        policy_hash="synthetic-policy-hash",
    )
    policies = (
        (unavailable_policy, matching_policy)
        if reverse
        else (matching_policy, unavailable_policy)
    )

    result = await evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "ordinary synthetic input",
        snapshot=_snapshot(
            pii_redaction=False,
            policy_enforcement=True,
            policies=policies,
        ),
    )

    assert result.status == "blocked"
    assert result.action == "block"
    assert result.error_code == "policy_embedding_missing"
    assert result.failure_codes == ("policy_embedding_missing",)
    assert any(item["type"] == "policy_violation" for item in result.violations)


@pytest.mark.asyncio
async def test_policy_failure_keeps_completed_pii_redaction_for_open_mode(monkeypatch) -> None:
    from app.services.guardrails import pipeline

    async def _broken_policy(*_args, **_kwargs):
        raise RuntimeError("synthetic policy failure")

    monkeypatch.setattr(pipeline.injection_detector, "detect_full_text", lambda *_args, **_kwargs: SimpleNamespace(
        is_injection=False,
        complete=True,
        confidence=0.0,
        method="model",
    ))
    monkeypatch.setattr(pipeline.policy_engine, "check_message", _broken_policy)
    result = await evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "Contact alice@example.com",
        snapshot=_snapshot(
            policy_enforcement=True,
            policies=(_enabled_policy(),),
        ),
    )

    assert result.status == "evaluation_failed"
    assert result.action == "redact"
    assert result.error_code == "policy_evaluation_failed"
    assert result.safe_text == "Contact [EMAIL_REDACTED]"


@pytest.mark.asyncio
async def test_unavailable_llm_policy_blocks_even_in_fail_open_mode(monkeypatch) -> None:
    from app.services.guardrails import pipeline

    async def _unavailable_judge(*_args, **_kwargs):
        return SimpleNamespace(
            violated=False,
            matched_policies=[],
            error_codes=["groq_api_key_missing"],
            safe_text="ordinary synthetic input",
            redaction_counts={},
            block_on_error=True,
        )

    monkeypatch.setattr(
        pipeline.injection_detector,
        "detect_full_text",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_injection=False,
            complete=True,
            confidence=0.0,
            method="synthetic",
        ),
    )
    monkeypatch.setattr(pipeline.policy_engine, "check_message", _unavailable_judge)
    llm_policy = PolicyRuleSnapshot(
        policy_id=uuid4(),
        version=1,
        name="synthetic judge rule",
        rule_type="llm_eval",
        rule_text="synthetic rule",
        parameters_json='{"rubric":"Apply a synthetic criterion."}',
        is_enabled=True,
        policy_hash="synthetic-policy-hash",
    )

    result = await evaluate_guardrails(
        SimpleNamespace(),
        uuid4(),
        3,
        SimpleNamespace(),
        "ordinary synthetic input",
        snapshot=_snapshot(
            pii_redaction=False,
            policy_enforcement=True,
            policies=(llm_policy,),
            fail_mode="open",
        ),
    )

    assert result.status == "evaluation_failed"
    assert result.action == "block"
    assert result.safe_text is None
    assert result.failure_codes == ("groq_api_key_missing",)
    assert not any(item["type"] == "policy_violation" for item in result.violations)
