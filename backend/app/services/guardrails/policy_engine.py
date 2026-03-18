"""
Policy Engine: Semantic matching of AI responses against business policies using
SentenceTransformers embeddings + pgvector similarity search.
"""
import hashlib
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID

from app.models.policy import Policy
from app.models.policy_embedding import PolicyEmbedding


@dataclass
class PolicyMatch:
    policy_id: str
    policy_name: str
    rule_text: str
    similarity_score: float


@dataclass
class PolicyCheckResult:
    violated: bool
    matched_policies: list[PolicyMatch]


class PolicyEngine:
    def __init__(self):
        self._model: SentenceTransformer | None = None

    def load_model(self):
        """Load embedding model at startup."""
        self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if not self._model:
            raise RuntimeError("PolicyEngine model not loaded. Call load_model() first.")
        return self._model.encode(text).tolist()

    def compute_hash(self, rule_text: str) -> str:
        """SHA-256 hash of policy rule text for on-chain registration."""
        return hashlib.sha256(rule_text.encode("utf-8")).hexdigest()

    async def embed_policy(self, db: AsyncSession, tenant_id: UUID, policy: Policy) -> None:
        """Generate embedding for a policy and store in policy_embeddings table."""
        embedding_vector = self.encode(policy.rule_text)

        # Delete old embeddings for this policy
        await db.execute(
            text("DELETE FROM policy_embeddings WHERE policy_id = :pid"),
            {"pid": str(policy.id)},
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
        self, db: AsyncSession, tenant_id: UUID, message: str, top_k: int = 3
    ) -> PolicyCheckResult:
        """
        Check if a message violates any tenant policies via semantic similarity.
        Returns policies with cosine similarity > 0.65 (configurable threshold).
        """
        SIMILARITY_THRESHOLD = 0.65

        query_embedding = self.encode(message)

        # pgvector cosine similarity search
        sql = text("""
            SELECT pe.policy_id, pe.chunk_text,
                   1 - (pe.embedding <=> :query_vec::vector) AS similarity,
                   p.name AS policy_name, p.rule_text
            FROM policy_embeddings pe
            JOIN policies p ON pe.policy_id = p.id
            WHERE pe.tenant_id = :tid
              AND p.is_enabled = true
            ORDER BY pe.embedding <=> :query_vec::vector
            LIMIT :top_k
        """)

        result = await db.execute(sql, {
            "query_vec": str(query_embedding),
            "tid": str(tenant_id),
            "top_k": top_k,
        })

        rows = result.fetchall()

        matched = []
        for row in rows:
            if row.similarity >= SIMILARITY_THRESHOLD:
                matched.append(PolicyMatch(
                    policy_id=str(row.policy_id),
                    policy_name=row.policy_name,
                    rule_text=row.rule_text,
                    similarity_score=round(float(row.similarity), 4),
                ))

        return PolicyCheckResult(
            violated=len(matched) > 0,
            matched_policies=matched,
        )


# Singleton instance
policy_engine = PolicyEngine()
