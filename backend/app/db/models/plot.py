"""
Plot model — a physical area of land within a farm.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Plot(Base):
    __tablename__ = "plots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Geographic info
    area_ha: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Agronomy
    crop: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    farm: Mapped["Farm"] = relationship(back_populates="plots")

    def __repr__(self) -> str:
        return f"<Plot {self.name!r} crop={self.crop} area={self.area_ha}ha>"