"""
DeviceClaimCode — one-time codes for physical device provisioning.

Flow:
    1. Tenant admin generates a code (via UI or CLI).
    2. Admin types the code into the physical device.
    3. Device calls POST /iot/register with its MAC + the code.
    4. Server validates, creates a Device row, marks code used.

The code is a one-time bearer token: valid until used OR until it
expires, whichever comes first.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceClaimCode(Base):
    __tablename__ = "device_claim_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    used_by_device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        state = "used" if self.used_at else "available"
        return f"<DeviceClaimCode {self.code!r} ({state})>"