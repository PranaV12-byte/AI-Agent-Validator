"""Policy matching must use only immutable rule/vector snapshots."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.guardrails.policy_engine import PolicyEngine
from app.services.guardrails.policy_snapshot import (
    PolicyRuleSnapshot,
    PolicyVectorSnapshot,
)


def _snapshot(
    *,
    chunk_text: str = "synthetic policy text",
    embeddings: tuple[PolicyVectorSnapshot, ...] | None = None,
) -> tuple[PolicyRuleSnapshot, ...]:
    if embeddings is None:
        embeddings = (
            PolicyVectorSnapshot(
                chunk_text=chunk_text,
                embedding=(1.0, 0.0),
            ),
        )
    return (
        PolicyRuleSnapshot(
            policy_id=uuid4(),
            version=1,
            name="synthetic policy",
            rule_type="semantic",
            rule_text="synthetic policy text",
            parameters_json="{}",
            is_enabled=True,
            policy_hash="synthetic-policy-hash",
            embeddings=embeddings,
        ),
    )


@pytest.mark.asyncio
async def test_policy_engine_matches_using_snapshot_vectors_without_database_reread(
    monkeypatch,
) -> None:
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=AssertionError("mutable vector reread"))
    )
    engine = PolicyEngine()
    engine._model = object()
    monkeypatch.setattr(engine, "encode", lambda _text: [1.0, 0.0])

    result = await engine.check_message(
        db,
        uuid4(),
        "ordinary synthetic text",
        policy_snapshot=_snapshot(),
    )

    assert result.violated is True
    assert result.matched_policies[0].similarity_score == 1.0
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_enabled_policy_without_snapshot_vector_returns_explicit_error(monkeypatch) -> None:
    engine = PolicyEngine()
    engine._model = object()
    monkeypatch.setattr(engine, "encode", lambda _text: [1.0, 0.0])
    missing_vector = _snapshot(embeddings=())

    result = await engine.check_message(
        SimpleNamespace(),
        uuid4(),
        "ordinary synthetic text",
        policy_snapshot=missing_vector,
    )

    assert result.violated is False
    assert result.error_codes == ["policy_embedding_missing"]


@pytest.mark.asyncio
async def test_stale_embedding_chunk_returns_explicit_error(monkeypatch) -> None:
    engine = PolicyEngine()
    engine._model = object()
    monkeypatch.setattr(engine, "encode", lambda _text: [1.0, 0.0])
    stale_vector = _snapshot(chunk_text="prior synthetic policy text")

    result = await engine.check_message(
        SimpleNamespace(),
        uuid4(),
        "ordinary synthetic text",
        policy_snapshot=stale_vector,
    )

    assert result.violated is False
    assert result.error_codes == ["policy_embedding_stale"]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.asyncio
async def test_later_bad_policy_does_not_discard_prior_match(monkeypatch, reverse) -> None:
    engine = PolicyEngine()
    engine._model = object()
    monkeypatch.setattr(engine, "encode", lambda _text: [1.0, 0.0])
    matching = _snapshot()[0]
    missing = _snapshot(embeddings=())[0]
    policies = (missing, matching) if reverse else (matching, missing)

    result = await engine.check_message(
        SimpleNamespace(),
        uuid4(),
        "ordinary synthetic text",
        policy_snapshot=policies,
    )

    assert result.violated is True
    assert len(result.matched_policies) == 1
    assert result.error_codes == ["policy_embedding_missing"]
