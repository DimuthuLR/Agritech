"""
Feature flags service — per-tenant capability system.

Architecture:
    Any backend module that needs to know "can this tenant use X?"
    calls features_service.is_enabled(). The answer is read from the
    tenant_features table; when no row exists, a per-key default decides.

Design principles:
- Default-ENABLED for pilot features. Existing tenants keep working
  when we deploy this.
- Config is JSONB. Shape is the caller's responsibility.
- Idempotent. Enabling an enabled feature is a no-op.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.tenant_feature import TenantFeature


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    description: str
    default_enabled: bool = True
    config_keys: tuple[str, ...] = ()


KNOWN_FEATURES: dict[str, FeatureSpec] = {
    "sensors": FeatureSpec(key="sensors", description="Live sensor readings and charts"),
    "agent": FeatureSpec(key="agent", description="AI agent pipeline"),
    "diagnosis": FeatureSpec(key="diagnosis", description="Vision-based plant disease diagnosis"),
    "chat": FeatureSpec(key="chat", description="Conversational assistant"),
    "finance": FeatureSpec(
        key="finance",
        description="Financial ledger and cost dashboard",
        config_keys=("exclude_cost_categories", "currency"),
    ),
    "dispatch": FeatureSpec(key="dispatch", description="Dispatch approved tasks via MQTT"),
    "feedback": FeatureSpec(key="feedback", description="Farmer override recording"),
    "users": FeatureSpec(key="users", description="Tenant-admin user management"),
}


def is_enabled(
    db: Session,
    tenant_id: UUID,
    feature_key: str,
    *,
    default: bool | None = None,
) -> bool:
    row = _get_row(db, tenant_id, feature_key)
    if row is not None:
        return row.disabled_at is None
    if default is not None:
        return default
    spec = KNOWN_FEATURES.get(feature_key)
    if spec is not None:
        return spec.default_enabled
    return True


def get_config(
    db: Session,
    tenant_id: UUID,
    feature_key: str,
    config_key: str,
    *,
    default: Any = None,
) -> Any:
    row = _get_row(db, tenant_id, feature_key)
    if row is None or not row.config:
        return default
    return row.config.get(config_key, default)


def get_feature_config(db: Session, tenant_id: UUID, feature_key: str) -> dict:
    row = _get_row(db, tenant_id, feature_key)
    if row is None or not row.config:
        return {}
    return dict(row.config)


def list_features(db: Session, tenant_id: UUID) -> dict[str, dict]:
    rows = db.execute(
        select(TenantFeature).where(TenantFeature.tenant_id == tenant_id)
    ).scalars().all()
    by_key = {r.feature_key: r for r in rows}

    result: dict[str, dict] = {}
    for key, spec in KNOWN_FEATURES.items():
        row = by_key.get(key)
        if row is None:
            result[key] = {
                "enabled": spec.default_enabled,
                "config": {},
                "description": spec.description,
                "default": spec.default_enabled,
            }
        else:
            result[key] = {
                "enabled": row.disabled_at is None,
                "config": dict(row.config or {}),
                "description": spec.description,
                "default": spec.default_enabled,
            }

    for key, row in by_key.items():
        if key in result:
            continue
        result[key] = {
            "enabled": row.disabled_at is None,
            "config": dict(row.config or {}),
            "description": "(unregistered)",
            "default": None,
        }
    return result


def enable_feature(
    db: Session, tenant_id: UUID, feature_key: str, *, config: dict | None = None,
) -> TenantFeature:
    _validate_key(feature_key)
    row = _get_row(db, tenant_id, feature_key)
    if row is None:
        row = TenantFeature(
            tenant_id=tenant_id, feature_key=feature_key, config=config or {},
        )
        db.add(row)
    else:
        row.disabled_at = None
        if config is not None:
            row.config = config
    db.commit()
    db.refresh(row)
    log.info(f"Enabled feature {feature_key!r} for tenant {tenant_id}")
    return row


def disable_feature(db: Session, tenant_id: UUID, feature_key: str) -> TenantFeature:
    _validate_key(feature_key)
    now = datetime.now(timezone.utc)
    row = _get_row(db, tenant_id, feature_key)
    if row is None:
        row = TenantFeature(
            tenant_id=tenant_id, feature_key=feature_key, config={}, disabled_at=now,
        )
        db.add(row)
    else:
        row.disabled_at = now
    db.commit()
    db.refresh(row)
    log.info(f"Disabled feature {feature_key!r} for tenant {tenant_id}")
    return row


def set_config(
    db: Session, tenant_id: UUID, feature_key: str, config: dict,
) -> TenantFeature:
    _validate_key(feature_key)
    if not isinstance(config, dict):
        raise ValueError(f"config must be a dict, got {type(config).__name__}")
    row = _get_row(db, tenant_id, feature_key)
    if row is None:
        row = TenantFeature(
            tenant_id=tenant_id, feature_key=feature_key, config=config,
        )
        db.add(row)
    else:
        row.config = config
    db.commit()
    db.refresh(row)
    log.info(f"Set config for feature {feature_key!r} (tenant {tenant_id})")
    return row


def _get_row(db: Session, tenant_id: UUID, feature_key: str) -> TenantFeature | None:
    return db.execute(
        select(TenantFeature).where(
            TenantFeature.tenant_id == tenant_id,
            TenantFeature.feature_key == feature_key,
        )
    ).scalar_one_or_none()


def _validate_key(feature_key: str) -> None:
    if not feature_key or not isinstance(feature_key, str):
        raise ValueError("feature_key must be a non-empty string")
    if len(feature_key) > 64:
        raise ValueError(f"feature_key too long (max 64): {feature_key!r}")