"""Type-specific policy contracts without database or provider access."""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.guardrails.policy_engine import PolicyEngine
from app.services.guardrails.groq_client import GroqClient, GroqProviderError
from app.services.guardrails.policy_snapshot import (
    PolicyRuleSnapshot,
    PolicyVectorSnapshot,
)

policy_engine_module = importlib.import_module(
    "app.services.guardrails.policy_engine"
)


class _CharacterOffsetTokenizer:
    model_max_length = 512

    def num_special_tokens_to_add(self, pair: bool = False) -> int:
        return 0

    def __call__(self, text: str, **_kwargs):
        return {"offset_mapping": [(index, index + 1) for index in range(len(text))]}


class _InjectionClassifier:
    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.tokenizer = _CharacterOffsetTokenizer()
        self.windows: list[str] = []

    def __call__(self, window: str):
        self.windows.append(window)
        return [
            {
                "label": "INJECTION" if self.marker in window else "SAFE",
                "score": 0.99 if self.marker in window else 0.01,
            }
        ]


def _rule(
    rule_type: str,
    parameters: dict | None = None,
    *,
    rule_text: str = "synthetic rule",
    embeddings: tuple[PolicyVectorSnapshot, ...] = (),
    enabled: bool = True,
) -> PolicyRuleSnapshot:
    return PolicyRuleSnapshot(
        policy_id=uuid4(),
        version=1,
        name=f"synthetic {rule_type}",
        rule_type=rule_type,
        rule_text=rule_text,
        parameters_json=json.dumps(parameters or {}),
        is_enabled=enabled,
        policy_hash="synthetic-policy-hash",
        embeddings=embeddings,
    )


def _db() -> SimpleNamespace:
    return SimpleNamespace()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Please BLOCKED this phrase.", True),
        ("This is blocked by policy.", True),
        ("This is unblocked.", False),
        ("This says BLOCKEDword.", False),
    ],
)
async def test_keyword_is_case_insensitive_literal_with_word_boundaries(
    message: str,
    expected: bool,
) -> None:
    engine = PolicyEngine()
    result = await engine.check_message(
        _db(),
        uuid4(),
        message,
        policy_snapshot=(_rule("keyword", {"keyword": "blocked"}),),
    )

    assert result.violated is expected
    assert bool(result.matched_policies) is expected
    if expected:
        assert result.matched_policies[0].rule_type == "keyword"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [("ref 1234 received", True), ("ref 12345 received", False)],
)
async def test_regex_match_isolated_and_bounded(message: str, expected: bool) -> None:
    engine = PolicyEngine()
    result = await engine.check_message(
        _db(),
        uuid4(),
        message,
        policy_snapshot=(_rule("regex_match", {"pattern": r"\b\d{4}\b"}),),
    )

    assert result.violated is expected
    assert result.error_codes == []


def test_pathological_regex_is_killed_and_reported() -> None:
    result, error_code = policy_engine_module._regex_match_isolated(
        r"^(a+)+$",
        "a" * 6000 + "!",
    )

    assert result is None
    assert error_code == "policy_regex_timeout"


@pytest.mark.asyncio
async def test_pii_rule_returns_only_transformed_text_and_category_counts() -> None:
    engine = PolicyEngine()
    result = await engine.check_message(
        _db(),
        uuid4(),
        "Contact alice@example.com",
        policy_snapshot=(
            _rule("pii_redaction", {"pii_types": ["email"]}),
        ),
    )

    assert result.violated is False
    assert result.safe_text == "Contact [EMAIL_REDACTED]"
    assert result.redaction_counts == {"email": 1}
    assert "alice@example.com" not in result.safe_text


@pytest.mark.asyncio
@pytest.mark.parametrize("insertion", [0, 500, 2000, 4000, 7900])
async def test_prompt_injection_policy_checks_full_input_without_sampling_gaps(
    monkeypatch,
    insertion: int,
) -> None:
    engine = PolicyEngine()
    marker = "SyntheticAgentOverride"
    message = "x" * insertion + marker + "x" * (8000 - insertion - len(marker))
    classifier = _InjectionClassifier(marker)
    monkeypatch.setattr(
        policy_engine_module.injection_detector,
        "_classifier",
        classifier,
    )
    result = await engine.check_message(
        _db(),
        uuid4(),
        message,
        policy_snapshot=(
            _rule("prompt_injection", {"sensitivity": "moderate"}),
        ),
    )

    assert result.violated is True
    assert result.matched_policies[0].rule_type == "prompt_injection"
    if insertion == 0:
        # A positive first window may safely short-circuit later inference.
        assert len(classifier.windows) == 1
    else:
        assert len(classifier.windows) > 1
    assert any(marker in window for window in classifier.windows)


@pytest.mark.asyncio
async def test_prompt_injection_policy_has_full_window_benign_control(monkeypatch) -> None:
    engine = PolicyEngine()
    marker = "SyntheticAgentOverride"
    classifier = _InjectionClassifier(marker)
    monkeypatch.setattr(
        policy_engine_module.injection_detector,
        "_classifier",
        classifier,
    )
    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary benign content " * 250,
        policy_snapshot=(
            _rule("prompt_injection", {"sensitivity": "moderate"}),
        ),
    )

    assert result.violated is False
    assert result.error_codes == []
    assert len(classifier.windows) > 1


@pytest.mark.asyncio
async def test_semantic_heuristic_and_keyword_match_survive_vector_error(monkeypatch) -> None:
    engine = PolicyEngine()
    engine._model = object()
    monkeypatch.setattr(engine, "encode", lambda _text: [1.0, 0.0])
    semantic_match = _rule(
        "semantic",
        embeddings=(
            PolicyVectorSnapshot(
                chunk_text="synthetic rule",
                embedding=(1.0, 0.0),
            ),
        ),
    )
    missing = _rule("semantic", rule_text="another synthetic rule")
    keyword_match = _rule("keyword", {"keyword": "ordinary"})

    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary input",
        policy_snapshot=(semantic_match, missing, keyword_match),
    )

    assert result.violated is True
    assert {item.rule_type for item in result.matched_policies} == {
        "semantic",
        "keyword",
    }
    assert result.error_codes == ["policy_embedding_missing"]


@pytest.mark.asyncio
async def test_multiple_llm_rules_use_one_judge_call_and_keep_violation(monkeypatch) -> None:
    engine = PolicyEngine()
    judge = AsyncMock(return_value=["allow", "violate"])
    monkeypatch.setattr(engine, "groq_client", SimpleNamespace(judge=judge))
    policies = (
        _rule("llm_eval", {"rubric": "Do not disclose synthetic secrets."}),
        _rule("llm_eval", {"rubric": "Do not promise guaranteed returns."}),
    )

    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary synthetic input",
        policy_snapshot=policies,
    )

    assert judge.await_count == 1
    assert len(judge.await_args.args[1]) == 2
    assert result.violated is True
    assert result.matched_policies[0].policy_id == str(policies[1].policy_id)


@pytest.mark.asyncio
async def test_uncertain_llm_judgment_is_explicitly_blocking(monkeypatch) -> None:
    engine = PolicyEngine()
    judge = AsyncMock(return_value=["uncertain"])
    monkeypatch.setattr(engine, "groq_client", SimpleNamespace(judge=judge))

    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary synthetic input",
        policy_snapshot=(
            _rule("llm_eval", {"rubric": "Apply this synthetic criterion."}),
        ),
    )

    assert result.violated is False
    assert result.block_on_error is True
    assert result.error_codes == ["llm_judge_uncertain"]


@pytest.mark.asyncio
async def test_provider_unavailable_never_becomes_a_policy_allow(monkeypatch) -> None:
    engine = PolicyEngine()
    judge = AsyncMock(side_effect=GroqProviderError("groq_api_key_missing"))
    monkeypatch.setattr(engine, "groq_client", SimpleNamespace(judge=judge))

    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary synthetic input",
        policy_snapshot=(
            _rule("llm_eval", {"rubric": "Apply this synthetic criterion."}),
        ),
    )

    assert result.violated is False
    assert result.block_on_error is True
    assert result.error_codes == ["groq_api_key_missing"]


@pytest.mark.asyncio
async def test_new_engine_with_missing_key_returns_provider_error_without_monkeypatch() -> None:
    client = GroqClient(
        configured=SimpleNamespace(
            groq_api_key="",
            groq_live_enabled=True,
            groq_free_plan_confirmed=True,
            groq_model="openai/gpt-oss-20b",
            groq_timeout_seconds=20.0,
            groq_max_completion_tokens=1024,
        )
    )
    engine = PolicyEngine(judge_client=client)

    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary synthetic input",
        policy_snapshot=(
            _rule("llm_eval", {"rubric": "Apply this synthetic criterion."}),
        ),
    )

    assert result.block_on_error is True
    assert result.error_codes == ["groq_api_key_missing"]


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_failure", [False, True])
async def test_fail_closed_skips_judge_after_local_evaluator_failure(
    monkeypatch,
    prior_failure: bool,
) -> None:
    client = GroqClient(
        configured=SimpleNamespace(
            groq_api_key="",
            groq_live_enabled=True,
            groq_free_plan_confirmed=True,
            groq_model="openai/gpt-oss-20b",
            groq_timeout_seconds=20.0,
            groq_max_completion_tokens=1024,
        )
    )
    engine = PolicyEngine(judge_client=client)
    policies = []
    if not prior_failure:
        monkeypatch.setattr(
            policy_engine_module,
            "_regex_match_isolated",
            lambda *_args: (None, "policy_regex_timeout"),
        )
        policies.append(_rule("regex_match", {"pattern": "synthetic"}))
    policies.append(
        _rule("llm_eval", {"rubric": "Apply this synthetic criterion."})
    )

    result = await engine.check_message(
        _db(),
        uuid4(),
        "ordinary synthetic input",
        policy_snapshot=tuple(policies),
        fail_closed=True,
        prior_evaluator_failure=prior_failure,
    )

    assert result.block_on_error is True
    assert "llm_judge_skipped_after_evaluator_failure" in result.error_codes
    assert "groq_api_key_missing" not in result.error_codes
    if not prior_failure:
        assert "policy_regex_timeout" in result.error_codes


@pytest.mark.asyncio
async def test_local_positive_skips_llm_judge_without_losing_match(monkeypatch) -> None:
    engine = PolicyEngine()
    judge = AsyncMock(return_value=["allow"])
    monkeypatch.setattr(engine, "groq_client", SimpleNamespace(judge=judge))

    result = await engine.check_message(
        _db(),
        uuid4(),
        "BLOCK this input",
        policy_snapshot=(
            _rule("keyword", {"keyword": "block"}),
            _rule("llm_eval", {"rubric": "Apply this synthetic criterion."}),
        ),
    )

    assert result.violated is True
    assert result.matched_policies[0].rule_type == "keyword"
    judge.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_nonsemantic_rule_needs_no_model_or_provider() -> None:
    engine = PolicyEngine()
    result = await engine.check_message(
        _db(),
        uuid4(),
        "BLOCK this input",
        policy_snapshot=(
            _rule("keyword", {"keyword": "block"}, enabled=False),
        ),
    )

    assert result.violated is False
    assert result.error_codes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_first", [False, True])
async def test_nonsemantic_match_is_preserved_when_another_rule_is_invalid(
    invalid_first: bool,
) -> None:
    engine = PolicyEngine()
    matching = _rule("keyword", {"keyword": "block"})
    invalid = _rule("regex_match", {"pattern": "["})
    result = await engine.check_message(
        _db(),
        uuid4(),
        "BLOCK this input",
        policy_snapshot=(invalid, matching) if invalid_first else (matching, invalid),
    )

    assert result.violated is True
    assert result.matched_policies[0].rule_type == "keyword"
    assert result.error_codes == ["policy_regex_invalid"]
