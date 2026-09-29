"""
TenantFeature — feature-flag registry, one row per (tenant, feature).

A tenant only has access to features that are enabled here. Routes check
this at request time; the agent composes its tool list from enabled features.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TenantFeature(Base):
    __tablename__ = "tenant_features"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Free-form per-feature configuration (validated against the module's schema)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    enabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="features")

    def __repr__(self) -> str:
        state = "disabled" if self.disabled_at else "enabled"
        return f"<TenantFeature {self.feature_key!r} for {self.tenant_id} ({state})>"