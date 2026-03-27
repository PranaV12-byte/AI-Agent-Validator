"""Policy CRUD endpoints."""

from uuid import UUID

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
)
from app.services.guardrails.policy_engine import policy_engine
from app.worker import register_policy_on_chain_task

router = APIRouter(prefix="/policies", tags=["Policies"])


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
    """Create a policy, embed it, and enqueue on-chain registration."""
    policy_hash = policy_engine.compute_hash(body.rule_text)

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

    await policy_engine.embed_policy(db, tenant.id, policy)
    await db.commit()
    await db.refresh(policy)

    register_policy_on_chain_task.delay(str(policy.id), policy_hash)
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

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data:
        policy.name = update_data["name"]
    if "description" in update_data:
        policy.description = update_data["description"]
    if "rule_text" in update_data:
        policy.rule_text = update_data["rule_text"]
    if "rule_type" in update_data:
        policy.rule_type = update_data["rule_type"]
    if "parameters" in update_data:
        policy.parameters = update_data["parameters"]
    if "is_enabled" in update_data:
        policy.is_enabled = update_data["is_enabled"]

    if "rule_text" in update_data:
        policy.policy_hash = policy_engine.compute_hash(policy.rule_text)
        policy.version += 1
        await policy_engine.embed_policy(db, tenant.id, policy)

    await db.commit()
    await db.refresh(policy)
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
    await db.commit()
