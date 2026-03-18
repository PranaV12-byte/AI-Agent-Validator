"""
SQLAlchemy model registry for Safebot.

Importing this module ensures all models are registered with
Base.metadata (required for Alembic autogenerate to detect all tables).
"""

from app.models.tenant import Tenant
from app.models.policy import Policy
from app.models.policy_embedding import PolicyEmbedding
from app.models.audit_log import AuditLog
from app.models.safety_config import SafetyConfig
from app.models.api_usage import ApiUsage

__all__ = [
    "Tenant",
    "Policy",
    "PolicyEmbedding",
    "AuditLog",
    "SafetyConfig",
    "ApiUsage",
]
