"""Policy CRUD endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models.policy import Policy
from app.models.safety_config import SafetyConfig
from app.models.tenant import Tenant
from app.schemas.policies import (
    PolicyConfigResponse,
    PolicyConfigUpdate,
    PolicyCreate,
    PolicyListResponse,
    PolicyResponse,
    PolicyUpdate,
    validate_rule_parameters,
)
from app.services.guardrails.policy_engine import policy_engine
from app.worker import register_policy_on_chain_task

router = APIRouter(prefix="/policies", tags=["Policies"])
logger = structlog.get_logger()


@router.get("/config", response_model=PolicyConfigResponse)
async def get_policy_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PolicyConfigResponse:
    """Get tenant policy behavior configuration."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Safety config not found")

    return PolicyConfigResponse(
        tenant_id=tenant.id,
        active_policy_version=tenant.active_policy_version,
        injection_protection=config.injection_protection,
        injection_sensitivity=config.injection_sensitivity,
        pii_redaction=config.pii_redaction,
        policy_enforcement=config.policy_enforcement,
        fail_mode=config.fail_mode,
        fallback_message=config.fallback_message,
    )


@router.put("/config", response_model=PolicyConfigResponse)
async def update_policy_config(
    body: PolicyConfigUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PolicyConfigResponse:
    """Update tenant policy behavior and bump active policy version."""
    result = await db.execute(
        select(SafetyConfig).where(SafetyConfig.tenant_id == tenant.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Safety config not found")

    update_data = body.model_dump(exclude_unset=True)
    if "injection_protection" in update_data:
        config.injection_protection = update_data["injection_protection"]
    if "injection_sensitivity" in update_data:
        config.injection_sensitivity = update_data["injection_sensitivity"]
    if "pii_redaction" in update_data:
        config.pii_redaction = update_data["pii_redaction"]
    if "policy_enforcement" in update_data:
        config.policy_enforcement = update_data["policy_enforcement"]
    if "fail_mode" in update_data:
        config.fail_mode = update_data["fail_mode"]
    if "fallback_message" in update_data:
        config.fallback_message = update_data["fallback_message"]

    tenant.active_policy_version += 1
    await db.commit()
    await db.refresh(config)
    await db.refresh(tenant)

    return PolicyConfigResponse(
        tenant_id=tenant.id,
        active_policy_version=tenant.active_policy_version,
        injection_protection=config.injection_protection,
        injection_sensitivity=config.injection_sensitivity,
        pii_redaction=config.pii_redaction,
        policy_enforcement=config.policy_enforcement,
        fail_mode=config.fail_mode,
        fallback_message=config.fallback_message,
    )


@router.get("/", response_model=PolicyListResponse)
async def list_policies(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PolicyListResponse:
    """List all policies owned by the authenticated tenant."""
    result = await db.execute(
        select(Policy)
        .where(Policy.tenant_id == tenant.id)
        .order_by(Policy.created_at.desc())
    )
    policies = result.scalars().all()
    return PolicyListResponse(policies=policies, total=len(policies))


@router.post("/", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: PolicyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    """Create a policy and enqueue its optional on-chain registration."""
    policy_hash = policy_engine.compute_hash(
        body.rule_text,
        body.rule_type,
        body.parameters,
        True,
    )

    policy = Policy(
        tenant_id=tenant.id,
        name=body.name,
        description=body.description,
        rule_text=body.rule_text,
        rule_type=body.rule_type,
        parameters=body.parameters or {},
        policy_hash=policy_hash,
    )
    db.add(policy)
    await db.flush()

    if body.rule_type == "semantic":
        try:
            await policy_engine.embed_policy(db, tenant.id, policy)
        except Exception as exc:
            logger.warning(
                "semantic_policy_embedding_unavailable",
                error_type=type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Semantic policy embeddings are unavailable.",
            ) from None
    tenant.active_policy_version += 1
    await db.commit()
    await db.refresh(policy)

    try:
        register_policy_on_chain_task.delay(str(policy.id), policy_hash)
    except Exception as exc:
        logger.warning(
            "optional_policy_anchor_enqueue_failed",
            policy_id=str(policy.id),
            error_type=type(exc).__name__,
        )
    return policy


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    body: PolicyUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    """Update a policy for the authenticated tenant."""
    result = await db.execute(
        select(Policy).where(Policy.id == policy_id, Policy.tenant_id == tenant.id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    original_rule_type = policy.rule_type
    original_rule_text = policy.rule_text
    update_data = body.model_dump(exclude_unset=True)
    for required_field in ("name", "rule_text", "rule_type", "is_enabled"):
        if required_field in update_data and update_data[required_field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{required_field} cannot be null",
            )

    updated_rule_type = update_data.get("rule_type", policy.rule_type)
    updated_rule_text = update_data.get("rule_text", policy.rule_text)
    updated_parameters = update_data.get("parameters", policy.parameters or {}) or {}
    behavior_changed = (
        updated_rule_text != policy.rule_text
        or updated_rule_type != policy.rule_type
        or updated_parameters != (policy.parameters or {})
        or (
            "is_enabled" in update_data
            and update_data["is_enabled"] != policy.is_enabled
        )
    )
    if behavior_changed:
        try:
            validate_rule_parameters(updated_rule_type, updated_parameters)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from None

    if "name" in update_data:
        policy.name = update_data["name"]
    if "description" in update_data:
        policy.description = update_data["description"]
    if "rule_text" in update_data:
        policy.rule_text = updated_rule_text
    if "rule_type" in update_data:
        policy.rule_type = updated_rule_type
    if "parameters" in update_data:
        policy.parameters = updated_parameters
    if "is_enabled" in update_data:
        policy.is_enabled = update_data["is_enabled"]

    if behavior_changed:
        policy.policy_hash = policy_engine.compute_hash(
            policy.rule_text,
            policy.rule_type,
            policy.parameters,
            policy.is_enabled,
        )
        policy.version += 1
        tenant.active_policy_version += 1
        needs_semantic_embedding = updated_rule_type == "semantic" and (
            updated_rule_text != original_rule_text
            or original_rule_type != "semantic"
        )
        if needs_semantic_embedding:
            try:
                await policy_engine.embed_policy(db, tenant.id, policy)
            except Exception as exc:
                logger.warning(
                    "semantic_policy_embedding_unavailable",
                    error_type=type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Semantic policy embeddings are unavailable.",
                ) from None

    await db.commit()
    await db.refresh(policy)
    if behavior_changed:
        try:
            register_policy_on_chain_task.delay(str(policy.id), policy.policy_hash)
        except Exception as exc:
            logger.warning(
                "optional_policy_anchor_enqueue_failed",
                policy_id=str(policy.id),
                error_type=type(exc).__name__,
            )
    return policy


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a policy owned by the authenticated tenant."""
    result = await db.execute(
        select(Policy).where(Policy.id == policy_id, Policy.tenant_id == tenant.id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    await db.delete(policy)
    tenant.active_policy_version += 1
    await db.commit()
