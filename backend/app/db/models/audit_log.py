"""
AuditLog — append-only trail of everything that matters.

Every AI decision, safety check, human approval, login, support session,
and configuration change writes here. The hash chain (prev_hash → hash)
makes tampering detectable: if any row is altered, all hashes after it break.

Enforcement of append-only at the DB level (REVOKE UPDATE, DELETE) is
applied by a later migration.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, BigInteger, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    # BIGSERIAL because audit logs grow fast — faster than UUIDs on append.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # What kind of event. Examples:
    #   agent.decision | safety.violation | safety.suppressed
    #   auth.login | auth.fail | support.session.start | support.session.end
    #   config.change | device.register | actuator.command
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Who. actor is either 'agent', 'system', or 'user:<uuid>'.
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Whose data was touched (null for platform-level events).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Optional context
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Model + prompt versioning (for AI decisions)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Where the request came from
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    # The payload — tool arguments, error details, diagnosis JSON, etc.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Hash chain for tamper evidence.
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog {self.kind} actor={self.actor!r} at={self.occurred_at}>"