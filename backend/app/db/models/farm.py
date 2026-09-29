"""
Farm model — top-level entity for a farm location.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(16), nullable=False, default="EU")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship to Plot. Backref: farm.plots returns a list of Plot objects.
    plots: Mapped[list["Plot"]] = relationship(
        back_populates="farm", cascade="all, delete-orphan"
    )
    tenant: Mapped["Tenant"] = relationship(back_populates="farms")

    def __repr__(self) -> str:
        return f"<Farm {self.name!r} region={self.region}>"