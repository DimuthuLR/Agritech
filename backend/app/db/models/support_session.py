"""
SupportSession — audited impersonation record.

When a platform user (support agent, platform admin, super admin)
impersonates a tenant user, that action must be logged. This table
is the audit trail for the platform plane: who entered which tenant,
as whom, why, when, and from where.

Design:
- One row per session, not per request. A session is a time window.
- ended_at NULL = session is active.
- user references use ON DELETE SET NULL so audit history survives
  user deletion. The session row stays; the pointer becomes null.
- target_tenant_id uses ON DELETE CASCADE: if a tenant is ever
  hard-deleted, the sessions that touched it go too.
- reason is mandatory — no anonymous impersonation.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupportSession(Base):
    __tablename__ = "support_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Who is doing the impersonating (the platform user).
    platform_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Who they are impersonating as (the tenant user).
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Which tenant the session entered. Denormalized for fast reports.
    target_tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Why this session exists. Free text. Mandatory.
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional external ticket reference (e.g. "SUP-1234").
    ticket_reference: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    # Lifecycle
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        nullable=False, index=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Request metadata for audit
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        state = "active" if self.ended_at is None else "ended"
        return f"<SupportSession {self.id} ({state}) tenant={self.target_tenant_id}>"