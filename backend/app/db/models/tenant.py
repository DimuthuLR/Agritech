"""
Tenant model — the top-level organization. One tenant = one farm business.

Every domain entity (Farm, Plot, Device, ...) belongs to exactly one Tenant.
Platform staff belong to no tenant — they're identified by a null tenant_id
on the User model (added later).
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    region: Mapped[str] = mapped_column(String(16), nullable=False, default="EU")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # A tenant can own many farms. Deleting a tenant cascades.
    farms: Mapped[list["Farm"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    features: Mapped[list["TenantFeature"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug!r} name={self.name!r}>"