"""Immutable behavior snapshots used for one guardrail decision."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isfinite
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy
from app.models.policy_embedding import PolicyEmbedding
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant


@dataclass(frozen=True)
class PolicyVectorSnapshot:
    chunk_text: str
    embedding: tuple[float, ...]

    @property
    def content_hash(self) -> str:
        record = json.dumps(
            self.embedding,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(record).hexdigest()


@dataclass(frozen=True)
class PolicyRuleSnapshot:
    policy_id: UUID
    version: int
    name: str
    rule_type: str
    rule_text: str
    parameters_json: str
    is_enabled: bool
    policy_hash: str | None
    embeddings: tuple[PolicyVectorSnapshot, ...] = ()
    embedding_error_codes: tuple[str, ...] = ()

    @classmethod
    def from_policy(
        cls,
        policy: Policy,
        embeddings: tuple[PolicyVectorSnapshot, ...] = (),
        embedding_error_codes: tuple[str, ...] = (),
    ) -> "PolicyRuleSnapshot":
        parameters = json.loads(
            json.dumps(policy.parameters or {}, sort_keys=True, ensure_ascii=False)
        )
        return cls(
            policy_id=policy.id,
            version=int(policy.version or 1),
            name=policy.name,
            rule_type=policy.rule_type,
            rule_text=policy.rule_text,
            parameters_json=json.dumps(
                parameters,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            is_enabled=bool(policy.is_enabled),
            policy_hash=policy.policy_hash,
            embeddings=embeddings,
            embedding_error_codes=embedding_error_codes,
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return json.loads(self.parameters_json)

    def as_hash_record(self) -> dict[str, Any]:
        return {
            "id": str(self.policy_id),
            "version": self.version,
            "rule_type": self.rule_type,
            "rule_text": self.rule_text,
            "parameters": json.loads(self.parameters_json),
            "is_enabled": self.is_enabled,
            "policy_hash": self.policy_hash,
            "embedding_chunks": [
                {
                    "chunk_text": item.chunk_text,
                    "vector_hash": item.content_hash,
                }
                for item in self.embeddings
            ],
            "embedding_error_codes": list(self.embedding_error_codes),
        }


@dataclass(frozen=True)
class TenantBehaviorSnapshot:
    active_policy_version: int
    config_values: dict[str, Any] | None
    policies: tuple[PolicyRuleSnapshot, ...]


async def load_behavior_snapshot(
    db: AsyncSession,
    tenant_id: UUID,
) -> TenantBehaviorSnapshot:
    """Read tenant version, safety settings, rules, and vectors in one statement."""
    result = await db.execute(
        select(
            Tenant.active_policy_version,
            SafetyConfig.global_block_enabled,
            SafetyConfig.injection_protection,
            SafetyConfig.injection_sensitivity,
            SafetyConfig.pii_redaction,
            SafetyConfig.pii_types,
            SafetyConfig.policy_enforcement,
            SafetyConfig.fail_mode,
            SafetyConfig.fallback_message,
            Policy,
            PolicyEmbedding.chunk_text,
            PolicyEmbedding.embedding,
        )
        .select_from(Tenant)
        .outerjoin(SafetyConfig, SafetyConfig.tenant_id == Tenant.id)
        .outerjoin(Policy, Policy.tenant_id == Tenant.id)
        .outerjoin(
            PolicyEmbedding,
            (PolicyEmbedding.policy_id == Policy.id)
            & (PolicyEmbedding.tenant_id == Tenant.id),
        )
        .where(Tenant.id == tenant_id)
        .order_by(Policy.id, PolicyEmbedding.id)
        .execution_options(populate_existing=True)
    )
    rows = result.all()
    if not rows:
        raise LookupError("Tenant behavior snapshot is unavailable.")

    first = rows[0]
    active_policy_version = int(first.active_policy_version)
    config_values = (
        None
        if first.global_block_enabled is None
        else {
            "global_block_enabled": bool(first.global_block_enabled),
            "injection_protection": bool(first.injection_protection),
            "injection_sensitivity": str(first.injection_sensitivity),
            "pii_redaction": bool(first.pii_redaction),
            "pii_types": tuple(sorted(first.pii_types or [])),
            "policy_enforcement": bool(first.policy_enforcement),
            "fail_mode": str(first.fail_mode),
            "fallback_message": str(first.fallback_message),
        }
    )

    rows_by_policy: dict[
        UUID,
        tuple[Policy, list[PolicyVectorSnapshot], set[str]],
    ] = {}
    for row in rows:
        policy = row.Policy
        if policy is None:
            continue
        entry = rows_by_policy.setdefault(policy.id, (policy, [], set()))
        if policy.rule_type != "semantic":
            continue
        if row.chunk_text is None and row.embedding is None:
            entry[2].add("policy_embedding_missing")
            continue
        if row.chunk_text is None or row.embedding is None:
            entry[2].add("policy_embedding_incomplete")
            continue
        try:
            embedding = tuple(float(value) for value in row.embedding)
        except (TypeError, ValueError, OverflowError):
            entry[2].add("policy_embedding_invalid")
            continue
        if not embedding or not all(isfinite(value) for value in embedding):
            entry[2].add("policy_embedding_invalid")
            continue
        entry[1].append(
            PolicyVectorSnapshot(chunk_text=row.chunk_text, embedding=embedding)
        )

    policies = tuple(
        PolicyRuleSnapshot.from_policy(
            policy,
            tuple(embeddings),
            tuple(sorted(error_codes)),
        )
        for policy, embeddings, error_codes in rows_by_policy.values()
    )
    return TenantBehaviorSnapshot(active_policy_version, config_values, policies)


async def load_policy_snapshot(
    db: AsyncSession,
    tenant_id: UUID,
) -> tuple[PolicyRuleSnapshot, ...]:
    """Read tenant rules once and return immutable copies for this evaluation."""
    return (await load_behavior_snapshot(db, tenant_id)).policies
