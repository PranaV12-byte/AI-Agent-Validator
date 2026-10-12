"""
Policy Engine: Semantic matching of AI responses against immutable, snapshot-bound
SentenceTransformers embeddings persisted in pgvector.
"""
import hashlib
import json
import asyncio
import subprocess
import re
import structlog
from dataclasses import dataclass, field
from math import isfinite, sqrt
import sys
from typing import Any
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Policy
from app.models.policy_embedding import PolicyEmbedding
from app.services.guardrails.policy_snapshot import (
    PolicyRuleSnapshot,
    load_policy_snapshot,
)
from app.services.guardrails.groq_client import (
    GroqClient,
    GroqProviderError,
    JudgeRule,
    groq_client,
)
from app.services.guardrails.injection_detector import (
    MAX_INJECTION_INPUT_CHARS,
    injection_detector,
)
from app.services.guardrails.pii_redactor import PII_PATTERNS, pii_redactor

MAX_POLICY_INPUT_CHARS = MAX_INJECTION_INPUT_CHARS
MAX_REGEX_PATTERN_CHARS = 256
REGEX_MATCH_TIMEOUT_SECONDS = 1.0
MAX_LLM_JUDGE_RULES = 5


@dataclass
class PolicyMatch:
    policy_id: str
    policy_name: str
    rule_text: str
    similarity_score: float | None = None
    rule_type: str = "semantic"


@dataclass
class PolicyCheckResult:
    violated: bool
    matched_policies: list[PolicyMatch]
    error_codes: list[str] = field(default_factory=list)
    safe_text: str | None = None
    redaction_counts: dict[str, int] = field(default_factory=dict)
    block_on_error: bool = False


def _regex_match_isolated(pattern: str, text: str) -> tuple[bool | None, str | None]:
    """Run a regex in a killable stdlib-only process with bounded inputs."""
    if len(pattern) > MAX_REGEX_PATTERN_CHARS or len(text) > MAX_POLICY_INPUT_CHARS:
        return None, "policy_regex_input_limit"
    worker_source = (
        "import json,re,sys\n"
        "data=json.load(sys.stdin)\n"
        "try:\n"
        "    result={'matched': re.search(data['pattern'], data['text'], re.I) is not None}\n"
        "except re.error:\n"
        "    result={'error':'invalid'}\n"
        "sys.stdout.write(json.dumps(result))\n"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", worker_source],
            input=json.dumps({"pattern": pattern, "text": text}),
            capture_output=True,
            text=True,
            timeout=REGEX_MATCH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "policy_regex_timeout"
    except Exception:
        return None, "policy_regex_worker_failed"
    if completed.returncode != 0:
        return None, "policy_regex_worker_failed"
    try:
        result = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return None, "policy_regex_worker_failed"
    if result == {"error": "invalid"}:
        return None, "policy_regex_invalid"
    if not isinstance(result, dict) or not isinstance(result.get("matched"), bool):
        return None, "policy_regex_worker_failed"
    return result["matched"], None


class PolicyEngine:
    def __init__(self, judge_client: GroqClient | None = None):
        self._model: SentenceTransformer | None = None
        self._load_error: str | None = None
        self.groq_client = judge_client if judge_client is not None else groq_client

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def load_model(self):
        """Load only a locally cached embedding model; do not fetch weights."""
        try:
            self._model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                local_files_only=True,
            )
            self._load_error = None
        except Exception as exc:
            self._model = None
            self._load_error = type(exc).__name__
            structlog.get_logger().warning(
                "policy_embedding_model_unavailable",
                error_type=self._load_error,
                local_cache_only=True,
            )

    def encode(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if not self._model:
            raise RuntimeError("PolicyEngine model not loaded. Call load_model() first.")
        return self._model.encode(text).tolist()

    def compute_hash(
        self,
        rule_text: str,
        rule_type: str = "semantic",
        parameters: dict | None = None,
        is_enabled: bool = True,
    ) -> str:
        """Hash the behavior-affecting policy snapshot for audit/anchoring."""
        snapshot = {
            "rule_type": rule_type,
            "rule_text": rule_text,
            "parameters": parameters or {},
            "is_enabled": bool(is_enabled),
        }
        canonical = json.dumps(
            snapshot,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def embed_policy(self, db: AsyncSession, tenant_id: UUID, policy: Policy) -> None:
        """Generate embedding for a policy and store in policy_embeddings table."""
        embedding_vector = self.encode(policy.rule_text)

        # Delete old embeddings for this policy (tenant_id included for defense-in-depth)
        await db.execute(
            text("DELETE FROM policy_embeddings WHERE policy_id = :pid AND tenant_id = :tid"),
            {"pid": str(policy.id), "tid": str(tenant_id)},
        )

        pe = PolicyEmbedding(
            tenant_id=tenant_id,
            policy_id=policy.id,
            chunk_text=policy.rule_text,
            embedding=embedding_vector,
        )
        db.add(pe)
        await db.flush()

    async def check_message(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        message: str,
        top_k: int = 3,
        *,
        policy_snapshot: tuple[PolicyRuleSnapshot, ...] | None = None,
        fail_closed: bool = False,
        prior_evaluator_failure: bool = False,
    ) -> PolicyCheckResult:
        """
        Dispatch enabled policy snapshots to their matching evaluator.

        Local PII transformations and deterministic checks run before the single
        optional external LLM-judge call. Semantic similarity is reported as a
        heuristic match, not proof of a logical violation. Every match survives
        unrelated per-rule errors.
        """
        from app.config import settings

        if policy_snapshot is None:
            policy_snapshot = await load_policy_snapshot(db, tenant_id)
        active_snapshot = tuple(
            policy for policy in policy_snapshot if policy.is_enabled
        )
        if not active_snapshot:
            return PolicyCheckResult(violated=False, matched_policies=[])

        matched: list[PolicyMatch] = []
        error_codes: set[str] = set()
        redaction_counts: dict[str, int] = {}
        safe_text: str | None = message
        block_on_error = False

        if len(message) > MAX_POLICY_INPUT_CHARS:
            error_codes.add("policy_input_too_long")
            safe_text = None
            block_on_error = True

        pii_policies = tuple(
            policy for policy in active_snapshot if policy.rule_type == "pii_redaction"
        )
        for policy in pii_policies:
            if safe_text is None:
                error_codes.add("policy_evaluation_skipped_unsafe_input")
                block_on_error = True
                continue
            pii_types = policy.parameters.get("pii_types", sorted(PII_PATTERNS))
            if (
                not isinstance(pii_types, list)
                or not pii_types
                or any(
                    not isinstance(pii_type, str) or pii_type not in PII_PATTERNS
                    for pii_type in pii_types
                )
            ):
                error_codes.add("policy_pii_types_invalid")
                safe_text = None
                block_on_error = True
                continue
            try:
                result = pii_redactor.redact(safe_text, pii_types)
                safe_text = result.sanitized_text
                for item in result.redactions:
                    redaction_counts[item.type] = redaction_counts.get(item.type, 0) + 1
            except Exception:
                error_codes.add("policy_pii_redaction_failed")
                safe_text = None
                block_on_error = True

        local_policies = tuple(
            policy
            for policy in active_snapshot
            if policy.rule_type not in ("pii_redaction", "llm_eval", "semantic")
        )
        for policy in local_policies:
            if safe_text is None:
                error_codes.add("policy_evaluation_skipped_unsafe_input")
                block_on_error = True
                break
            parameters = policy.parameters

            if policy.rule_type == "keyword":
                keyword = parameters.get("keyword")
                if not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 256:
                    error_codes.add("policy_keyword_invalid")
                    continue
                # Literal case-insensitive word/phrase matching: adjacent
                # letters, digits, and underscores make a substring non-match.
                keyword_pattern = re.compile(
                    rf"(?<!\w){re.escape(keyword)}(?!\w)",
                    re.IGNORECASE,
                )
                if keyword_pattern.search(safe_text):
                    matched.append(self._make_match(policy, "keyword"))
                continue

            if policy.rule_type == "regex_match":
                pattern = parameters.get("pattern")
                if not isinstance(pattern, str) or not pattern.strip():
                    error_codes.add("policy_regex_invalid")
                    continue
                regex_matched, error_code = await asyncio.to_thread(
                    _regex_match_isolated,
                    pattern,
                    safe_text,
                )
                if error_code:
                    error_codes.add(error_code)
                elif regex_matched:
                    matched.append(self._make_match(policy, "regex_match"))
                continue

            if policy.rule_type == "prompt_injection":
                sensitivity = parameters.get("sensitivity", "moderate")
                if not isinstance(sensitivity, str) or sensitivity not in {
                    "strict",
                    "moderate",
                    "lenient",
                }:
                    error_codes.add("policy_injection_sensitivity_invalid")
                    continue
                try:
                    detection = await asyncio.to_thread(
                        injection_detector.detect_full_text,
                        safe_text,
                        sensitivity,
                    )
                except Exception:
                    error_codes.add("policy_injection_evaluation_failed")
                    continue
                if detection.is_injection:
                    matched.append(self._make_match(policy, "prompt_injection"))
                elif not detection.complete:
                    error_codes.add("policy_injection_detector_unavailable")
                continue

            error_codes.add("policy_rule_type_unsupported")

        semantic_policies = tuple(
            policy for policy in active_snapshot if policy.rule_type == "semantic"
        )
        if semantic_policies:
            if safe_text is None:
                error_codes.add("policy_evaluation_skipped_unsafe_input")
                block_on_error = True
            else:
                policy_errors: set[str] = set()
                for policy in semantic_policies:
                    policy_errors.update(policy.embedding_error_codes)
                error_codes.update(policy_errors)

                if not self._model:
                    error_codes.add("policy_embedding_model_unavailable")
                else:
                    try:
                        query_embedding = self.encode(safe_text)
                        if (
                            not query_embedding
                            or not all(isfinite(value) for value in query_embedding)
                        ):
                            raise ValueError("invalid query embedding")
                        query_norm = sqrt(
                            sum(value * value for value in query_embedding)
                        )
                        if not isfinite(query_norm) or query_norm == 0:
                            raise ValueError("invalid query norm")
                    except Exception:
                        query_embedding = []
                        query_norm = 0.0
                        error_codes.add("policy_embedding_query_failed")

                    if query_embedding:
                        for policy in semantic_policies:
                            if not policy.embeddings:
                                error_codes.add("policy_embedding_missing")
                                continue
                            try:
                                threshold = float(
                                    policy.parameters.get(
                                        "threshold",
                                        settings.policy_similarity_threshold,
                                    )
                                )
                            except (TypeError, ValueError, OverflowError):
                                error_codes.add("policy_semantic_threshold_invalid")
                                continue
                            if not isfinite(threshold) or not 0 <= threshold <= 1:
                                error_codes.add("policy_semantic_threshold_invalid")
                                continue

                            best_similarity: float | None = None
                            for rule_vector in policy.embeddings:
                                if rule_vector.chunk_text != policy.rule_text:
                                    error_codes.add("policy_embedding_stale")
                                    continue
                                if (
                                    not rule_vector.embedding
                                    or not all(
                                        isfinite(value)
                                        for value in rule_vector.embedding
                                    )
                                ):
                                    error_codes.add("policy_embedding_invalid")
                                    continue
                                if len(rule_vector.embedding) != len(query_embedding):
                                    error_codes.add(
                                        "policy_embedding_dimensions_mismatch"
                                    )
                                    continue
                                vector_norm = sqrt(
                                    sum(value * value for value in rule_vector.embedding)
                                )
                                if not isfinite(vector_norm) or vector_norm == 0:
                                    error_codes.add("policy_embedding_invalid")
                                    continue
                                dot_product = sum(
                                    query_value * policy_value
                                    for query_value, policy_value in zip(
                                        query_embedding,
                                        rule_vector.embedding,
                                        strict=True,
                                    )
                                )
                                similarity = dot_product / (query_norm * vector_norm)
                                if (
                                    best_similarity is None
                                    or similarity > best_similarity
                                ):
                                    best_similarity = similarity

                            if (
                                best_similarity is not None
                                and best_similarity >= threshold
                            ):
                                matched.append(
                                    self._make_match(
                                        policy,
                                        "semantic",
                                        round(float(best_similarity), 4),
                                    )
                                )

        # A local positive is already a block; avoid spending a judge request.
        if matched or block_on_error:
            llm_policies: tuple[PolicyRuleSnapshot, ...] = ()
        else:
            llm_policies = tuple(
                policy for policy in active_snapshot if policy.rule_type == "llm_eval"
            )

        if llm_policies and fail_closed and (
            prior_evaluator_failure or error_codes
        ):
            error_codes.add("llm_judge_skipped_after_evaluator_failure")
            block_on_error = True
            llm_policies = ()

        if llm_policies:
            if safe_text is None:
                error_codes.add("llm_judge_skipped_unsafe_input")
                block_on_error = True
            elif len(llm_policies) > MAX_LLM_JUDGE_RULES:
                error_codes.add("llm_judge_rule_limit")
                block_on_error = True
            else:
                rubrics: list[str] = []
                for policy in llm_policies:
                    rubric = policy.parameters.get("rubric")
                    if (
                        not isinstance(rubric, str)
                        or not rubric.strip()
                        or len(rubric) > 600
                    ):
                        error_codes.add("llm_judge_rubric_invalid")
                        block_on_error = True
                        break
                    rubrics.append(rubric)

                if not block_on_error:
                    try:
                        decisions = await self.groq_client.judge(
                            safe_text,
                            [JudgeRule(rubric=rubric) for rubric in rubrics],
                        )
                        if len(decisions) != len(llm_policies) or any(
                            decision not in {"allow", "violate", "uncertain"}
                            for decision in decisions
                        ):
                            raise GroqProviderError("llm_judge_invalid_response")
                    except GroqProviderError as exc:
                        error_codes.add(exc.code)
                        block_on_error = True
                    except Exception:
                        error_codes.add("llm_judge_failed")
                        block_on_error = True
                    else:
                        for policy, decision in zip(
                            llm_policies,
                            decisions,
                            strict=True,
                        ):
                            if decision == "violate":
                                matched.append(self._make_match(policy, "llm_eval"))
                            elif decision == "uncertain":
                                error_codes.add("llm_judge_uncertain")
                                block_on_error = True

        top_k = max(1, min(top_k, settings.policy_max_top_k))
        matched.sort(
            key=lambda item: (
                item.similarity_score if item.similarity_score is not None else 1.0
            ),
            reverse=True,
        )
        matched = matched[:top_k]
        return PolicyCheckResult(
            violated=len(matched) > 0,
            matched_policies=matched,
            error_codes=sorted(error_codes),
            safe_text=safe_text,
            redaction_counts=redaction_counts,
            block_on_error=block_on_error,
        )

    @staticmethod
    def _make_match(
        policy: PolicyRuleSnapshot,
        rule_type: str,
        similarity_score: float | None = None,
    ) -> PolicyMatch:
        return PolicyMatch(
            policy_id=str(policy.policy_id),
            policy_name=policy.name,
            rule_text=policy.rule_text,
            similarity_score=similarity_score,
            rule_type=rule_type,
        )


# Singleton instance
policy_engine = PolicyEngine()
