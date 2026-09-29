"""
User model — accounts for both tenant users and platform staff.

A user belongs to EITHER a tenant (tenant_id set) OR the platform (tenant_id null).
A DB-level check constraint enforces this — the app cannot create a malformed user.
"""
import uuid
import enum
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import (
    String, DateTime, Boolean, ForeignKey, func, CheckConstraint, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TenantRole(str, enum.Enum):
    """Roles a user can have within a tenant."""
    VIEWER = "viewer"
    OPERATOR = "operator"
    AGRONOMIST = "agronomist"
    TENANT_ADMIN = "tenant_admin"


class PlatformRole(str, enum.Enum):
    """Roles a user can have as a platform (Hex Hive) staff member."""
    SUPPORT_AGENT = "support_agent"
    PLATFORM_ADMIN = "platform_admin"
    SUPER_ADMIN = "super_admin"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "("
            "  tenant_id IS NOT NULL AND tenant_role IS NOT NULL AND platform_role IS NULL"
            ") OR ("
            "  tenant_id IS NULL AND tenant_role IS NULL AND platform_role IS NOT NULL"
            ")",
            name="ck_users_role_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Identity
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # State
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    # Tenancy — null means platform user, non-null means tenant user
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tenant_role: Mapped[TenantRole | None] = mapped_column(
        SAEnum(TenantRole, name="tenant_role"), nullable=True
    )
    platform_role: Mapped[PlatformRole | None] = mapped_column(
        SAEnum(PlatformRole, name="platform_role"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship back to tenant (only populated for tenant users)
    tenant: Mapped["Tenant | None"] = relationship(back_populates="users")

    def __repr__(self) -> str:
        return f"<User {self.email!r} role={self.tenant_role or self.platform_role}>"